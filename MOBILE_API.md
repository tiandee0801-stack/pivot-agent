# Pivot 换场 API · V1.1.3

手机端 PWA 使用同源 JSON API。除回执、事件、上传和鉴权等独立接口外，写请求返回当前业务状态。状态包括 `plan`、`profile`、`permissions`、`device`、`alternatives`、`history`、`activeTask`、`sessions`、`videoJobs`、`weeklyGoal` 和能力摘要。

## 访客、鉴权与能力

- 手机端独立体验启用 `PIVOT_GUEST_MODE=1`。首访生成随机 `pivot_space` Cookie，按 Cookie 查找独立 SQLite 和媒体目录。Cookie 为 HttpOnly、SameSite=Lax，配置 HTTPS 时带 Secure，有效期为 7 天。Cookie 的有效期与数据库留存相互独立。
- 旧配对接口仅用于开启配对的兼容实例，配对码从后端环境读取。
- GET `/api/health` 返回 `{app:'pivot-agent',demoVersion:'1.1.3',model:{available,label},vision:{available,label},authRequired:boolean}`。其中模型状态描述服务就绪情况。
- GET `/api/auth`: `{authenticated:boolean,pairingRequired:boolean}`. Without pairing configured, loopback-only is authenticated.
- POST `/api/auth/pair` `{code}`: sets HttpOnly session cookie, returns `{authenticated:true}`. Wrong => 401; rate limiting =>429. Do not persist code client-side.
- POST `/api/auth/logout` `{}` clears cookie.
- 兼容配对模式下，未通过配对的业务请求返回 401，错误码为 `pair_required`。

## HTTP 错误

现行客户端的 JSON 请求、视频上传和健康文件上传带 `X-Pivot-Error-Format: structured`，错误响应结构为 `{"error":{"code":"…","message":"…"}}`。旧客户端省略该请求头仍收到 `{"code":"…","error":"…"}`。客户端解析两种格式，HTTP 状态和成功响应结构沿用原约定。文件读取的 416 响应按 Range 协议处理，视频任务查询成功时的 `job.error` 是任务状态字段。

## 计划、确认和操作回执
- GET `/api/state`: current state.
- POST `/api/tasks` `{input}` -> current state; creates/activates task.
- POST `/api/answer` `{id,text}` -> current state.
- 本轮解释结果随 `activeTask.interpretation` 返回 `{source,requestId}`。来源为 `model`（采用本地模型解析）、`fallback_rules`（自由文本转规则）或 `structured_rules`（主动使用结构化快捷入口）。刷新后从 `GET /api/state` 读取已保存的最近一次解析。历史任务可能缺少此字段。已有 `activeTask.mode` 保留供旧客户端兼容。后端诊断按访客保存，界面通过来源和请求标识展示本轮发生了什么。
- POST `/api/confirm` `{id,optionId,draftVersion,remind:false,idempotencyKey,availabilityConfirmed?:true}` -> current state. Client must generate one UUID per logical submission and reuse it on transport retry. `operation` contains `{operationId,idempotencyKey,status:'succeeded',taskId,planVersion}`.
- POST `/api/confirm/check` 使用原确认载荷 -> `{operation}`。已成功返回原回执。条件仍有效且服务端确认从未提交时，返回 `{status:'not_submitted',idempotencyKey,taskId}`；随后可用原幂等键及相同载荷继续。其他查单失败保持待核对。
- GET `/api/operations/{key-or-operationId}` -> `{operation}`。保存成功后操作号和原键解析到同一条回执。普通 404 没有证实未提交，不能据此再次提交。
- POST `/api/keep` `{id}`, `/api/cancel` `{id}` -> state.
- POST `/api/settings` `{profile?:{goal,sport,preferredTime,constraint},permissions?:{device,save,reminder},weeklyGoal?:integer1to7}` -> state.
- POST `/api/plan` `{expectedVersion,title,date:'YYYY-MM-DD',time:'HH:MM',minutes:1..240}` -> state. 409 on stale version; marks source user-confirmed.
- POST `/api/alternatives` `{items:[{id?,title,minutes:1..240}]}` -> state. At most 8 user-confirmed alternatives; can be empty. Global context version invalidates old drafts.
- Existing POST `/api/feedback` remains backward compatible but new mobile should use sessions below.

## 篮球体能训练库

- 本机预览的状态响应含 `trainingCatalog`，提供版本、动作库、场景模板和真实的待审核状态。每个动作有稳定编号与计量类型。视频白名单仍由视频服务提供。
- `POST /api/plan` 接受结构化 `actions`，可附 `templateId`。每项用 `exerciseId` 标识，可带 `quantity`、`sets` 和 `restSeconds`。原版本检查继续生效。
- `POST /api/sessions` 可提交 `exerciseEntries`。按所选动作提交组次／负重、秒、米或回合及合法的附加字段。服务端保留动作名称和计量类型，历史可直接回读。
- 结构化调整仍使用 `/api/tasks`、`/api/answer`、`/api/confirm`。候选包含结构化动作和变化说明。写入后的动作清单与选中的候选一致，沿用回执及幂等语义。

### 进行中训练

- 本机预览状态增加 `activeWorkout`，包含一份按原计划版本冻结的动作清单、动作完成状态和训练修订号。没有进行中训练时为 `null`。
- `POST /api/workout/start` 接收 `planVersion`。已存在同一访客的进行中草稿时返回该草稿。
- `POST /api/workout/action` 接收 `id`、`expectedRevision`、`index`、`status` 及可选 `entry` 或 `reason`。状态支持 `pending`、`completed`、`skipped`。完成时按动作校验实做单位。
- `POST /api/workout/finish` 接收 `id`、`expectedRevision`、`minutes`、`feeling`、`idempotencyKey` 及可选不适状态与备注。至少一项实做才可保存。响应附 `savedSessionId` 和回执。历史额外保留原计划版本与逐项结果。
- `POST /api/workout/discard` 接收 `id` 和 `expectedRevision`。界面先向用户确认，再取消本次草稿。

## 穿戴数据文件

- POST `/api/wearable/import` 上传 Apple 健康 XML/ZIP 或规范 CSV/JSON，最大 100 MiB。成功返回当前状态中的设备数据，包含来源、采集时间及可用性。服务端从文件内容解析并校验字段和解压边界。
- POST `/api/wearable/disconnect` 停止在后续任务引用穿戴记录。核心流程可继续使用本人确认的感受。

## 视频观察

支持弯举、深蹲、俯卧撑、侧平举与肩上推举，动作分别使用独立观察规则。质量证明按样片和动作单独记录。上传或拍摄完成后分析。
- POST `/api/video?side=left|right&exercise=bicep_curl|squat|pushup|lateral_raise|overhead_press` raw video bytes, Content-Type video/* or application/octet-stream, **0.3–45 sec / <=60 MiB / max4K**. `{jobId,status:'queued'}` 202. Upload can use XHR for real progress. Reject large/invalid files. One analysis at a time (429).
- GET `/api/jobs/{jobId}` `{jobId,createdAt,status:'queued|running|done|error',progress:0..100,error,result?}`.
- result `{count:number|null,quality:'usable|insufficient',side,duration,validRatio,summary,frames:[{t,points:[[x,y,score]×17],angle:number|null,count,valid}],events,sourceUrl,width,height,limitations,mode}`. x/y normalized independently for drawing; retain actual video aspect ratio. Quality insufficient must show unknown total, not interim frames count.
- GET `/media/{jobId}.mp4` normalized silent MP4, supports Range. 由服务端校验访客空间或已启用的兼容配对会话。
- DELETE `/api/jobs/{jobId}` -> state. Running job returns409. Linked historical session keeps structured observation but media link removed; no broken media request.
- Server enforces actual decoding/model inference and bounded subprocess. Does not return preset counts.

## Actual training and correction
- POST `/api/sessions` `{taskId?:string,videoJobId?:string,completion:'completed|partial|not_done',minutes:integer0..240,feeling:'合适|偏累|偏轻松|不合适',discomfort:boolean,note?:string<=500,correctedCount?:integer0..1000|null,correctionReason?:string<=200,performedAt?:'YYYY-MM-DD',idempotencyKey:string}` -> current state plus `savedSessionId`.
- completed or partial requires minutes>0; not_done requires0. Linked task must be saved/partial; standalone record allowed. Video must be done, usable/insufficient both allowed. If correctedCount differs from model count, require correctionReason. If absent use observed count; if insufficient no correction supplied remains null, never zero.
- POST `/api/sessions/update` same fields + `{id,expectedRevision}` -> state. Cannot switch task/video association. Conflict409. Original model result preserved. Version increments; old adjustment drafts invalidated.
- DELETE `/api/sessions/{id}` -> state; deletes this structured record, not plan history. Old drafts invalidated.
- session `{id,revision,createdAt,updatedAt,performedAt,taskId,videoJobId,completion,minutes,feeling,discomfort,note,observation:{originalCount,confirmedCount,correctionReason,quality,validRatio,side,sourceUrl?,modelVersion?,ruleVersion?}|null}`.
- New adjustment `evidence` includes latest actual session and confirmed observation with source, time, revision. Video does not auto-prescribe/increase load.

## History, export and nonfunctional
- GET `/api/export` downloads JSON of profile/plan/tasks/sessions/observations, no raw media.
- POST `/api/reset` remains destructive demo reset; UI requires explicit confirmation; returns409 if video running. Pairing unchanged. Never automatically reset.
- 默认绑定 `127.0.0.1`。手机 App 体验通过配置的 HTTPS 入口使用独立访客空间。Service Worker 只缓存静态界面，离线保留输入等待联网确认。

## Implemented retention and observation metadata
- Original/normalized uploaded media expires 7 days after job creation. Cleanup runs when the workspace media manager starts and during subsequent requests (at most once per 10 minutes for those requests). Structured observation/history remain, `mediaDeleted:true` is set and `sourceUrl` removed.
- `GET /api/state` returns job result summaries without `frames`/`events`; retrieve `/api/jobs/{id}` for replay frames.
- Observation also carries `cycleDurationSeconds:number|null` (median interval of adjacent complete cycles in continuous usable footage), `modelVersion`, `ruleVersion`; no clinical score or automated load change.
- Drafts expire after 30 minutes. Refresh/answer regenerates against latest plan/context. A prior successful idempotent confirmation remains queryable after expiry.

- Reschedule candidates have `requiresAvailabilityConfirmation:true`; show their reason and require an explicit free-time confirmation checkbox. Confirm payload must set `availabilityConfirmed:true` for that candidate. Server never claims access to a real calendar. Explicit requested dates/times are preserved.

## Minimal product events
- POST `/api/events` `{eventId,event:'draft_view',taskId,draftVersion}` -> `{event}`. Current task version is checked; same ID and payload are idempotent, changed payload gives409. Only this frontend event is accepted; clients cannot forge server outcomes.
- Server records `adjust_start`, `clarify_answer`, `plan_confirm`, `operation_finished`, `training_recorded`, `video_submitted`, `video_finished`, `observation_confirmed`. Records contain allowlisted identifiers, version/status, duration and correction flags, not user text, health notes, video bytes, pairing codes or cookies.
- GET `/api/export` includes `events` for later analysis. These are measurements, not precomputed product success metrics. A failed confirmation records a safe rejected/conflict outcome after business rollback; replaying a successful idempotent operation does not duplicate its success event.
- Fresh profiles return `profileConfirmed:false`, new plans `planIsExample:true`; set onboarding labels. New devices are off by default. No sample basketball event enters adjustment evidence. Existing user DBs are not auto-reset, including old untouched demo dates.
