# BidRadar-X 统一数据契约

版本：TASK-01 / 2026-07-14

## 1. 目的与边界

本契约定义“真实数据源 → 清洗去重 → 增量判断 → DOCX”各模块之间唯一共享的结构化数据形态。实现位于 `backend/app/schemas/tender.py`，调用方应直接从 `app.schemas.tender` 导入模型。

本任务只定义模型和校验规则，不改变现有数据源、工作流、存储或前端。现有普通字典可由后续任务在模块边界逐步转换为这些模型，不要求一次性改造全部节点。

统一约定：

- 所有时间使用带时区的 ISO 8601 时间；不得保存无时区时间。
- URL 使用 HTTP(S) URL。
- 所有指纹使用 64 位小写十六进制 SHA-256 字符串。
- 未知事实必须保存为 `value=null`，并填写 `unknown_reason`；禁止用模板或推测补值。
- 已知 Word 事实和表格行必须携带 `evidence_ids`，且编号必须指向同一 `TenderNotice.evidence` 中的证据。
- 模型拒绝未声明字段，避免不同模块静默产生不兼容的私有字段。

## 2. 模型总览

| 模型 | 职责 | 主要生产者 | 主要消费者 |
| --- | --- | --- | --- |
| `TaskSpec` | 规范化用户主题、区域、关键词、排除词和时间窗口 | 需求理解 | 来源选择、检索、调度 |
| `ScheduleSpec` | 描述 once/daily/weekly 频率与时区 | API/需求理解 | 调度与增量任务 |
| `SourceRecord` | 描述一条公告的实际发布位置及原始/转载角色 | 来源采集、归并 | 去重、审计、报告 |
| `Attachment` | 描述公告附件链接、类型、哈希和抓取时间 | 附件采集 | 解析、证据、报告 |
| `TenderNotice` | 表示一条来源特定的公告，并连接公告事件和项目实体 | 标准化、归并 | 去重、增量、DOCX |
| `EvidenceReference` | 将结构化字段绑定到可复核 URL、文档、页码/定位符和原文片段 | 解析/抽取 | 核验、DOCX |
| `DeliveryRecord` | 记录全量、新项目或实质变化的幂等交付 | 增量/报告 | 推送记忆、审计 |
| `RequirementSection` 等 | 表示 Word 的八类章节、事实和可变宽表格 | 字段抽取 | DOCX 渲染 |
| `FieldChange` | 表示实质字段变化的前值、后值和证据 | 变化检测 | `DeliveryRecord`、DOCX |

## 3. TaskSpec 与 ScheduleSpec

`TaskSpec` 字段：

- `task_id`：跨运行稳定的任务 ID。
- `query`：用户原始需求，保留用于审计。
- `topic`：规范化主题。
- `regions`：零个或多个规范化地区；空列表表示未限定，不使用“未知地区”等伪值。
- `keywords`：至少一个正向检索/相关性关键词。
- `exclusions`：排除语境。
- `time_range_start`、`time_range_end`：可为空的监控窗口；两者同时存在时结束时间不得早于开始时间。
- `schedule`：执行计划。

`ScheduleSpec.frequency` 只允许 `once`、`daily`、`weekly`，`timezone` 默认 `Asia/Shanghai`。未来调度任务可新增独立运行记录，但不应把动态的 `next_run_at` 写回任务定义。

## 4. TenderNotice 字段契约

| 业务字段 | 模型字段 | 规则 |
| --- | --- | --- |
| 标题 | `title` | 非空原始/规范化公告标题 |
| 发布时间 | `published_at` | 带时区；来自来源页面，不得用抓取时间代替 |
| 来源名称 | `source.source_name` | 实际发布站点名称 |
| 来源链接 | `source.source_url` | 实际访问到的公告 URL |
| 核心内容 | `core_content` | 清洗后的客观正文，非模板摘要 |
| 附件链接 | `attachments[].url` | 每个附件独立记录；可补充名称、媒体类型、哈希和抓取时间 |
| 地区 | `region` | 未确认时为 `null` |
| 主题关键词 | `topic_keywords` | 由任务和正文匹配得到，可为空列表 |
| 采购人 | `purchaser` | 未确认时为 `null` |
| 预算 | `budget` + `budget_currency` | 非负十进制金额；默认币种 CNY；未披露时为 `null` |
| 截止时间 | `deadline` | 带时区；未披露时为 `null` |
| 原始内容指纹 | `raw_content_fingerprint` | 本次来源原始响应/正文的精确内容身份 |
| 公告稳定指纹 | `notice_stable_fingerprint` | 同一生命周期公告跨站转载共享 |
| 项目稳定指纹 | `project_stable_fingerprint` | 同一项目的招标、更正、结果等不同公告共享 |
| 抓取时间 | `fetched_at` | 本次采集完成的带时区时间 |

附加字段：

- `notice_id`：这条来源特定公告记录的主键。
- `notice_type`：`tender`、`correction`、`award`、`cancellation` 或 `other`，用于区分项目生命周期事件。
- `project_code`：来源披露的项目编号；未披露时为 `null`，不得生成伪编号。
- `evidence`：字段级证据集合。
- `requirement_sections`：Word 内容集合。

`project_code`、`region`、非空 `topic_keywords`、`purchaser`、`budget`、`deadline` 只要存在，就必须有一条 `EvidenceReference.field_path` 与字段名完全一致的证据；缺失证据时模型拒绝该公告。标题、发布时间和正文由公告自身的来源 URL 与抓取时间直接溯源。

### 4.1 三层身份与跨站转载

必须同时保留以下三层，不得只用一个“项目 ID”替代：

1. 来源发布记录：由 `notice_id`、`source.source_url`、`source.publication_role` 和 `raw_content_fingerprint` 表示。原站与转载站各有一条记录。
2. 公告生命周期事件：由 `notice_stable_fingerprint` 表示。同一招标公告的跨站转载共享该值；更正公告或结果公告使用不同值。
3. 项目实体：由 `project_stable_fingerprint` 表示。同一项目的招标、更正、结果及其转载共享该值。

`SourceRecord.publication_role` 必须明确为：

- `original`：权威或首发来源；
- `republication`：跨站转载。若已识别原公告，可在 `canonical_notice_url` 保存原公告 URL；未知时保持 `null`。

指纹计算算法由后续去重任务版本化实现，但必须满足：相同输入跨运行稳定；原始内容指纹包含原始内容差异；公告稳定指纹排除转载站 URL 和抓取时间；项目稳定指纹排除公告类型、发布时间、转载站和抓取时间，并使用可验证的项目编号/采购人/标题等规范化事实。算法升级不得静默覆盖历史版本，存储任务应为版本字段预留迁移能力。

## 5. 附件与证据

`Attachment` 保存公告实际给出的附件 URL。下载完成后可填写 `content_sha256`、`media_type` 和 `fetched_at`；下载失败时仍保留链接，不删除公告。

`EvidenceReference` 至少保存：

- `evidence_id`：公告内唯一编号；
- `field_path`：被证明字段的稳定路径；
- `source_url`：可复核页面或附件 URL；
- `quote`：支持该字段的原文片段；
- `fetched_at`：证据采集时间。

附件证据还可填写 `attachment_id`、`document_name`、`page_number`、`section`；HTML、表格或无页码文档可使用 `locator` 保存 CSS 选择器、段落编号、工作表/单元格等定位信息。若填写 `attachment_id`，该编号必须存在于同一公告的 `attachments` 中。

## 6. Word 内容契约

`TenderNotice.requirement_sections` 使用统一结构表示章节：

- `RequirementSection`：`section_id`、标题、摘要、事实列表、表格列表。
- `RequirementFact`：标签、值、未知原因、证据编号。
- `RequirementTable`：标题、列名和行；列数可随章节变化。
- `RequirementTableRow`：单元格和支持整行的证据编号；单元格数量必须与列数一致。

允许的八个 `section_id` 及应能容纳的 Word 字段如下。以下是字段类别，不是固定内容，任何值都必须从真实来源抽取：

1. `procurement`（项目及采购内容）：背景目标、工作范围与责任边界、甲方提供条件、中标方工作、不包含内容，以及标段、名称、数量、单位、交付成果、格式。
2. `qualification`（投标人资格要求）：资格原文、资质名称与等级、颁发机构、成立年限与注册资本、财务与审计、纳税与社保、类似业绩、项目负责人、团队、禁止投标情形、证明材料及适用标段。
3. `technical`（技术与服务要求）：型号规格/材质、国家或行业标准、兼容性、软硬件功能、人员驻场、样品、测试运维、售后响应、保密安全，以及“项目、甲方要求值、强制性、证明材料位置”等参数表列。
4. `timeline`（项目周期与验收要求）：合同/开始条件、总工期、阶段时刻表和交付物、驻场/交货/运输、安装调试、初验/终验、验收资料、指标方法与不合格处理、质保服务。
5. `commercial`（报价、付款与保证金）：控制价/最高限价、单价/总价/费率、暂估/暂列金额、包含和不得计入费用、税率/发票、付款节点、审计/财政拨款前提、质保金、投标/履约保证金。
6. `submission`（投标组织与文件要求）：联合体/分包、标书获取、提问截止/踏勘、标书目录、证明材料/签章、正副本份数、命名/上传/密封/递交、截标/开标。
7. `evaluation`（评标与定标规则）：资格/符合性审查、价格公式与基准价、偏差扣分、业绩证明/演示答辩、异常低价/废标、同分排序/定标，以及评分类别、项目、分值、标准和证明材料位置。
8. `reference`（客观参考信息）：招标人公开登记、公开司法案件、公开被执行、公开行政处罚、数据来源/更新时间，以及历史项目名称、公告时间、地点、规模、控制价、投标/中标单位、金额或折扣率、期限。

`reference` 只允许收录合法公开且可证实的客观事实，不得扩展为企业画像、胜率、风险、竞争对手或投标建议。

## 7. 增量与交付契约

`DeliveryRecord.delivery_type`：

- `full_snapshot`：首次或明确要求的全量交付；
- `new_project`：此前未交付的 `project_stable_fingerprint`；
- `material_change`：同一项目发生实质字段变化，必须至少包含一个 `FieldChange`。

`FieldChange` 保存 `field_path`、`previous_value`、`current_value` 和支持新值的 `evidence_ids`。仅格式变化不得生成 `material_change`。

`delivery_fingerprint` 是增量推送幂等键。后续存储实现应对任务范围内的该字段建立唯一约束；其确定性输入至少包含 `task_id`、`project_stable_fingerprint`、`notice_stable_fingerprint`、交付类型和规范化变化内容。重复运行命中相同指纹时复用已有记录，不重复生成或发送报告。

状态只允许 `pending`、`generated`、`delivered`、`failed`；`delivered` 必须带 `delivered_at`。`artifact_uri` 保存 DOCX 工件的受控内部定位符，不保存账号、令牌或签名下载凭据。

## 8. 后续任务如何使用

- 数据库/迁移任务：按模型拆分任务、来源发布、公告、项目、附件、证据、章节、快照和交付表；完整保留三个指纹，并对任务范围内 `delivery_fingerprint` 建唯一约束。持久化边界使用 `model_dump(mode="json")`，读取时用对应模型重新校验。
- 真实来源任务：每个采集结果先构造 `SourceRecord`、`Attachment` 和来源特定的 `TenderNotice`；不得继续向后传递自由形态字典。
- 文档解析与字段抽取任务：为每个已知字段创建 `EvidenceReference`；写入 `RequirementFact`/`RequirementTableRow` 的 `evidence_ids`。未披露字段写 `null + unknown_reason`。
- 去重任务：计算并版本化 `raw_content_fingerprint`、`notice_stable_fingerprint`、`project_stable_fingerprint`，设置 `publication_role`，保留所有来源记录而不是删除转载。
- 增量任务：以项目指纹读取历史快照，以公告指纹区分生命周期事件，以 `FieldChange` 表示实质变化，再生成 `DeliveryRecord` 并用交付指纹去重。
- DOCX 任务：按 `requirement_sections` 顺序渲染事实与表格，并通过 `evidence_ids` 输出来源、附件、页码/定位符和原文片段；不得从旧固定模板补造缺失内容。

在现有普通字典工作流迁移期间，应在节点输入/输出边界显式调用模型校验；不要修改本契约来迎合单个来源的临时字段，来源私有元数据应先规范化或由后续版本经过评审新增。
