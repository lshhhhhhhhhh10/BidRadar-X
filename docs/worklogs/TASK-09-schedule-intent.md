# TASK-09 自然语言调度意图执行日志

- 更新时间：2026-07-14（Asia/Shanghai）
- 状态：已完成
- 负责人/窗口：Codex TASK-09 执行窗口
- 依赖任务：TASK-08（已完成）
- 声明文件范围：
  - `backend/app/services/schedule_intent.py`
  - `backend/app/schemas/task.py`
  - `backend/app/api/subscriptions.py`
  - `backend/tests/test_schedule_intent.py`
  - `backend/tests/test_subscriptions_api.py`
  - `docs/worklogs/TASK-09-schedule-intent.md`
  - `docs/WORK_PLAN.md`（仅最终验收状态）
- 明确不修改：TASK-08 scheduler/worker/task runner、storage、workflow、sources、publisher、前端和 DOCX 逻辑。

## 2026-07-14 15:33:48 +08:00 — 启动与基线核对

- 当前目标：确认 TASK-08 本地恢复基线、工作区状态与 TDD 执行边界。
- 修改文件范围：本阶段仅新增本日志；生产代码尚未修改。
- 执行命令：
  - `git status --short --branch`
  - `git log -1 --decorate --oneline`
  - `Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'`
- 结果：当前分支为 `recovery/task-08-baseline`；HEAD 为 `169698c (tag: local-task-08-baseline)`；`git status` 仅输出分支行，工作区干净，没有需要绕开的未提交改动。
- 红灯或失败原因：尚未开始新增测试；无测试红灯记录。
- 修复内容：无。
- 下一步：阅读任务指定文档与代码，确认解释器、测试环境和现有订阅服务接口；随后运行 80 个后端基线测试。
- 明确未完成项：解析器、自然语言 API、TDD 红灯、自动测试、HTTP 黑盒、Git 提交均未完成。

## 2026-07-14 15:35:36 +08:00 — 指定文件审阅与后端基线

- 当前目标：确认 TASK-08 调度链路的复用接缝，并在新增测试前验证 80 项基线。
- 修改文件范围：仍仅有本日志；已确认后续预计只改 `backend/app/services/schedule_intent.py`、`backend/app/schemas/task.py`、`backend/app/api/subscriptions.py`、对应测试与直接相关文档。
- 执行命令：
  - 按任务清单逐一读取 PROJECT_CONTEXT、WORK_PLAN、DATA_CONTRACT、TASK-07/TASK-08 日志、task/tender schema、subscriptions API、scheduler/worker/task runner、requirement/task_plan 节点及 scheduler/subscriptions 测试。
  - 首次尝试：`$env:PYTHONPATH='.'; python -m unittest discover -s tests -p "test_*.py" -v`。
  - 第二次尝试：`$env:PYTHONPATH='.'; .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v`。
  - 有效基线：`$env:PYTHONPATH='.;.venv\Lib\site-packages'; C:\Users\lisihan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest discover -s tests -p "test_*.py" -v`。
- 结果：有效基线运行 80 项，80 通过、0 失败、0 跳过，用时 6.743 秒。解释器为 CPython 3.12.13；`PYTHONPATH=.;.venv\Lib\site-packages`。
- 红灯或失败原因：前两次命令没有进入测试：PATH 中没有 `python`；仓库 `.venv` 的启动器仍指向旧用户 `C:\Users\DzSexton\...`，报 `No Python at ...`。这两次不是 TDD 红灯。基线唯一警告为 StarletteDeprecationWarning：`fastapi.testclient` 使用 `httpx` 的兼容方式已弃用，建议未来安装 `httpx2`；属于既有依赖警告。
- 修复内容：不改动环境或依赖，改用当前 Codex Python，并把仓库 `.venv\Lib\site-packages` 加入 `PYTHONPATH`。
- 下一步：新增解析器公开行为的第一条测试，在生产模块不存在时立即运行并记录真实失败；然后按垂直切片实现。
- 明确未完成项：真实 TDD 红灯、解析器、自然语言 API、完整回归、HTTP 黑盒、安全扫描和 Git 提交均未完成。

## 2026-07-14 15:37:27 +08:00 — TDD 第一条真实红灯

- 当前目标：先以解析器公开接口锁定“每天上午 9 点 + 业务查询清理”的用户行为。
- 修改文件范围：新增 `backend/tests/test_schedule_intent.py`；生产实现仍不存在。
- 执行命令：`$env:PYTHONPATH='.;.venv\Lib\site-packages'; C:\Users\lisihan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest tests.test_schedule_intent.ScheduleIntentParserTest.test_daily_morning_time_is_separated_from_the_search_query -v`。
- 结果：真实红灯，运行 1 项，0 通过、0 失败断言、1 个 import error。
- 红灯或失败原因：测试名 `tests.test_schedule_intent.ScheduleIntentParserTest.test_daily_morning_time_is_separated_from_the_search_query`；关键错误原样为 `ModuleNotFoundError: No module named 'app.services.schedule_intent'`。
- 修复内容：尚未修复；该失败证明测试先于生产模块出现。
- 下一步：只实现使第一条 daily 测试通过的最小解析器切片，再逐条加入 weekly、once 与错误行为测试。
- 明确未完成项：除第一条红灯证据外，所有生产实现、后续测试、HTTP 黑盒和提交仍未完成。

## 2026-07-14 15:45:04 +08:00 — 解析器与 API 垂直切片

- 当前目标：完成规则解析器的成功/拒绝行为，并通过真实 FastAPI 测试接入 TASK-08 订阅服务。
- 修改文件范围：新增 `backend/app/services/schedule_intent.py`、`backend/tests/test_schedule_intent.py`；修改 `backend/app/schemas/task.py`、`backend/app/api/subscriptions.py`、`backend/tests/test_subscriptions_api.py`。
- 执行命令：逐条运行新解析器测试；随后运行 `... -m unittest tests.test_schedule_intent -v` 与 `... -m unittest tests.test_subscriptions_api -v`，解释器/PYTHONPATH 与基线相同。
- 结果：解析器 14/14 通过；subscriptions API 6/6 通过。新 API 测试已证明 daily/weekly/once 创建、临时 SQLite 持久化、同库服务重启可读、原结构化入口未回归，以及 5 类失败不创建订阅。
- 红灯或失败原因：除首次模块不存在红灯外，后续真实红灯包括 weekly 初始不支持（`ValueError: schedule expression is not supported`）、绝对日期/明天/24 小时制初始不支持，以及 API 路由初始返回 `405 Method Not Allowed`。拒绝组首次运行有 5 项失败，分别证明旧切片会静默接受冲突频率、多时间、多星期、过去时间和空业务查询。
- 修复内容：实现纯规则 `ScheduleIntentParser.parse(query, now=..., timezone=...)`；固定时钟由调用者注入；支持 daily/weekly/明天/明确日期、12/24 小时时间、中文标点与查询清理；稳定错误码为 `schedule_not_found`、`schedule_ambiguous`、`schedule_invalid`、`schedule_in_past`、`empty_search_query`。新增 `POST /api/subscriptions/from-query`，解析后构造现有 `SubscriptionCreateRequest` 并调用同一 `SubscriptionService`，没有第二套调度器或置信度字段。
- 下一步：补强边界测试并检查 diff；运行 TASK-09 定向、subscriptions、scheduler、完整回归、编译和扫描；之后启动独立临时 SQLite 的真实 uvicorn HTTP 黑盒。
- 明确未完成项：完整后端回归、编译/安全扫描、真实进程 HTTP 黑盒、工作计划最终更新、代码审查与本地提交尚未完成。

## 2026-07-14 15:50:14 +08:00 — 自动验收与真实 HTTP 黑盒

- 当前目标：完成全部自动门禁，并用独立真实 uvicorn 进程、临时 SQLite 和真实 HTTP 请求验证成功/失败路径。
- 修改文件范围：生产/正式测试文件不再扩张；临时创建 `backend/tests/_task09_blackbox_harness.py` 仅作为 HTTP 验收驱动，验收后已删除，未作为 fixture 或待提交文件保留。
- 执行命令：
  - `... -m unittest tests.test_schedule_intent tests.test_subscriptions_api tests.test_scheduler -v`
  - `... -m unittest discover -s tests -p "test_*.py" -v`
  - `... -m compileall -q app tests`
  - 改动范围敏感赋值模式扫描；生产改动 `example.local`/“模拟成功”扫描。
  - 首次黑盒启动使用 `Start-Process`；第二次成功启动命令为 `C:\Users\lisihan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 18373`，后台 Job 内设置 `TENDER_DATA_DIR` 和既定 `PYTHONPATH`。
- 结果：定向测试 39/39 通过；完整后端 101/101 通过、0 失败、0 跳过，用时 5.420 秒；编译通过；敏感赋值和生产模拟成功扫描均无命中。唯一警告为既有 `StarletteDeprecationWarning`（FastAPI TestClient 使用已弃用的 httpx 兼容方式）；另有既有 CCGP 测试日志“Skipping unparseable ... title”，不是 unittest skip。
- 红灯或失败原因：首次 `Start-Process` 未启动服务，Windows 报 `ArgumentException`：环境字典同时出现 `Path/PATH`；PID 为空并超时。未发出产品请求，不计产品黑盒失败。改用 PowerShell `Start-Job` 后成功。
- 修复内容：只调整验收启动方式，不修改产品代码。成功黑盒使用端口 `18373`、数据库 `C:\Users\lisihan\AppData\Local\Temp\bidradar-task09-c890d7290b774b5095fdbdb2e9b1a165\app.db`。
- 黑盒成功路径：
  - A `每天上午9点查询安徽省服务器采购项目` → HTTP 201，daily/09:00/Asia/Shanghai，业务查询为 `查询安徽省服务器采购项目`，`next_run_at=2026-07-15T01:00:00Z`。
  - B `每周一下午3点查询上海市计算设备采购` → HTTP 201，weekly/monday/15:00，`next_run_at=2026-07-20T07:00:00Z`。
  - C `2026-07-20 上午9点查询安徽服务器采购` → HTTP 201，once，解析 `run_at=2026-07-20T09:00:00+08:00`；数据库 UTC `run_at=next_run_at=2026-07-20T01:00:00+00:00`、status=active，证明 TASK-08 worker 可按现有到期条件识别。
- 黑盒失败路径：缺时间和 25 点均 HTTP 422/`schedule_invalid`；多星期 HTTP 422/`schedule_ambiguous`；过去日期 HTTP 422/`schedule_in_past`。错误响应均不含堆栈、数据库路径或环境变量。
- 数据库/副作用：成功请求后 subscriptions=3；四个失败请求后仍为 3；schedule_runs=0、project_snapshots=0、source_watermarks=0、deliveries=0、DOCX=0。因此失败请求没有错误推进快照、水位线或 DOCX。
- 服务停止：`SERVICE_STOPPED=True`；后台 Job 已停止并移除，没有遗留监听进程。
- 下一步：执行双轴代码审查，处理发现；最终更新 WORK_PLAN 与本日志，复跑必要检查并创建单一本地提交。
- 明确未完成项：代码审查、WORK_PLAN 最终说明、Git 提交和提交后状态核对尚未完成；没有真实等待未来时间触发这三条订阅。

## 2026-07-14 15:58:38 +08:00 — 双轴审查修复与最终收口

- 当前目标：处理 Standards/Spec 双轴只读审查发现，完成最终回归、文档状态和单一 TASK-09 本地提交。
- 修改文件范围：仍严格限定于声明的 7 个文件；未修改 scheduler、worker、storage、workflow、sources、publisher、前端或 DOCX 逻辑。
- 执行命令：
  - 固定点/审查：`git diff 169698c...HEAD`、`git log 169698c..HEAD --oneline`；两个隔离只读审查分别检查 Standards 与本任务规格。
  - 审查回归红灯：`... -m unittest tests.test_schedule_intent.ScheduleIntentParserTest.test_half_hour_is_consumed_instead_of_leaking_into_the_search_query tests.test_subscriptions_api.SubscriptionsApiTest.test_invalid_natural_language_requests_do_not_create_subscriptions -v`。
  - 最终定向：`... -m unittest tests.test_schedule_intent tests.test_subscriptions_api tests.test_scheduler -v`。
  - 最终完整：`... -m unittest discover -s tests -p "test_*.py" -v`。
  - 最终编译：`... -m compileall -q app tests`；敏感信息、TASK-09 生产 diff 模拟成功、`git diff --check` 扫描。
- 红灯或失败原因：审查回归首次真实运行 2 项均未通过：`9点半` 得到 `09:00`（断言失败），空 query 被 Pydantic 返回 list 型通用 422（测试读取 `detail.code` 时 `TypeError`）。
- 修复内容：时间正则完整消费“半”并转换为 30 分钟；自然语言请求允许空/单字符进入解析器，由统一 `ScheduleIntentError` 返回 `schedule_not_found`；补齐负责人/窗口和文件范围；复用 `Frequency`/`WeeklyDay`；抽取结构化请求到 SubscriptionService 的单一适配函数，消除重复转发。
- 审查结果：Standards 原 4 项（2 项日志硬规则、2 项判断性代码味道）全部处理；Spec 原 3 项中 2 个行为缺口已修复，第 3 项日志/Git 状态在本阶段同步。未发现第二套调度器、越界生产修改或范围扩张。
- 最终结果：定向 40/40 通过；完整后端 102/102 通过、0 失败、0 跳过，用时 5.324 秒；编译通过。唯一警告仍为既有 `StarletteDeprecationWarning`；CCGP “Skipping unparseable ... title”是既有测试日志，不是 unittest skip。
- 扫描结果：TASK-09 生产 diff 无 `example.local`/模拟成功命中；全范围高置信凭据扫描无命中。全 `backend/app` 另有 6 个既有 `example.local` 命中，位于未修改的 `sources/public_platform.py`、`commercial_platform.py`、`enterprise_portal.py`，不是 TASK-09 新增，且本任务按边界未改来源。
- Git：已创建初始本地提交 `93f8da7`，审查修复与本日志将 amend 到同一提交；不执行 push，最终 hash 以完成回执为准。
- 明确未完成项：网页端未接入；不支持“下个月第一个工作日”等复杂日历表达和无明确时间的默认；没有用户确认歧义的交互流程；未使用大模型；未真实等待未来时刻触发新建订阅；未推送 GitHub；黑盒使用独立临时 SQLite，未写生产数据库。
- 下一步：TASK-09 无剩余修复项。关键路径唯一下一任务为 TASK-10：修复并接通“首页运行任务 → 项目列表 → 项目详情 → DOCX 下载/历史记录”的真实前后端产品链路。

## 最终状态

- TASK-09 已完成：实现、TDD 红灯、自动回归、真实 HTTP 成功/失败黑盒、双轴审查、扫描、计划状态和本地 Git 收口均已通过。
- 更新时间：2026-07-14 15:58:38 +08:00。
