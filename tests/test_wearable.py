import io
import json
from pathlib import Path
import sys
import unittest
import zipfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import RequestError
from wearable import parse_export, summarize, device_view, when


class WearableTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc).replace(microsecond=0)

    def record(self, kind='resting_hr', value=58, ago=1, source='Garmin', **kw):
        return dict(type=kind, value=value, at=(self.now-timedelta(hours=ago)).isoformat(), source=source, **kw)

    def parse_json(self, records):
        return parse_export(json.dumps({'records': records}).encode(), 'health.json')

    def expect_error(self, data, code=None):
        with self.assertRaises(RequestError) as cm:
            parse_export(data, 'test')
        self.assertEqual(cm.exception.status, 422)
        if code:
            self.assertEqual(cm.exception.code, code)

    def test_json_source_units_and_method(self):
        rows = [self.record(), self.record('hrv_sdnn', .052, unit='s'),
                self.record('hrv_rmssd', 49, unit='ms'), self.record('sleep', 420, unit='min')]
        result = self.parse_json(rows)
        metrics = {r['key']: r for r in result['metrics']}
        self.assertEqual(metrics['sleep']['value'], 7)
        self.assertEqual(metrics['hrv_sdnn']['value'], 52)
        self.assertEqual(metrics['hrv_rmssd']['value'], 49)
        self.assertEqual(result['sourceNames'], ['Garmin'])
        self.assertEqual(result['status'], 'imported')

    def test_csv_with_bom_and_quotes(self):
        data = ('\ufefftype,value,unit,at,source\nresting_hr,58,bpm,' + self.record()['at'] + ',"My Garmin"\n').encode()
        out = parse_export(data, 'health.csv')
        self.assertEqual(out['metrics'][0]['source'], 'My Garmin')

    def xml(self, records, header=''):
        import html
        tags = ''.join('<Record ' + ' '.join(f'{k}="{html.escape(str(v), quote=True)}"' for k,v in r.items()) + '/>' for r in records)
        return ('<?xml version="1.0" encoding="UTF-8"?>' + header + '<HealthData>' + tags + '</HealthData>').encode()

    def test_apple_xml_and_zip(self):
        row = {'type':'HKQuantityTypeIdentifierRestingHeartRate', 'value':'60',
               'unit':'count/min', 'sourceName':'Apple Watch', 'endDate': self.record()['at']}
        raw = self.xml([row], '<!DOCTYPE HealthData [<!ELEMENT HealthData (Record*)><!ELEMENT Record EMPTY>]>')
        for data in (raw, b'\xef\xbb\xbf'+raw):
            out = parse_export(data, 'export.xml')
            self.assertEqual(out['metrics'][0]['value'], 60)
            self.assertEqual(out['sourceNames'], ['Apple Watch'])
        f = io.BytesIO()
        with zipfile.ZipFile(f, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('apple_health_export/export.xml', raw)
            z.writestr('apple_health_export/workout-routes/test.gpx', '<gpx/>')
        out = parse_export(f.getvalue(), 'export.zip')
        self.assertEqual(out['sourceType'], 'Apple 健康导出')

    def test_sleep_union_prevents_summary_stage_and_duplicate_double_count(self):
        end = self.now-timedelta(hours=1)
        start = end-timedelta(hours=8)
        common = {'type': 'HKCategoryTypeIdentifierSleepAnalysis', 'sourceName':'Apple Watch'}
        def r(a,b,val):
            return dict(common, startDate=a.isoformat(), endDate=b.isoformat(), value=val)
        rows = [r(start,end,'HKCategoryValueSleepAnalysisAsleepUnspecified'),
                r(start,start+timedelta(hours=5),'HKCategoryValueSleepAnalysisAsleepCore'),
                r(start+timedelta(hours=5),end,'HKCategoryValueSleepAnalysisAsleepREM')]
        rows.extend([rows[0].copy(), r(start-timedelta(hours=1),end,'HKCategoryValueSleepAnalysisInBed')])
        result = parse_export(self.xml(rows), 'sleep.xml')
        self.assertEqual(result['metrics'][0]['value'],8)
        self.assertEqual(result['metrics'][0]['aggregation'],'single_source_interval_union_24h')

    def test_sleep_sources_not_added_together(self):
        rows=[self.record('sleep',7,source='Apple Watch'), self.record('sleep',6.5,ago=2,source='Phone')]
        out=self.parse_json(rows)
        self.assertEqual(out['metrics'][0]['value'],7)
        self.assertEqual(out['metrics'][0]['source'],'Apple Watch')

    def test_sleep_old_intervals_clipped_to_window(self):
        end=self.now-timedelta(hours=1)
        rows=[dict(type='HKCategoryTypeIdentifierSleepAnalysis', sourceName='Watch',
                   startDate=(end-timedelta(hours=26)).isoformat(),endDate=(end-timedelta(hours=20)).isoformat(),
                   value='HKCategoryValueSleepAnalysisAsleepCore'), self.record('sleep',2)]
        # Different source: latest source wins, rather than adding yesterday.
        self.assertEqual(self.parse_json(rows)['metrics'][0]['value'],2)

    def test_unrecognized_units_nonfinite_and_bad_values_ignored(self):
        rows = [self.record('heart_rate',999), self.record('resting_hr',58,unit='kg'),
                self.record('hrv_sdnn',float('nan')), self.record('sleep',-1), self.record('steps',100001),
                self.record('heart_rate',72)]
        out=self.parse_json(rows)
        self.assertEqual([(r['key'],r['value']) for r in out['metrics']],[('heart_rate',72)])

    def test_future_and_old_values_not_imported(self):
        out=self.parse_json([self.record(ago=-24), self.record(ago=24*31), self.record(ago=1,value=61)])
        self.assertEqual(out['metrics'][0]['value'],61)

    def test_different_offsets_sorted_as_instants(self):
        newer=self.record(value=57,ago=1)
        older=self.record(value=65,ago=2)
        older['at']=when(older['at']).astimezone(timezone(timedelta(hours=10))).isoformat()
        self.assertEqual(self.parse_json([newer,older])['metrics'][0]['value'],57)

    def test_step_overlap_never_double_counts_cumulative_with_intervals(self):
        end=self.now-timedelta(hours=1)
        rows=[dict(type='steps',value=5000,startDate=(end-timedelta(hours=4)).isoformat(),endDate=end.isoformat(),source='Watch'),
              dict(type='steps',value=1000,startDate=(end-timedelta(hours=1)).isoformat(),endDate=end.isoformat(),source='Watch')]
        out=self.parse_json(rows)['metrics'][0]
        self.assertEqual(out['aggregation'],'latest_record')
        self.assertNotEqual(out['value'],6000)
        self.assertEqual(out['label'],'步数（最新记录）')

    def test_step_nonoverlap_sum_same_source(self):
        end=self.now.astimezone().replace(hour=18)
        if end>self.now:end-=timedelta(days=1)
        rows=[dict(type='steps',value=200,startDate=(end-timedelta(hours=4)).isoformat(),endDate=(end-timedelta(hours=3)).isoformat(),source='Watch'),
              dict(type='steps',value=100,startDate=(end-timedelta(hours=2)).isoformat(),endDate=(end-timedelta(hours=1)).isoformat(),source='Watch')]
        out=self.parse_json(rows)['metrics'][0]
        self.assertEqual(out['value'],300)
        self.assertEqual(out['aggregation'],'single_source_daily_sum')

    def test_invalid_files_return_typed_errors(self):
        for raw in (b'', b'{"records":1}', b'123', b'not,a,health,file', b'[1,2]', b'\xff', b'PKbroken', b'{', b'<?xml version="1.0"?><HealthData><Record'):
            with self.subTest(raw=raw):
                self.expect_error(raw)

    def test_entity_declarations_rejected(self):
        payload=self.xml([], '<!DOCTYPE HealthData [<!ENTITY x "a">]>')
        self.expect_error(payload, 'bad_xml')

    def test_large_zip_header_rejected(self):
        f=io.BytesIO()
        with zipfile.ZipFile(f,'w') as z:
            z.writestr('a/export.xml',b'<HealthData/>')
            z.writestr('b/export.xml',b'<HealthData/>')
        self.expect_error(f.getvalue(),'bad_health_zip')

    def test_truncated_xml_even_after_valid_record_not_accepted(self):
        raw=self.xml([self.record()])[:-10]
        self.expect_error(raw,'bad_xml')

    def test_per_metric_freshness_no_old_value_evidence(self):
        imported=self.parse_json([self.record(), self.record('sleep',7,ago=48), self.record('hrv_sdnn',52,ago=72)])
        view=device_view({'wearable':imported,'permissions':{'device':True}})
        self.assertEqual(view['mode'],'missing')
        self.assertEqual([r['key'] for r in view['evidenceMetrics']],['resting_hr'])
        self.assertEqual(sum(r['fresh'] for r in view['metrics']),1)
        self.assertFalse(view['live'])

    def test_revoked_data_hidden_and_bluetooth_capture_not_live(self):
        w=summarize([self.record('heart_rate',65)],'Bluetooth')
        view=device_view({'wearable':w,'permissions':{'device':True}})
        self.assertFalse(view['live'])
        self.assertTrue(view['lastCaptureBluetooth'])
        revoked=device_view({'wearable':w,'permissions':{'device':False}})
        self.assertEqual(revoked['metrics'],[])
        self.assertEqual(revoked['evidenceMetrics'],[])
        self.assertEqual(revoked['mode'],'disconnected')
        self.assertEqual(revoked['label'],'未授权读取')

    def test_complete_requires_three_current_measurement_types(self):
        w=self.parse_json([self.record(),self.record('sleep',7),self.record('hrv_sdnn',45)])
        self.assertEqual(device_view({'wearable':w,'permissions':{'device':True}})['mode'],'complete')
        old=self.parse_json([self.record(ago=60)])
        self.assertEqual(device_view({'wearable':old,'permissions':{'device':True}})['mode'],'stale')

    def test_future_saved_metric_is_not_fresh(self):
        w={'metrics':[dict(key='heart_rate',label='心率',value=70,unit='bpm',source='Watch',at=(self.now+timedelta(days=5)).isoformat())]}
        self.assertEqual(device_view({'wearable':w,'permissions':{'device':True}})['evidenceMetrics'],[])


if __name__=='__main__':
    unittest.main()
