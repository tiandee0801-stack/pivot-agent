# Pivot 换场｜V1.1.3 后端运行与恢复

## 手机入口与独立验收

在当前源码目录运行 `python3 ops/guest_access.py --local` 后，打开 [本机预览](http://127.0.0.1:8897/)。启动器将后台进程、入口和运行状态写到新版独立路径。本机运行状态存于 `~/Library/Application Support/Dee/Pivot-Demo-v113/access.json`，入口页位于工作区 `output/Pivot-Demo-V1.1.3-2026-11-20/00-打开Pivot手机MVP.html`。停止时，先核对状态文件中的 supervisor 对应本版本启动器，再向该进程发出终止信号。

需要手机访问时，可停止本机预览后运行 `python3 ops/guest_access.py` 开启临时 HTTPS。手机链接写入同一输出目录下的 `手机访问链接.txt`，Mac 和网络需在线。打开链接即进入基于 Cookie 的独立访客空间。

阶段验收使用独立数据库。在仓库根目录运行下面的命令，终端会打印访问地址。需验证本地模型时使用已经装好 MLX 的解释器，并去掉 `--rules-only`。

```sh
pivot_qa_dir="$(mktemp -d)"
PIVOT_CATALOG_PREVIEW=1 PIVOT_GUEST_MODE=1 PIVOT_PUBLIC_ORIGIN= \
  python3 server.py --port 0 --db "$pivot_qa_dir/workspace.sqlite3" --rules-only
```

当前服务的 Python 3.11 解释器位于工作区 `sites/stride-agent/local-ai/.venv/bin/python`。`GET /api/health` 返回服务版本及模型就绪状态。按本轮 `activeTask.interpretation.source` 区分真模型、规则降级和结构化快捷入口，并用 `requestId` 核对诊断。Qwen 提取意图，用户明确确认且事务成功后才生成计划保存回执。

## 数据、上传和恢复

- 业务记录保存在访客独立的 SQLite。媒体在各工作区的资产目录，位于 Web 静态根目录之外。浏览器清除 Cookie 或切换临时域名会失去原空间入口，需要保留记录时先导出。
- `intent_diagnostics` 按访客保存必要的解析来源、原因、时间和重试信息。诊断保留 30 天，原文及健康记录留在各自业务数据中。验收样本在隔离本机实例采集。
- 视频分析使用本地 FFmpeg、Good-GYM Python 运行时与 RTMPose/YOLOX 权重。服务验证真实编码、时长和大小，标准化视频时移除音轨。处理质量不足时返回空计数，用户可以核对和校正。
- 视频媒体以 7 天为清理阈值。访客空间初始化和后续访问时执行清理。主动删除媒体后，相关结构化反馈仍可回看。设备文件导入只提取所需字段，原始健康文件和媒体不在业务导出内。
- 网络中断后，先按原确认载荷请求 `POST /api/confirm/check`，或用已有操作号查询 `GET /api/operations/{id}`。明确未提交时才按原幂等键恢复，待核对时继续保留待核对。重启恢复持久化的计划、记录和回执，中断的视频任务会在工作区打开后标成可重试。
- 将测试、演示和日常体验放在不同目录。恢复演示数据会清空该访客空间中相应记录，确认后才能操作。

## 验证入口

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
python3 tests/smoke_video_http.py --guest --input /absolute/test-video.mp4 --report /absolute/test-summary.json
```

真实视频检查使用独立回环实例，覆盖上传、推理、回放、不同访客无法访问同一媒体、人工校正、查回执和删除。只保留汇总结果。请求、错误格式和操作详情见 [API 说明](MOBILE_API.md)。
