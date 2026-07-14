# F02 可迁移的数据模型与溯源字段

- 更新时间：2026-07-14（Asia/Shanghai）
- 状态：已完成
- 负责人/窗口：Codex F02 工程师（recovery/task-08-baseline）
- 依赖任务：F01（已完成）
- 起始 HEAD：`eaafca6b9f36fd787dbbdd771a04ecaa90daf6c3`
- 声明文件范围：
  - `backend/app/storage/database.py`
  - `backend/app/storage/models.py`
  - `backend/app/storage/repository.py`
  - `backend/app/storage/migrations/`（拟新建的唯一正式迁移目录）
  - `backend/tests/test_storage_migrations.py`（拟新增的 F02 独立测试）
  - `docs/worklogs/F02-migratable-storage.md`
  - `docs/WORK_PLAN.md`（仅在全部门禁通过后更新 F02 状态与唯一下一任务）
- 明确不修改：
  - `backend/app/sources/ccgp.py`、`backend/tests/test_ccgp_source.py`
  - `backend/app/schemas/tender.py`、现有来源/工作流/API/调度/报告文件
  - `docs/SOURCE_CCGP.md`、`docs/worklogs/F01-public-source-contract.md`
  - `app/**`、`lib/**`、前端、fixture、`docs/worklogs/TASK-10-product-chain.md`
  - R01、R02、N01 或其他关键路径任务文件
  - 账号、Cookie、Token、API Key 和用户文件

## 阶段记录

### 2026-07-14 — 阶段 0：认领、基线与范围核对

#### 已完成

- 完整阅读 F02 指定文档、现有存储实现、数据契约 schema，以及当前 SQLite 建表、快照、水位线、交付和运行记录相关测试。
- 确认分支为 `recovery/task-08-baseline`，HEAD 与指定起点一致，起始工作树无差异，`git diff --check` 通过。
- 确认没有现存 F02 日志；TASK-07/TASK-08 已完成，TASK-06 公开链路已收口且仅保留外部授权阻塞，不是进行中的存储修改窗口。
- 确认正式迁移目录尚不存在；声明只在 `backend/app/storage/migrations/` 建立版本化迁移，不修改来源、工作流或 API。
- WORK_PLAN 中 I02 虽为进行中但没有独立日志；为避免测试文件重叠，本任务只新增 `backend/tests/test_storage_migrations.py`。

#### 改动文件

- `docs/worklogs/F02-migratable-storage.md`：创建独立日志并声明精确文件边界与正式迁移目录。

#### 验证结果

- 命令/检查：`git status --short --branch`、`git diff`、`git diff --check`、`git rev-parse HEAD`、工作日志状态/范围扫描、迁移目录扫描。
- 结果：通过。
- 证据：目标分支和起始 HEAD 精确匹配；起始 diff 为空；没有 F02 日志或活动存储范围声明；正式迁移目录不存在。

#### 阻塞

- 无。

#### 下一步

- 先新增 F02 迁移测试形成红灯，再实现带事务边界的正式版本化迁移、原型库升级和持久化模型。

### 2026-07-14 19:10 — 阶段 1：测试优先与正式迁移实现

#### 已完成

- 先新增 `backend/tests/test_storage_migrations.py`，首轮按预期因 `MIGRATIONS`、`Migration` 和 `apply_migrations` 尚不存在而红灯。
- 将启动时内嵌 SQL 替换为正式迁移运行器：迁移按连续版本、名称和校验和验证，每个待执行版本使用独立 `BEGIN IMMEDIATE` 事务，迁移成功与版本记录原子提交。
- 新建唯一正式目录 `backend/app/storage/migrations/`：v1 固化并升级原型表，v2 建立正式溯源/审计模型，v3 事务性兼容旧工作流的直接调用入口。
- 建立项目、公告生命周期事件、来源发布、附件、字段证据、采集运行、采集运行-发布关联、项目快照版本、来源水位线版本、工作流运行版本、交付事件和变化版本表。
- 为项目/公告/发布/附件/证据/水位线使用稳定或确定性主键；建立项目—公告—来源发布、发布—附件/证据、采集运行—发布、水位线—采集运行、快照—项目和交付—事件/变化的外键及唯一约束。
- 新增存储边界模型 `AttachmentState`、`SourceResponseMetadata`、`SourceWatermark`，校验带时区时间、附件状态/哈希/大小和响应元数据不得携带凭据字段。
- 新增采集运行开始、成功原子提交和失败记录接口；成功提交在同一事务中写公告三层身份、附件、证据和复合水位线，失败不推进水位线。
- 将既有工作流运行、项目快照、交付状态和变化内容写入追加式历史表；重复内容按指纹幂等，当前视图继续兼容现有调用方。

#### 改动文件

- `backend/app/storage/database.py`：正式迁移运行器、版本/校验和/连续历史校验、事务边界和外键启用。
- `backend/app/storage/migrations/`：新增三版正式迁移，覆盖原型基线、溯源模型和旧工作流兼容升级。
- `backend/app/storage/models.py`：新增附件状态、有限响应元数据和复合水位线存储模型。
- `backend/app/storage/repository.py`：新增三层身份持久化、采集运行原子提交、复合水位线和快照/运行/交付审计历史。
- `backend/tests/test_storage_migrations.py`：新增 F02 独立迁移与持久化测试。

#### 验证结果

- 命令/检查：Codex Python `-B -m unittest tests.test_storage_migrations -v`。
- 结果：通过。
- 证据：整理测试继承关系后 F02 独立测试 7/7 通过；覆盖空库、原型库、重复迁移、失败回滚、约束、三层身份、附件/证据、复合水位线、时区/空值和审计幂等。
- 失败记录：仓库 `.venv/Scripts/python.exe` 指向另一用户已不存在的运行时；改用 Codex 自带 Python，并仅为测试进程加载仓库 `.venv/Lib/site-packages`，未安装依赖或改写环境。

#### 阻塞

- 无。

#### 下一步

- 运行增量、调度、产品 API 和完整后端回归；随后执行范围、敏感信息、禁用标记和 diff 门禁。

### 2026-07-14 19:20 — 阶段 2：兼容性修复与相关回归

#### 已完成

- 首轮相关回归发现旧增量测试可直接调用工作流图并绕过 `TaskRunner.create_task()`；v2 快照/水位线历史表对 `tasks` 的外键因此触发事务回滚。
- 保持已应用 v2 名称和校验和不变，新增 v3 正式迁移，在单一事务中重建快照/水位线历史表，仅移除对旧兼容入口不成立的 task 外键；项目、采集运行、公告、发布、附件和证据关系外键继续保留。
- 修复后 F02 测试、增量、调度、产品链路、API 和数据契约相关回归全部通过。

#### 改动文件

- `backend/app/storage/migrations/v0003_legacy_workflow_compatibility.py`：新增兼容迁移并保留既有历史数据。
- `backend/app/storage/migrations/__init__.py`：登记 v3 顺序与校验和。
- `backend/tests/test_storage_migrations.py`：将预期版本序列更新为 v1—v3。

#### 验证结果

- 命令/检查：`tests.test_storage_migrations`、`tests.test_incremental_delivery`、`tests.test_scheduler`、`tests.test_product_chain`、`tests.test_api`、`tests.test_tender_schema`。
- 结果：通过。
- 证据：F02 7/7；增量 15/15；合并相关回归 58/58 通过。
- 警告：测试输出包含既有 `StarletteDeprecationWarning`（Starlette TestClient 的 httpx 兼容层）；未由 F02 引入，不影响结果。
- 失败记录：第一次相关回归未加载 `.venv` site-packages，4 个模块在收集阶段缺少 `fastapi/langgraph`；设置测试进程 `PYTHONPATH` 后进入测试。进入测试后的首轮有 9 个失败、3 个错误，根因均为上述 task 外键兼容问题；v3 修复后全部通过。

#### 阻塞

- 无。

#### 下一步

- 执行完整后端测试、静态编译、声明范围、敏感信息、禁用标记和 `git diff --check` 门禁。

### 2026-07-14 20:05 — 阶段 3：契约补全、升级缺陷修复与双轴审查

#### 已完成

- Standards/Spec 首轮审查发现：完整 `TenderNotice` 契约没有版本化回读、来源发布身份约束未完整覆盖 URL/角色、旧兼容调用缺少稳定 task 外键目标、附件状态缺少追加历史，以及 canonical JSON/水位线参数重复。新增 v4 契约历史迁移、`task_identities`、完整 payload/附件版本表、统一指纹 helper 与 `WatermarkCursor` 后逐项修复。
- Spec 复审发现来源发布唯一约束仍会阻止同一来源身份使用不同 URL，且无显式附件状态的普通重采会把已下载状态降级。新增 v5 精确五字段身份迁移并保留现有附件状态，补充不同 URL 和附件非降级回归。
- 完整回归暴露 populated v4 数据库升级 v5 时，SQLite 会把历史子表外键跟随父表 rename，造成旧父表无法删除。v5 改为事务内 TEMP 备份历史、删除依赖子表、重建发布图和历史表、回填历史；新增 populated v4→v5 数据保留与 `foreign_key_check` 回归。
- 最终双轴复审又发现兼容查重遗漏 `notice_id`、v5 实现修订后 checksum 未更新以及一个乱码测试样本。查重现完整使用来源、公告 ID、URL、角色和原始内容指纹；更新 checksum 并新增旧 checksum 拒绝测试；测试样本改为可读文本。
- Standards 与 Spec 最终复审均 PASS，无剩余 hard/judgment finding、无 scope creep。

#### 改动文件

- `backend/app/storage/migrations/v0004_contract_history.py`：完整公告 payload 与附件状态历史、稳定 task 身份、快照/水位线外键恢复及发布图重建 helper。
- `backend/app/storage/migrations/v0005_source_publication_identity.py`：落实来源发布五字段唯一身份，并安全升级已有 v4 历史数据。
- `backend/app/storage/migrations/__init__.py`：按顺序登记 v4、v5 及不可变 checksum。
- `backend/app/storage/repository.py`：完整契约版本化读写、五字段发布身份、附件非降级、追加式运行/快照/交付历史与复合水位线。
- `backend/app/storage/models.py`：增加 `WatermarkCursor` 并集中校验复合水位线。
- `backend/tests/test_storage_migrations.py`：补充 v4→v5、checksum、五字段身份、附件演进、payload 回读和事务失败回归。

#### 验证结果

- F02 专项：`13/13` 通过。
- 完整后端：在工作区隔离且已清理的数据目录中 `125/125` 通过；未接触外部网络。
- 空库重复升级、原型库升级、populated v4→v5 升级、迁移失败回滚、版本/checksum 拒绝、主外键与唯一约束、三层身份、附件/证据、带时区/未知值、运行/快照/交付审计及失败不推进水位线均有自动测试覆盖。
- 范围、敏感信息、禁用标记、Python AST、临时产物和 `git diff --check` 扫描通过。
- 警告：`gitleaks`、`ruff`、`mypy` 在当前环境不可用；Git 仅提示 LF→CRLF；完整测试有既有 `StarletteDeprecationWarning`，并输出预期的不可解析 CCGP 固定样本跳过日志。
- 失败记录：一次完整回归发现 v4→v5 外键 rename 缺陷；修复并加入专项回归。更新 v5 checksum 后，未隔离的默认临时测试库因保留开发中旧 checksum 按设计被拒绝；随后全部验证均改用新建、结束后清理的隔离数据目录，最终全绿，未修改或删除该默认数据文件。

#### 阻塞

- 无。

#### 下一步

- 所有门禁通过后更新 `docs/WORK_PLAN.md`，将 F02 标为已完成并把唯一下一任务切换为 R01；随后创建单一本地提交，不 push。

### 2026-07-14 20:15 — 阶段 4：计划收口

#### 已完成

- 全部门禁和双轴审查通过后，才将 `docs/WORK_PLAN.md` 中 F02 更新为已完成。
- 最新计划的唯一下一任务已切换为 R01；本任务未实现或提前开启 R01、R02、N01。

#### 改动文件

- `docs/WORK_PLAN.md`：更新 F02 状态、F02 证据入口与唯一下一任务 R01。
- `docs/worklogs/F02-migratable-storage.md`：补齐最终实现、测试、扫描、审查、警告和失败记录。

#### 验证结果

- 结果：通过；提交前最终重复门禁已再次通过，待提交后状态核验。

#### 阻塞

- 无。

#### 下一步

- 创建唯一一个本地提交并验证相对起始 HEAD 仅新增一个提交；不 push。

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
