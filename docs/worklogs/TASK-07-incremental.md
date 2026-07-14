# TASK-07 可靠增量、来源水位线与幂等交付

- 更新时间：2026-07-14（Asia/Shanghai）
- 状态：已完成
- 负责人/窗口：Codex TASK-07 窗口
- 依赖任务：TASK-01 数据契约、TASK-06 真实链路集成
- 声明文件范围：
  - `backend/app/storage/**`
  - `backend/app/intelligence/change_detector.py`
  - `backend/app/workflow/nodes/change.py`
  - `backend/app/workflow/nodes/report.py`
  - `backend/app/workflow/nodes/feedback.py`
  - `backend/app/services/publisher.py`
  - `backend/app/schemas/tender.py`（仅契约必要时）
  - `backend/tests/test_incremental_delivery.py`
  - 与本任务直接相关的现有后端测试
  - `docs/worklogs/TASK-07-incremental.md`
  - `docs/WORK_PLAN.md`（仅最终验收后）
- 明确不修改：前端、数据源解析器、调度器、意图解析器

## 阶段记录

### 2026-07-14 — 阶段 1：上下文、基线与最小设计

#### 已完成

- 完整阅读 PROJECT_CONTEXT、DATA_CONTRACT、REPORT_FORMAT、TASK-06 日志、现有 storage、变化检测、change/report/feedback 节点、Publisher、Tender schema 和全部后端 Python 测试。
- 确认测试接缝为工作流公开结果与持久化公开状态，不测试私有辅助函数。
- 确认 `.git` 当前不可用：`git status --short` 返回 `fatal: not a git repository`；未初始化、删除或修复 Git 元数据。
- 确认 TASK-06 无需大幅改写。最小改动是在现有 `change → report → feedback` 链上分离候选计算、工件生成和事务提交。

#### 已确认问题

- `change` 当前在 DOCX 生成前覆盖 `project_snapshots`，报告失败会吞掉下一次应重试的变化。
- 原型快照只保存 RAG 的 `budget`、`deadline`、`purchaser`，没有完整公告、证据、生命周期和版本信息。
- 当前没有数据库 delivery 唯一约束；文件锁只能保护单机文件生成，不能作为交付事实来源。
- 无变化时 `Publisher` 会查找并返回历史完整报告，造成“本次新增内容”的歧义。
- 来源成功/失败没有独立持久化水位线语义；遗留 `.lock` 可等待 60 秒后永久失败。

#### 最小实现方案

1. 以可重复的 `CREATE TABLE IF NOT EXISTS` 和增量列迁移兼容已有原型库，保留旧表与旧行。
2. `change` 只读取已提交版本化快照并计算候选变化、候选快照、成功来源水位线及 delivery 指纹，不写数据库。
3. `report` 先通过数据库唯一约束争夺 delivery；仅拥有 pending 交付的运行生成和验证 DOCX，并把状态更新为 generated 或 failed。
4. `feedback` 仅在工件 generated 后，于一个 SQLite 事务中提交 delivery、项目/公告快照和成功来源水位线；报告失败不推进任何快照或水位线。
5. 无变化返回 `no_change`、`notice_count=0`、`filename=null`，历史报告仅作为独立字段。
6. lock/staging 使用有界陈旧判定和可恢复清理；数据库唯一约束是最终并发仲裁依据。

#### 下一步

- 新增 `backend/tests/test_incremental_delivery.py`，先覆盖任务要求的十类失败行为并记录红灯原因。

### 2026-07-14 — 阶段 2：红灯基线与可靠提交状态机

#### 红灯记录

- 现有后端基线在正确运行时下为 47/47 通过，但它把“第二次无变化返回旧完整报告”视为成功，不能证明 TASK-07 语义。
- 新增首个 TASK-07 失败测试后立即执行，实际红灯为 `KeyError: 'status'`：旧报告结果没有 `generated/no_change/failed` 状态，也没有数据库 delivery、版本化完整快照或来源水位线可断言。
- 静态核对其余目标行为的旧实现失败原因：change 提前写快照；Publisher 仅靠文件锁且返回历史报告；数据库没有 watermark/delivery/notice snapshot 表；旧锁固定等待后超时；旧表没有可重复列迁移。
- 后续测试按垂直切片逐个加入；底层状态机完成后新增切片立即通过，因此没有把它们虚报为“实际执行过的旧代码红灯”。

#### 已完成

- 新增可重复 SQLite 初始化：保留旧表/旧行，增量补充项目快照列，并创建 `source_watermarks`、`notice_snapshots`、`deliveries` 及唯一 delivery 指纹约束。
- change 节点只构建候选版本化快照、业务变化和成功来源水位线，不再提前写数据库。
- 变化比较规范化预算、日期、采购人格式；排除抓取时间、原始响应和镜像来源；公告生命周期新增作为 `notice_lifecycle` 实质变化。
- material change 保留前值、后值、证据 ID 和完整证据对象。
- Publisher 先争夺数据库 pending delivery；所有者生成并验证 DOCX，失败改为 failed；竞争者等待数据库 generated 事实并复用唯一工件。
- feedback 在单个 `BEGIN IMMEDIATE` 事务中把 delivery 改为 generated，同时提交项目/公告快照和成功来源水位线；no-change 只提交成功水位线；failed 不推进。
- no-change 当前结果为 `status=no_change`、`notice_count=0`、`filename=null`、`download_url=null`，历史工件放在独立 `historical_report` 字段。
- 过期 lock 与 staging 使用 5 分钟陈旧阈值清理；近期锁仍保持互斥，不会误删活跃生成。

#### 定向验证

- `python -m unittest tests.test_incremental_delivery -v`：10/10 通过。
- 覆盖首次全量、完全相同 no-change、新项目增量、字段/生命周期变化、非业务变化、DOCX 失败重试、部分来源失败、并发唯一交付、旧库迁移、遗留 lock/staging 恢复。

#### 下一步

- 执行完整后端回归，修订与新 no-change 契约直接冲突的既有测试，再做临时数据库三轮黑盒验收。

### 2026-07-14 — 阶段 3：完整回归与三轮临时库黑盒验收

#### 完整回归

- 旧 API 回归最初仅有 1 个失败：它仍断言第二次无变化运行复用首轮 filename/download_url。测试已按 TASK-07 契约改为断言当前 `filename=null`，并通过独立 `historical_report` 验证历史下载仍可用。
- 后端完整测试：57/57 通过。
- 目标文件编译检查通过。

#### 三轮黑盒运行

- 使用全新临时 SQLite 数据库和临时报告目录，通过完整 `WORKFLOW.ainvoke` 入口运行固定来源替身。该验收验证工作流、数据库和 DOCX 状态机，不是实际网络验收，也不宣称来源在线可用。
- 第 1 轮：`generated/full_snapshot`，1 条公告，生成 1 个 DOCX。
- 第 2 轮：`no_change`，0 条公告，`filename=null`，DOCX 总数仍为 1。
- 第 3 轮：预算从 1000000.00 变为 1500000.00，`generated/material_change`，1 条公告，DOCX 总数变为 2。

#### 数据库摘要

- watermark：1 条，`source_id=public-a`，最终 `run_id=blackbox-run-3`，`max_fetched_at=2026-07-15T10:00:00+08:00`，记录 1 个公告稳定指纹。
- project snapshot：1 条，版本 2，最终预算 1500000.00、截止时间 2026-07-31T17:00:00+08:00、采购人“某采购单位”；包含 1 个生命周期公告和 3 条字段证据。
- delivery：2 条，分别为 `full_snapshot/generated` 和 `material_change/generated`；无变化轮没有伪造 delivery 或 DOCX。
- 报告目录：新生成 DOCX 共 2 个；文件名分别使用各自 delivery fingerprint，第二轮没有新增文件。

#### 下一步

- 汇总 Standards / Spec 双轴审查，修复发现后重跑回归；最终更新 WORK_PLAN 状态。

### 2026-07-14 — 阶段 4：双轴审查修复与最终验收

#### 双轴审查

- 因 `.git` 不可用，无法按 commit/merge-base 生成 diff；按 TASK-06 已知原实现和 TASK-07 声明文件集合完成 Standards / Spec 两个隔离只读审查。
- 审查发现并以新增红灯测试复现 5 项：重抓证据导致 fingerprint 漂移、历史任务的新项目批次误标 full、水位线回退、no-change 证据版本丢失、陈旧 pending 无法接管。5 个测试初次运行均失败，修复后全部通过。
- delivery 记录补充项目/公告稳定指纹集合；SQLite 初始化改为进程内串行，避免并发首次建库争夺 WAL。
- 删除 change 节点未被 LangGraph 状态保留的候选字段和 Publisher 死代码，feedback 只在提交边界重建候选快照。

#### 最终验证

- TASK-07 定向测试：15/15 通过。
- 后端完整测试：62/62 通过。
- 目标文件编译检查通过。
- 敏感凭据模式、`example.local` 和“模拟证据”扫描在生产改动范围内无命中。
- 修复后重新执行三轮临时库黑盒：结果仍为 full_snapshot → no_change → material_change；项目快照版本 2，公告快照版本 1/2，delivery 2 条 generated，报告目录 2 个 DOCX。

#### 失败路径结论

- DOCX 生成失败：delivery 记为 failed，项目快照和水位线保持原值；相同业务变化即使重新抓取导致 evidence/fetched_at 改变，也复用同一 fingerprint 并可重试为 generated。
- 单来源失败：只提交成功来源 watermark；失败来源没有水位线行。
- 并发：数据库唯一约束只允许一条 delivery；非所有者等待 generated 事实并复用同一文件。
- 崩溃恢复：5 分钟前的 pending 可由新运行原子接管；过期 lock/staging 可清理，近期锁不被误删。

#### 状态与未完成项

- TASK-07 需求范围已完成；`WORK_PLAN` 中 I01 更新为已完成。
- `WORK_PLAN` 的 I02 仍为进行中，因为总计划还要求关键资格/技术条款变化规则，本任务只要求并完成预算、截止时间、采购人和公告生命周期。
- 数据库 delivery 表是报告级聚合记录，保留项目/公告指纹集合、变化 JSON 和状态约束；公开 `DeliveryRecord` schema 仍保持 TASK-01 的单项目契约，未为内部聚合强改公共接口。
- 报告文件继续沿用 TASK-06 的 task/fingerprint 确定性命名，以满足并发唯一工件；这与旧 `REPORT_FORMAT` 的分钟文件名文字约定存在既有文档差异，本任务未越界修改该文档。
- 本次三轮验收使用固定来源替身和临时数据库，不是实际网络验收；未把 fixture 结果称为真实网络成功。
- 未修改来源解析器、调度器、意图解析器或前端；水位线已可靠持久化，来源适配器侧按水位线缩小抓取窗口仍属于后续集成。
- `.git` 仍不是有效仓库，无法创建实现技能要求的提交；未初始化、删除或修复 Git 元数据。

## 最终状态

- 状态：TASK-07 已完成并通过验收
- 更新时间：2026-07-14（Asia/Shanghai）
