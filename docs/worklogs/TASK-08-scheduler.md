# TASK-08 可恢复定时调度闭环

- 更新时间：2026-07-14（Asia/Shanghai）
- 状态：已完成
- 负责人/窗口：Codex TASK-08 窗口
- 依赖任务：TASK-07（已完成并通过可靠增量与幂等交付验收）
- 声明文件范围：
  - `backend/app/services/scheduler.py`
  - `backend/app/services/scheduler_worker.py`
  - `backend/app/services/task_runner.py`
  - `backend/app/storage/**`
  - `backend/app/api/tasks.py`
  - `backend/app/api/subscriptions.py`
  - `backend/app/main.py`
  - `backend/app/schemas/tender.py`
  - `backend/app/schemas/task.py`
  - `backend/requirements.txt`
  - `backend/tests/test_scheduler.py`
  - `backend/tests/test_subscriptions_api.py`
  - 与调度集成直接相关的测试
  - `docs/worklogs/TASK-08-scheduler.md`
  - `docs/WORK_PLAN.md`（最终验收后）
- 明确不修改：
  - 前端
  - 真实数据源解析器
  - 意图解析规则

## 阶段记录

### 2026-07-14 — 阶段 1：上下文、契约与基线

#### 已完成

- 阅读 TASK-07 日志、调度器原型、Publisher、存储层、任务 API、应用入口、任务/招标 schema 和工作流图。
- 确认共享执行接缝为 `TaskRunner`；手工 API 与调度 worker 都必须通过它调用现有 `WORKFLOW`。
- 确认调度测试的公开接缝为订阅 HTTP API、持久化原子 claim/租约、worker 到期执行和 TASK-07 交付结果；时间统一通过 fake clock 注入。
- 确认 `.git` 目录为空且当前不是有效 Git 仓库；不初始化或修复 Git 元数据。

#### 改动文件

- `docs/worklogs/TASK-08-scheduler.md`：创建独立任务日志并声明范围。

#### 验证结果

- 命令/检查：使用仓库既有 `.venv` 依赖配合 Codex Python 运行 `python -m unittest discover -s tests -v`。
- 结果：通过
- 证据：TASK-08 改动前后端基线 62/62 通过；无代码失败。

#### 阻塞

- 无。

#### 下一步

- 运行后端测试基线；按垂直切片补充 fake clock 调度、租约与 API 红灯测试。

### 2026-07-14 — 阶段 2：调度状态机、共享运行器与 API

#### 已完成

- 实现 IANA 时区的 once/daily/weekly 下一次时间计算；结构化调用统一返回 UTC 时刻，并兼容工作流旧式计划展示调用。
- 新增持久化 `subscriptions` 与 `schedule_runs`；任务、租约、重试、运行 attempt 和错误均写入 SQLite。
- 使用 `BEGIN IMMEDIATE` 与条件更新原子 claim；同一任务租约存续期内不能被第二 worker 领取，运行中通过心跳续租。
- worker 崩溃后，租约到期可由新 worker 接管，旧 attempt 记录为 `lease_expired`。
- 实现有限重试、指数退避、once 成功完成、daily/weekly 成功重排、暂停/恢复/取消。
- 提取共享 `TaskRunner`；手工 API 与 scheduler worker 均经同一入口调用现有 LangGraph 工作流。
- 新增订阅创建、列表、详情、暂停、恢复、取消 API；参数为明确结构化调度字段，未修改自然语言意图规则。
- 接入 FastAPI lifespan；服务启动立即扫描持久化到期任务，关闭时停止 worker。
- 真实工作流集成测试证明：DOCX 失败不会推进 TASK-07 快照/水位线；退避后重试成功；下一周期相同事件不新增 delivery 或 DOCX。

#### 改动文件

- `backend/app/services/scheduler.py`：时区计算与订阅服务。
- `backend/app/services/scheduler_worker.py`：持久化 worker、租约心跳、成功/失败状态机。
- `backend/app/services/task_runner.py`：手工与定时共用工作流入口。
- `backend/app/storage/database.py`：订阅和调度运行表。
- `backend/app/storage/repository.py`：订阅 CRUD、原子 claim、租约和 attempt 状态提交。
- `backend/app/api/tasks.py`：改用共享 TaskRunner。
- `backend/app/api/subscriptions.py`：结构化订阅 API。
- `backend/app/main.py`：订阅路由与 lifespan worker。
- `backend/app/schemas/task.py`：订阅请求/响应契约和交叉字段校验。
- `backend/tests/test_scheduler.py`：fake clock、持久化、并发、恢复、重试和幂等测试。
- `backend/tests/test_subscriptions_api.py`：API 全流程测试。

#### 验证结果

- 命令/检查：`python -m unittest tests.test_scheduler -v`
- 结果：通过
- 证据：最终 16/16 通过，覆盖时区/DST、重启恢复、原子 claim、租约丢失取消、有限重试、暂停恢复、失败安全和幂等交付。
- 命令/检查：`python -m unittest tests.test_subscriptions_api tests.test_api tests.test_scheduler -v`
- 结果：通过
- 证据：当时 12/12 通过；最终完整回归见阶段 3。

#### 阻塞

- 无。

#### 下一步

- 运行完整后端回归和编译检查；执行 1—2 分钟真实服务 once 任务、重启不重复及数据库验收。

### 2026-07-14 — 阶段 3：真实重启验收、审查与收口

#### 已完成

- 以独立临时 SQLite/报告目录启动真实 FastAPI 服务，未替换生产来源、未注入测试 fixture；通过 `POST /api/subscriptions` 创建约 75 秒后到期的 once 任务。
- 任务在 `2026-07-14T07:02:16Z` 到期，`07:02:17Z` 完成；自动生成 workflow run、generated delivery 和有效 DOCX。
- 停止服务后使用同一数据库重启；等待 5 秒再次查询，subscription 仍为 `completed`，workflow run 数和 DOCX 数均保持 1，未重复执行。
- 回读验收 DOCX：37,052 字节，可由 `python-docx` 打开，包含 2 个段落和 1 个表格。
- 数据库验收：subscription 租约已清空；schedule run 为 `succeeded`；workflow run 为 `completed`；delivery 为 `generated`；本轮真实来源返回无可提交项目快照，保存 1 条成功来源水位线。
- 失败恢复集成验收：首次 DOCX 失败后快照和水位线均为 0；退避重试成功后提交 1 个项目快照、2 条成功来源水位线、1 条 generated delivery 和 1 个 DOCX。
- Standards/Spec 双轴只读审查完成。修复续租失败仍继续工作流的重叠风险，并补全 IANA DST 空档/重复时间策略；其余为非阻塞维护性建议。

#### 验证结果

- 命令/检查：`python -m unittest discover -s tests -v`
- 结果：通过
- 证据：80/80 通过。
- 命令/检查：`python -m compileall -q app tests`
- 结果：通过
- 证据：应用与测试文件无语法/字节码编译错误。
- 命令/检查：真实服务 once → 自动运行 → 停止 → 同库重启 → 查询数据库与回读 DOCX。
- 结果：通过
- 证据：task `b7d950a0-d7a5-4950-89d8-3592dc547af9`；重启前后 run=1、DOCX=1；状态 `completed`。
- 命令/检查：改动范围敏感词扫描。
- 结果：通过
- 证据：无账号、Cookie、Token、API Key 或 Secret 值命中；仅任务日志安全检查文字命中。

#### 明确未完成项

- 无 TASK-08 功能或验收项未完成。
- `.git` 目录为空，当前不是有效 Git 仓库，因此无法按实现流程创建提交；未越权初始化或修复 Git 元数据。

#### 下一步

- TASK-09 可在本结构化订阅 API 之上实现自然语言“每天 9 点”识别；TASK-08 不包含该规则。

## 安全检查

- [x] 未将账号写入仓库或日志。
- [x] 未将 Cookie 写入仓库或日志。
- [x] 未将 Token 写入仓库或日志。
- [x] 未将 API Key 写入仓库或日志。
- [x] 仅记录了无敏感值的环境变量名或配置状态。

## 完成验收

- [x] `docs/WORK_PLAN.md` 中该任务的验收条件全部满足。
- [x] 所有改动都在声明文件范围内。
- [x] 改动文件和验证结果已记录。
- [x] 已完成安全检查。
- [x] 已通知协调窗口更新总计划状态。

## 最终状态

- 状态：TASK-08 已完成并通过自动测试、失败恢复和真实服务重启验收。
- 更新时间：2026-07-14（Asia/Shanghai）
