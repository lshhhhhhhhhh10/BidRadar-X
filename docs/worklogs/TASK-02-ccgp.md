# TASK-02 中国政府采购网真实采集适配器

- 更新时间：2026-07-14 12:35（Asia/Shanghai）
- 状态：已完成
- 负责人/窗口：Codex TASK-02 窗口
- 依赖任务：TASK-01 统一数据契约
- 声明文件范围：
  - `backend/app/sources/ccgp.py`
  - `backend/tests/fixtures/ccgp/`
  - `backend/tests/test_ccgp_source.py`
  - `docs/worklogs/TASK-02-ccgp.md`
- 明确不修改：
  - `source_select.py`、`requirements.txt`、现有其他数据源、工作流、前端和报告模块

## 阶段记录

### 2026-07-14 12:14 — 阶段 1：契约、现状与公开站点结构调研

#### 已完成

- 阅读 `docs/PROJECT_CONTEXT.md`、`docs/DATA_CONTRACT.md`、`app.schemas.tender`、现有来源适配器、采集节点和后端测试。
- 确认本适配器直接返回 `TenderNotice`，并为所有已抽取结构化事实创建字段级 `EvidenceReference`；来源未披露或无法可靠解析的字段保持空值。
- 确认公开测试 seam 为 `CCGPSource.collect(task_spec, search_plan)`：测试替换 HTTP 传输，覆盖主题、地区、时间参数，列表到详情解析，以及合规失败行为。
- 只读核对中国政府采购网公开检索入口和公告详情结构。详情页公开元数据包含标题与发布时间，正文位于公告内容容器，概要表可提供采购人、地区、预算等事实，附件可能以链接或 `gm-download` 属性发布。
- 真实检索入口返回“访问频繁”安全页时停止继续探测；实现将识别并显式报错，不尝试绕过验证码、频控或其他网站安全措施。
- 确认可用实现无需新增第三方依赖：HTTP 使用 Python 标准库，HTML 使用 `html.parser`。若后续集成选择更强健的解析库，应由集成任务统一添加依赖。

#### 改动文件

- `docs/worklogs/TASK-02-ccgp.md`：创建独立日志并声明文件边界。

#### 验证结果

- 命令/检查：UTF-8 读取项目上下文、数据契约、模型、来源与相关测试；对公开详情页进行单次只读结构核对。
- 结果：通过。
- 证据：确认 TASK-01 的模型证据约束；公开详情页提供 `ArticleTitle`、`PubDate`、公告正文、概要表及附件声明结构。

#### 阻塞

- 当前 `.git` 目录不含 `HEAD` 等可识别仓库元数据，Git 报告当前目录不是仓库；不阻塞实现与测试，但最终无法创建提交或做基于提交点的 diff。

#### 下一步

- 以脱敏列表页和详情页 fixture 先编写失败测试，再按纵向切片实现查询、解析和合规网络策略。

### 2026-07-14 12:20 — 阶段 2：脱敏 fixture 与核心采集纵向切片

#### 已完成

- 创建脱敏搜索列表、完整详情和字段未披露详情 fixture；不含真实单位、联系人、账号或凭据。
- 按红灯 → 绿灯实现首个公共行为切片：`collect` 将主题、关键词、地区和时间范围映射到公开检索参数，从列表跟进详情页，并返回通过 `TenderNotice` 校验的公告。
- 解析详情页标题、发布时间、正文、项目编号、采购人、地区、预算、截止时间和显式附件链接，为非空结构化事实创建字段级证据。
- 以列表发布时间预过滤时间窗口，以列表和详情两层地区匹配过滤噪声结果，避免抓取明显越界公告。
- 验证不可解析的“未披露”预算和“另行通知”截止时间保持 `None`；无法可靠还原的相对 `gm-download` 标识不生成附件 URL。
- 生成来源记录、来源公告 ID、原始内容指纹、公告稳定指纹和项目稳定指纹；不硬编码任何公告结果。

#### 改动文件

- `backend/app/sources/ccgp.py`：新增标准库实现的 CCGP 查询、列表解析、详情解析和契约模型构造。
- `backend/tests/fixtures/ccgp/search_results.html`：脱敏列表 fixture，含时间和地区边界项。
- `backend/tests/fixtures/ccgp/detail_tender.html`：脱敏完整详情 fixture。
- `backend/tests/fixtures/ccgp/search_results_unknown.html`：脱敏未披露字段列表 fixture。
- `backend/tests/fixtures/ccgp/detail_unknown_fields.html`：脱敏未披露字段详情 fixture。
- `backend/tests/test_ccgp_source.py`：新增 `collect` 公共 seam 测试。

#### 验证结果

- 命令/检查：`python -m unittest tests.test_ccgp_source -v`（在 `backend` 目录，使用 Codex bundled Python）。
- 结果：通过。
- 证据：2 个测试全部通过；红灯分别验证缺失适配器和地区噪声未过滤，绿灯验证查询、契约输出、字段证据、附件、未知值及范围过滤。

#### 阻塞

- 无。

#### 下一步

- 为访问频繁/安全验证停止行为、超时重试、请求限速、User-Agent 和必需字段解析失败补充纵向测试与实现。

### 2026-07-14 12:25 — 阶段 3：网络韧性、合规停止与解析失败策略

#### 已完成

- 为默认 HTTP 传输设置 15 秒超时、2 次重试、0.5 秒指数退避、每次请求最少 1 秒间隔和固定标识 User-Agent；全部参数可在测试中注入。
- 使用异步锁串行维护请求起始间隔，避免同一适配器并发调用绕过限速。
- 对超时、连接错误和 5xx 做有限重试；普通 4xx 不重试；403、429、访问频繁、验证码和安全验证页面立即抛出 `CCGPAccessBlockedError`，不尝试绕过。
- 必需的详情标题、来源发布时间或正文缺失时跳过该详情并记录警告，不使用列表值或抓取时间补造。
- 搜索结果容器缺失时显式抛出解析错误，避免把页面结构变化误报成“零结果”。
- 支持 `TaskSpec.regions` 的多个地区逐区检索，并对重复详情 URL 去重。
- 收紧列表标题解析，只采集公告链接自身文本；区分瞬态 5xx 与不可重试 4xx。

#### 改动文件

- `backend/app/sources/ccgp.py`：增加重试、退避、限速、安全页停止、多地区检索和显式解析失败策略。
- `backend/tests/fixtures/ccgp/access_blocked.html`：脱敏访问频繁/安全验证 fixture。
- `backend/tests/fixtures/ccgp/search_results_empty.html`：空结果 fixture。
- `backend/tests/fixtures/ccgp/detail_missing_required.html`：必需来源字段缺失 fixture。
- `backend/tests/test_ccgp_source.py`：增加安全停止、重试、User-Agent、超时、限速、必需字段缺失及多地区测试。

#### 验证结果

- 命令/检查：`python -m py_compile app/sources/ccgp.py tests/test_ccgp_source.py`。
- 结果：通过。
- 证据：适配器和测试文件语法检查通过。
- 命令/检查：`python -m unittest tests.test_ccgp_source -v`。
- 结果：通过。
- 证据：7 个定向测试全部通过；安全页测试确认仅发出 1 次请求，超时测试确认 3 次总尝试和 0.25/0.5 秒退避，限速测试确认相邻请求间隔 0.75 秒。

#### 阻塞

- 无实现阻塞。

#### 下一步

- 运行后端完整测试，按 `code-review` 技能从标准与任务规格两轴审查限定范围改动，完成最终日志和安全检查。

### 2026-07-14 12:35 — 阶段 4：双轴审查、全量验证与移交

#### 已完成

- 完成标准轴审查：修复超长行、搜索页空页继续请求、非 CCGP 跳转校验、解码文本代替原始响应字节计算指纹，以及异常页面无界读取问题。
- 完成规格轴审查：发现并修复“开标时间”误当投标截止时间、正文项目编号未抽取、详情发布时间未二次执行时间窗校验三项问题；均有回归测试或既有端到端断言覆盖。
- 默认传输现在以原始响应字节计算 `raw_content_fingerprint`，并将 HTML 响应限制为 10 MB；测试传输可继续只提供文本。
- 增加搜索页结构漂移 fixture，确认结构未知时显式报错而不是返回空结果。
- 逐项对照任务规格确认：没有硬编码项目结果，返回 `TenderNotice`，保存来源 URL、来源发布时间、清洗正文和页面明确提供的 HTTP(S) 附件链接，设置超时/重试/限速/User-Agent，未知字段不补造，安全页不绕过。
- 动态 `gm-download` 相对对象标识不等于可访问 URL；在无法从官网公开 HTML 可靠验证转换规则时保持不构造。后续若集成任务获得官方稳定解析规则，可在本适配器补充并增加对应 fixture；当前不会把猜测地址写进 `Attachment.url`。
- 未修改总工作流、`source_select.py`、`requirements.txt`、其他来源、前端或报告模块；未新增依赖，也未接入总工作流。

#### 改动文件

- `backend/app/sources/ccgp.py`：完成 CCGP 真实公开检索、列表/详情解析、契约输出、网络策略与合规停止逻辑。
- `backend/tests/fixtures/ccgp/`：共 8 个脱敏 HTML fixture，覆盖完整详情、未知字段、空结果、时间/地区边界、安全页、必需字段缺失和结构漂移。
- `backend/tests/test_ccgp_source.py`：共 8 个公共 seam 测试。
- `docs/worklogs/TASK-02-ccgp.md`：完成各阶段、审查、验证和移交记录。

#### 验证结果

- 命令/检查：`python -m py_compile app/sources/ccgp.py tests/test_ccgp_source.py`。
- 结果：通过。
- 证据：实现和测试语法检查通过。
- 命令/检查：`python -m unittest tests.test_ccgp_source -v`。
- 结果：通过。
- 证据：8 个 CCGP 定向测试全部通过。
- 命令/检查：复用仓库 `.venv/Lib/site-packages` 后执行 `python -m unittest discover -s tests -v`。
- 结果：通过。
- 证据：后端共 44 个测试全部通过；仅出现既有 Starlette/httpx 弃用警告。
- 首次全量测试说明：bundled Python 未包含 `fastapi`、`langgraph`，导致 API/工作流测试导入失败；只读注入仓库现有 `.venv` site-packages 后复跑通过，未安装依赖或修改配置。
- 命令/检查：限定路径敏感信息扫描、生成缓存清理、禁止文件时间戳检查。
- 结果：通过。
- 证据：未发现 Authorization/Cookie/Token/API Key/私钥模式；本任务 `.pyc` 已清理；`source_select.py` 与 `requirements.txt` 保持既有时间戳。

#### 阻塞

- 交付实现无阻塞。
- 环境限制：`.git` 目录仍无 `HEAD` 等仓库元数据，Git 报告当前目录不是仓库，因此无法按技能要求创建提交或执行基于固定点的正式 diff；已改为对允许路径执行本地标准轴/规格轴审查。

#### 下一步

- 由后续集成任务在 `source_select.py`/工作流中显式注册 `CCGPSource`；本任务按边界不接入。
- 若后续取得官网稳定、可验证的动态附件解析规则，为相对 `gm-download` 增加转换测试后再启用，不得猜测 URL。

## 安全检查

- [x] 未将账号写入仓库或日志。
- [x] 未将 Cookie 写入仓库或日志。
- [x] 未将 Token 写入仓库或日志。
- [x] 未将 API Key 写入仓库或日志。
- [x] 仅记录了无敏感值的环境变量名或配置状态。

## 完成验收

- [x] 可按主题、地区和时间范围检索公开公告。
- [x] 返回符合 DATA_CONTRACT 的 `TenderNotice`。
- [x] 保存来源 URL、发布时间、正文和页面明确提供的 HTTP(S) 附件链接。
- [x] 配置合理超时、重试、限速与 User-Agent。
- [x] 解析失败不伪造字段。
- [x] 脱敏 HTML fixture 测试通过。
- [x] 不绕过验证码或网站安全措施。
- [x] 所有改动都在声明文件范围内。
- [x] 改动文件和验证结果已记录。
- [x] 已完成安全检查。
