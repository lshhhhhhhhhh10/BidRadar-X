# TASK-01 统一数据契约

- 更新时间：2026-07-14（Asia/Shanghai）
- 状态：已完成
- 负责人/窗口：Codex TASK-01 窗口
- 依赖任务：C00；本任务仅定义契约，不替代 F01、F02、R03 的实现
- 声明文件范围：
  - `backend/app/schemas/tender.py`
  - `backend/tests/test_tender_schema.py`
  - `docs/DATA_CONTRACT.md`
  - `docs/worklogs/TASK-01-data-contract.md`
- 明确不修改：
  - 现有数据源、工作流、前端、`requirements.txt`、共享配置及其他文件

## 阶段记录

### 2026-07-14 — 阶段 1：上下文与现状调研

#### 已完成

- 阅读 `docs/PROJECT_CONTEXT.md`、`docs/WORK_PLAN.md` 及现有 schemas、storage、workflow、sources。
- 确认统一契约必须贯穿“真实数据源 → 清洗去重 → 增量判断 → DOCX”，并保持来源 URL、发布时间、抓取时间和字段级证据。
- 识别现有 Word 展示所需的八类章节，可统一表示为章节、事实项、表格和证据引用，避免把当前固定模板内容写进契约。
- 确认公开测试 seam 为 Pydantic 模型的构造、校验和序列化接口。

#### 改动文件

- `docs/worklogs/TASK-01-data-contract.md`：创建独立日志并声明文件边界。

#### 验证结果

- 命令/检查：以 UTF-8 逐项读取任务指定目录和项目上下文，并检索现有 Word 字段结构。
- 结果：通过。
- 证据：确认项目使用 Pydantic 2.12.5；现有数据以普通字典跨节点传递；八类模块均可归一为事实和表格。

#### 阻塞

- 当前目录的 `.git` 不含可识别的仓库元数据，暂不能执行基于提交点的审查或提交；不阻塞模型实现与测试。

#### 下一步

- 先编写模型公开行为测试，验证来源角色、项目身份、字段级证据、Word 章节表达和增量交付幂等键。

### 2026-07-14 — 阶段 2：测试驱动的统一模型实现

#### 已完成

- 按红灯 → 绿灯切片实现 `ScheduleSpec`、`TaskSpec`、`SourceRecord`、`Attachment`、`TenderNotice`、`EvidenceReference`、`DeliveryRecord`。
- 增加 Word 内容配套模型 `RequirementSection`、`RequirementFact`、`RequirementTable`、`RequirementTableRow`，覆盖八类章节、事实和可变宽表格。
- 增加 `FieldChange`，使增量记录能够携带字段路径、前值、后值和证据编号。
- 建立三层身份：原始内容指纹、公告稳定指纹、项目稳定指纹；来源角色显式区分原始发布和转载。
- 增加契约校验：时区时间、SHA-256 格式、时间窗口顺序、未知值原因、证据/附件引用完整性、表格列数及交付状态一致性。

#### 改动文件

- `backend/app/schemas/tender.py`：新增统一 Pydantic 数据契约。
- `backend/tests/test_tender_schema.py`：新增模型公开行为测试。
- `docs/worklogs/TASK-01-data-contract.md`：追加阶段结果。

#### 验证结果

- 命令/检查：`python -m unittest tests.test_tender_schema -v`（在 `backend` 目录，使用 Codex bundled Python）。
- 结果：通过。
- 证据：共运行 7 个测试，全部通过；红灯分别验证缺失模型/接口，绿灯验证任务窗口、公告与转载身份、八类 Word 内容、证据完整性和增量交付。

#### 阻塞

- 无实现阻塞；Git 元数据缺失问题保留至收尾说明。

#### 下一步

- 编写 `docs/DATA_CONTRACT.md`，逐项定义字段语义、指纹计算边界、Word 章节映射和后续任务用法。

### 2026-07-14 — 阶段 3：数据契约文档

#### 已完成

- 编写统一契约的适用边界、公共规则和模型生产者/消费者关系。
- 将 TenderNotice 的标题、发布时间、来源、核心内容、附件、地区、关键词、采购人、预算、截止时间、三类身份指纹及抓取时间逐项映射到模型字段。
- 列明八类 Word 章节可表达的字段类别，并强调这些是结构而非固定内容。
- 定义三层身份、转载保留策略、未知值规则、字段级证据和增量交付幂等键。
- 写明数据库、真实来源、解析抽取、去重、增量和 DOCX 后续任务的接入方式。

#### 改动文件

- `docs/DATA_CONTRACT.md`：新增完整统一数据契约。
- `docs/worklogs/TASK-01-data-contract.md`：追加文档阶段记录。

#### 验证结果

- 命令/检查：人工逐条对照用户验收要求、`PROJECT_CONTEXT.md`、`WORK_PLAN.md` 与现有八类 Word 模块字段。
- 结果：通过。
- 证据：七个必需模型均有字段说明；TenderNotice 必需字段和后续模块使用方式均有独立章节。

#### 阻塞

- 无。

#### 下一步

- 执行语法检查、模型定向测试和后端完整测试；审查仅限本任务四个文件，并完成安全/范围检查。

### 2026-07-14 — 阶段 4：验证、审查与移交

#### 已完成

- 完成标准轴审查：发现非空结构化事实可缺少字段级证据、时区仅校验非空两项问题；均已修复并补充回归测试。
- 完成需求轴审查：七个必需模型、TenderNotice 必需字段、三层身份、八类 Word 内容、增量交付和后续任务用法均已覆盖，未发现范围蔓延。
- 验证 TenderNotice 生成的 JSON Schema 将标题、发布时间、来源、核心内容、原始内容指纹、项目稳定指纹和抓取时间列为必需字段。
- 清理测试产生的本任务 `.pyc` 文件；源文件改动保持在声明的四个文件内。
- 完成安全检查和下游移交说明。

#### 改动文件

- `backend/app/schemas/tender.py`：增加已知结构化事实的证据路径校验和有效 IANA 时区校验。
- `backend/tests/test_tender_schema.py`：增加核心事实证据和无效时区回归测试。
- `docs/DATA_CONTRACT.md`：补充非空结构化字段的证据要求。
- `docs/worklogs/TASK-01-data-contract.md`：记录最终验证与移交。

#### 验证结果

- 命令/检查：`python -m unittest tests.test_tender_schema -v`。
- 结果：通过。
- 证据：9 个模型测试全部通过。
- 命令/检查：以当前 bundled Python 加载仓库现有 `.venv/Lib/site-packages` 后执行 `python -m unittest discover -s tests -v`。
- 结果：通过。
- 证据：后端共 11 个测试全部通过（模型 9、API 1、工作流 1）；仅出现既有 Starlette/httpx 弃用警告。
- 命令/检查：生成 `TenderNotice.model_json_schema()` 并检查必需字段集合。
- 结果：通过。
- 证据：必需字段检查输出 `TenderNotice JSON Schema required-field check: OK`。
- 首次完整测试说明：直接使用 bundled Python 时因缺少 `fastapi`、`langgraph` 导入失败；仓库 `.venv` 的解释器记录了另一用户的失效路径。随后只读复用该虚拟环境已有 site-packages 复跑成功，未安装依赖、未修改配置。

#### 阻塞

- 任务验收无阻塞。
- 环境限制：当前 `.git` 目录为空，系统和 bundled Git 均报告“not a git repository”，因此无法执行提交或基于提交点的正式 diff；不影响四个交付文件和测试结果。

#### 下一步

- 下一任务从 `app.schemas.tender` 直接导入模型，在模块输入/输出边界用 `model_validate` 校验、用 `model_dump(mode="json")` 持久化；详细分工见 `docs/DATA_CONTRACT.md` 第 8 节。
- 由协调窗口更新 `docs/WORK_PLAN.md` 的任务状态；本窗口按文件边界不修改总计划。

## 安全检查

- [x] 未将账号写入仓库或日志。
- [x] 未将 Cookie 写入仓库或日志。
- [x] 未将 Token 写入仓库或日志。
- [x] 未将 API Key 写入仓库或日志。
- [x] 仅记录了无敏感值的环境变量名或配置状态。

## 完成验收

- [x] 至少定义 TaskSpec、ScheduleSpec、SourceRecord、Attachment、TenderNotice、EvidenceReference、DeliveryRecord。
- [x] TenderNotice 覆盖任务要求字段及 Word 内容结构。
- [x] 可区分原始公告、跨站转载和项目实体。
- [x] 可支持后续增量推送与幂等交付。
- [x] 模型测试通过。
- [x] 所有改动都在声明文件范围内。
- [x] 改动文件和验证结果已记录。
- [x] 已完成安全检查。
- [x] 已写明下一任务的模型使用方式。
