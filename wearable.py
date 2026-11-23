"""Bounded, user-initiated health imports. No vendor connection is implied."""
import csv
import io
import json
import math
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

from engine import RequestError

MAX_IMPORT = 100 * 1024 * 1024
MAX_XML = 400 * 1024 * 1024
MAX_ROWS = 2_000_000
FRESH_HOURS = 36
KINDS = {
    'HKQuantityTypeIdentifierRestingHeartRate': ('resting_hr', '静息心率', '次/分'),
    'HKQuantityTypeIdentifierHeartRate': ('heart_rate', '心率', '次/分'),
    'HKQuantityTypeIdentifierHeartRateVariabilitySDNN': ('hrv_sdnn', 'HRV（SDNN）', 'ms'),
    'HKQuantityTypeIdentifierStepCount': ('steps', '步数', '步'),
    'HKCategoryTypeIdentifierSleepAnalysis': ('sleep', '睡眠时长', '小时'),
    'heart_rate': ('heart_rate', '心率', '次/分'),
    'resting_hr': ('resting_hr', '静息心率', '次/分'),
    'hrv_sdnn': ('hrv_sdnn', 'HRV（SDNN）', 'ms'),
    'hrv_rmssd': ('hrv_rmssd', 'HRV（RMSSD）', 'ms'),
    'sleep': ('sleep', '睡眠时长', '小时'),
    'steps': ('steps', '步数', '步'),
}


def when(value):
    try:
        d = datetime.fromisoformat(str(value).strip().replace('Z', '+00:00'))
        return d if d.tzinfo else d.astimezone()
    except (ValueError, TypeError, OverflowError):
        return None


def _union_hours(intervals):
    """Union sleep stages, including overlapping 'Asleep' summary intervals."""
    total = 0.0
    start = end = None
    for a, b in sorted(intervals):
        if start is None:
            start, end = a, b
        elif a <= end:
            end = max(end, b)
        else:
            total += (end - start).total_seconds()
            start, end = a, b
    if start is not None:
        total += (end - start).total_seconds()
    return total / 3600


def summarize(rows, source_type):
    now = datetime.now().astimezone()
    latest = {}
    sleep = []
    steps = []
    seen = set()
    accepted = 0
    for index, r in enumerate(rows):
        if index >= MAX_ROWS:
            raise RequestError('文件记录过多，请导出较短日期范围后重试。', 'too_many_records', 422)
        if not isinstance(r, dict):
            continue
        kind = KINDS.get(str(r.get('type', '')))
        if not kind:
            continue
        key, label, unit = kind
        at = when(r.get('endDate') or r.get('date') or r.get('at'))
        if not at or at > now + timedelta(minutes=5) or at < now - timedelta(days=30):
            continue
        source = str(r.get('sourceName') or r.get('source') or '用户导入（来源未注明）').strip()[:100]
        value_raw = r.get('value')
        ru = str(r.get('unit') or '').strip().lower()
        start = when(r.get('startDate'))
        try:
            if key == 'sleep' and str(value_raw).startswith('HKCategoryValue'):
                if 'Asleep' not in str(value_raw) or not start:
                    continue
                value = (at - start).total_seconds() / 3600
            else:
                value = float(value_raw)
                if key in ('heart_rate', 'resting_hr'):
                    if ru not in ('', 'count/min', 'bpm', '次/分', 'beats/min'):
                        continue
                elif key.startswith('hrv_'):
                    if ru in ('s', 'sec', 'seconds', '秒'):
                        value *= 1000
                    elif ru not in ('', 'ms', '毫秒'):
                        continue
                elif key == 'sleep':
                    if ru in ('min', 'minutes', '分钟'):
                        value /= 60
                    elif ru in ('s', 'sec', 'seconds', '秒'):
                        value /= 3600
                    elif ru not in ('', 'h', 'hr', 'hours', 'hour', '小时'):
                        continue
                    start = at - timedelta(hours=value) if math.isfinite(value) else None
                elif ru not in ('', 'count', 'steps', '步'):
                    continue
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(value) or value < 0:
            continue
        if ((key in ('heart_rate', 'resting_hr') and not 20 <= value <= 250)
                or (key.startswith('hrv_') and value > 1000)
                or (key == 'sleep' and not 0 < value <= 24)
                or (key == 'steps' and value > 100000)):
            continue
        if start and (start > at or at - start > timedelta(hours=24)):
            continue
        identity = (key, at.isoformat(), start.isoformat() if start else None, round(value, 6), source)
        if key in ('sleep', 'steps'):
            if identity in seen:
                continue
            if len(seen) >= 250000:
                raise RequestError('近期睡眠或步数记录过多，请缩短导出范围。', 'too_many_records', 422)
            seen.add(identity)
        accepted += 1
        rec = dict(key=key, label=label, value=round(value, 2), unit=unit,
                   source=source, at=at.isoformat())
        if key == 'sleep':
            sleep.append((rec, start, at))
        elif key == 'steps':
            steps.append((rec, start, at))
        elif key not in latest or at >= when(latest[key]['at']):
            latest[key] = rec

    # Select exactly one source. Union its recent sleep intervals instead of
    # summing both summary Asleep records and detailed REM/Core/Deep stages.
    if sleep:
        latest_sleep, _, end = max(sleep, key=lambda item: item[2])
        begin = end - timedelta(hours=24)
        selected = [(max(start, begin), at) for r, start, at in sleep
                    if r['source'] == latest_sleep['source'] and at > begin and start]
        total = _union_hours(selected)
        if total > 0:
            latest['sleep'] = dict(latest_sleep, value=round(total, 2),
                                   aggregation='single_source_interval_union_24h',
                                   windowStart=begin.isoformat(), windowEnd=end.isoformat())
    if steps:
        last, _, end = max(steps, key=lambda item: item[2])
        selected = [(r, a, b) for r, a, b in steps
                    if r['source'] == last['source'] and b.astimezone().date() == end.astimezone().date()]
        ranges = sorted((a, b) for _, a, b in selected if a and a < b)
        overlaps = any(a < previous[1] for previous, (a, b) in zip(ranges, ranges[1:]))
        # Some exports mix cumulative and interval step records. Do not invent
        # a daily total when those ranges overlap or timestamps are ambiguous.
        ambiguous = len(selected) > 1 and (overlaps or any(not a for _, a, _ in selected))
        total = sum(r['value'] for r, _, _ in selected)
        ambiguous = ambiguous or total > 100000
        latest['steps'] = dict(last, value=last['value'] if ambiguous else round(total),
                               label='步数（最新记录）' if ambiguous else '步数（当日导入记录合计）',
                               aggregation='latest_record' if ambiguous else 'single_source_daily_sum')
    if not latest:
        raise RequestError('文件中没有最近 30 天可读取的心率、睡眠、步数或 HRV 记录。请检查日期和导出格式。',
                           'no_health_records', 422)
    return {'sourceType': source_type, 'importedAt': now.isoformat(),
            'metrics': list(latest.values()), 'sourceNames': sorted(set(r['source'] for r in latest.values())),
            'status': 'imported', 'acceptedRecords': accepted}


class _XMLReader:
    """Bound expanded bytes and refuse entity declarations without rejecting
    Apple's ordinary HealthData element/attribute DOCTYPE declarations."""
    def __init__(self, stream):
        self.stream = stream
        self.read_bytes = 0
        self.tail = b''

    def read(self, size=-1):
        data = self.stream.read(min(size, 65536) if size > 0 else 65536)
        self.read_bytes += len(data)
        if self.read_bytes > MAX_XML:
            raise RequestError('健康 XML 解压后超过 400 MB，请导出较短日期范围。', 'xml_size', 413)
        inspect = self.tail + data
        if b'<!ENTITY' in inspect.upper():
            raise RequestError('健康 XML 含不支持的实体声明，请重新导出。', 'bad_xml', 422)
        self.tail = inspect[-16:]
        return data


def parse_export(data, filename):
    if not data:
        raise RequestError('健康文件为空，请重新选择文件。', 'empty_import', 422)
    if len(data) > MAX_IMPORT:
        raise RequestError('健康文件超过 100 MB。', 'import_size', 413)
    if data.startswith(b'PK'):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                files = [item for item in z.infolist()
                         if item.filename.lower().endswith(('export.xml', '导出.xml')) and not item.is_dir()]
                if len(files) != 1 or files[0].file_size > MAX_XML or files[0].flag_bits & 1:
                    raise ValueError()
                with z.open(files[0]) as f:
                    return parse_xml(f)
        except (zipfile.BadZipFile, ValueError, OSError, RuntimeError, NotImplementedError, EOFError):
            raise RequestError('ZIP 中需要一份未加密的 Apple 健康 export.xml，解压后不超过 400 MB。',
                               'bad_health_zip', 422)
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise RequestError('无法读取健康文件，请选择 UTF-8 CSV、JSON 或 Apple 健康导出。', 'bad_health_file', 422)
    stripped = text.lstrip()
    if stripped.startswith('<'):
        return parse_xml(io.BytesIO(stripped.encode('utf-8')))
    try:
        if stripped[:1] in ('{', '['):
            obj = json.loads(text)
            rows = obj if isinstance(obj, list) else obj.get('records', []) if isinstance(obj, dict) else None
            if not isinstance(rows, list):
                raise ValueError()
        else:
            rows = csv.DictReader(io.StringIO(text), strict=True)
            if not rows.fieldnames or 'type' not in rows.fieldnames or 'value' not in rows.fieldnames:
                raise ValueError()
        return summarize(rows, '健康记录导入')
    except (ValueError, csv.Error, RecursionError):
        raise RequestError('请上传 Apple 健康 XML/ZIP，或符合模板的 CSV/JSON 文件。', 'bad_health_file', 422)


def parse_xml(stream):
    try:
        def rows():
            root = None
            for event, element in ET.iterparse(_XMLReader(stream), events=('start', 'end')):
                if root is None:
                    root = element
                if event == 'end':
                    if element.tag == 'Record':
                        yield element.attrib.copy()
                    element.clear()
                    if root is not element:
                        root.clear()
        return summarize(rows(), 'Apple 健康导出')
    except (ET.ParseError, ValueError, OverflowError, LookupError):
        raise RequestError('健康 XML 文件不完整或格式不正确。', 'bad_xml', 422)


def device_view(ctx):
    w = ctx.get('wearable') or {}
    permitted = bool(ctx.get('permissions', {}).get('device'))
    now = datetime.now().astimezone()
    metrics = []
    for r in w.get('metrics', []) if permitted else []:
        at = when(r.get('at'))
        age = (now - at).total_seconds() / 3600 if at else None
        fresh = age is not None and -5 / 60 <= age <= FRESH_HOURS
        metrics.append(dict(r, value=str(r['value']), fresh=fresh,
                            freshness='recent' if fresh else 'stale',
                            ageHours=round(max(0, age), 1) if age is not None else None,
                            quality='最近记录' if fresh else '历史记录 · 不作为当前状态依据'))
    current = [r for r in metrics if r['fresh']]
    keys = {r['key'] for r in current}
    complete = {'sleep', 'resting_hr'}.issubset(keys) and bool(keys & {'hrv_sdnn', 'hrv_rmssd'})
    mode = ('complete' if complete else 'missing') if current else 'stale' if metrics else 'disconnected'
    if not w.get('metrics'):
        label, quality = '尚无穿戴记录', '导入 Apple 健康或规范文件，保留来源和采集时间，结合本人感受用于安排。'
    elif not permitted:
        label, quality = '未授权读取', '授权后才能将已导入的记录用于调整；不会自动读取设备账号。'
    elif current:
        label = '蓝牙心率记录已更新' if w.get('sourceType') == 'Bluetooth' else '健康数据已导入'
        quality = '仅引用各项最近 36 小时内的记录；历史记录不作为当前状态依据。单项数值不等于恢复或训练结论。'
        if not complete:
            quality += '睡眠、静息心率或 HRV 有缺失／过期，需要结合本人反馈。'
    elif metrics:
        label, quality = '历史数据 · 需要更新', '记录已超过 36 小时，本次调整不将其当作当前身体状态。'
    else:
        label, quality = '未连接设备', '导入你的健康记录；厂商账号授权与文件导入分别展示。'
    return {'mode': mode, 'label': label, 'syncedAt': w.get('importedAt', ''), 'quality': quality, 'hasRecords': bool(w.get('metrics')),
            'metrics': metrics, 'evidenceMetrics': current, 'simulated': False,
            'sourceType': w.get('sourceType'), 'sourceNames': sorted(set(r['source'] for r in metrics)),
            'live': False, 'connectionType': 'bluetooth_capture' if w.get('sourceType') == 'Bluetooth' else 'file_import',
            'lastCaptureBluetooth': w.get('sourceType') == 'Bluetooth'}
