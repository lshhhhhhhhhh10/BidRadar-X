# TASK-03 全国公共资源交易平台真实采集适配器

- 更新时间：2026-07-14 13:15（Asia/Shanghai）
- 状态：已完成（实时站点连通性待具备 DNS 的集成环境复验）
- 负责人/窗口：Codex TASK-03 窗口
- 依赖任务：TASK-01 统一数据契约
- 声明文件范围：
  - `backend/app/sources/ggzy.py`
  - `backend/tests/fixtures/ggzy/`
  - `backend/tests/test_ggzy_source.py`
  - `docs/worklogs/TASK-03-ggzy.md`
- 明确不修改：
  - `source_select.py`、`requirements.txt`、现有其他数据源、工作流、前端和报告模块

## 阶段记录

### 2026-07-14 12:30 — 阶段 1：契约、现状与公开站点结构调研

#### 已完成

- 阅读 `docs/PROJECT_CONTEXT.md`、`docs/DATA_CONTRACT.md`、`app.schemas.tender`、现有来源适配器及后端测试。
- 确认公开测试 seam 为 fixture 驱动的列表/详情解析，以及 `GGZYSource.collect(task_spec, search_plan)` 的分页、筛选和失败行为。
- 核对全国公共资源交易平台公开交易查询页：支持发布时间、数据来源、省市/平台、业务类型、信息类型和关键词筛选；列表由公开 POST 分页接口加载，详情使用 `www.ggzy.gov.cn/information/deal/html/...` URL。
- 确认适配器直接返回 `TenderNotice`，所有非空结构化字段都必须生成字段级 `EvidenceReference`；来源未可靠披露的字段保持空值。
- 确认无需新增第三方依赖：HTTP 与 HTML 解析使用 Python 标准库。依赖文件不在本任务授权范围内。
- 明确合规边界：识别验证码、频控、拒绝访问和登录提示并停止，不尝试绕过；不保存 Cookie 或凭据。

#### 改动文件

- `docs/worklogs/TASK-03-ggzy.md`：创建独立日志并声明文件边界。

#### 验证结果

- 命令/检查：UTF-8 读取项目契约、数据模型、现有来源及测试；只读访问官方公开交易查询页和公开详情页。
- 结果：通过。
- 证据：官方页面当前公开展示主题关键词、地区和发布时间筛选，详情 URL 使用官方域名。

#### 阻塞

- 当前 `.git` 目录缺少 `HEAD` 等仓库元数据，Git 无法识别本目录；不阻塞实现和测试，但最终无法创建提交或执行基于提交点的三点 diff。
- 当前运行环境无法直接解析官方域名 DNS，内置网页读取可核对公开页面，但无法保存实时响应作为测试输入；fixture 将依据已核验字段结构脱敏构造，并把传输层保持可注入。

#### 下一步

- 先以脱敏详情 fixture 编写失败测试，再逐个实现解析、分页、空结果和合规失败切片。

### 2026-07-14 12:55 — 阶段 2：fixture 解析与真实采集边界实现

#### 已完成

- 新增 `GGZYSource`，公开入口直接返回 `TenderNotice`，未接入 `source_select.py` 或总工作流。
- 实现全国平台公开 POST 检索参数：主题、时间起止、地区代码、页码及平台公开筛选字段；支持多个地区逐一检索和详情 URL 去重。
- 实现列表 JSON 的大小写/常见字段名兼容解析，按平台页数逐页请求；`ttlpage: 0` 正确表示空结果。
- 实现详情 HTML 多容器解析，提取标题、发布时间、正文、采购项目编号、采购人、信息来源和附件链接。
- 实现聚合详情中的公开 iframe/原文链接跟随：全国平台详情 URL 保存在 `source_url`，原始公告 URL 保存在 `canonical_notice_url`，正文内相对附件按原站 URL 解析。
- 为 `project_code`、`region`、`topic_keywords`、`purchaser` 等非空结构化字段创建字段级证据，生成三类 SHA-256 指纹并保存带时区抓取时间。
- 使用 Python 标准库实现可注入 HTTP 传输、请求超时、一次瞬时失败重试、请求间隔和明确 User-Agent；未新增第三方依赖。若未来改用成熟 HTTP/HTML 库，应由集成任务评审并修改依赖文件。
- 对验证码、安全验证、频控、拒绝访问和相关 HTTP 状态显式抛出 `GGZYAccessRestrictedError`，不重放 Cookie、不解验证码、不规避网站限制。

#### 改动文件

- `backend/app/sources/ggzy.py`：新增真实公开检索、分页、详情/原文解析、契约转换和合规网络错误处理。
- `backend/tests/fixtures/ggzy/`：新增脱敏列表、直接详情、嵌入原文、空结果、访问限制和结构变化 fixture。
- `backend/tests/test_ggzy_source.py`：新增解析、分页筛选、原始来源、空结果、超时、访问限制和结构变化测试。
- `docs/worklogs/TASK-03-ggzy.md`：追加实现阶段记录。

#### 验证结果

- 命令/检查：`python -m unittest discover -s tests -p 'test_ggzy_source.py' -v`（使用工作区内置 Python）。
- 结果：通过，9 个测试全部成功。
- 证据：两页 fixture 均被采集；请求表单包含 `FINDTXT=计算设备`、`DEAL_PROVINCE=340000`、`TIMEBEGIN=2026-07-10`、`TIMEEND=2026-07-14`；直接详情和嵌入原文均生成有效 `TenderNotice`。

#### 阻塞

- 无实现阻塞。官方站点实时连通性因当前运行环境 DNS 限制未做端到端验收，运行时网络边界已通过可注入传输 fixture 覆盖。

#### 下一步

- 执行语法编译、后端全量测试、文件范围检查和规格/标准双轴审查，修复审查发现后完成日志。

### 2026-07-14 13:15 — 阶段 3：双轴审查修复与最终验证

#### 已完成

- 完成 Standards / Spec 双轴只读审查，并逐项修复审查发现：
  - 对城市、区县及未知地区代码增加来源事实/正文后过滤，不再把请求地区回填为公告事实；异地结果 fixture 会被拒绝。
  - 单边开始时间检索到当前日期；单边结束时间使用明确历史下界 `2000-01-01`，不再退化成单日窗口。
  - `SourceRecord.source_name` 与全国平台详情 URL 保持同站一致；原始来源名称作为独立证据片段保存，原文 URL 使用 `canonical_notice_url` 保存。
  - 项目编号存在时以项目编号计算项目稳定指纹；无编号时使用去生命周期词的标题与采购人，跨招标/结果公告保持项目身份稳定。
  - 列表地区与来源名称证据保存原始 JSON 字段片段；locator 保存请求方法、完整 POST 表单（含页码、主题、地区、时间）、`source_notice_id` 和原字段名，可复现定位。
- 增加对应回归测试，TASK-03 测试从 9 项增加到 12 项。
- 完成最终范围核对；仅创建/修改任务声明的四个位置，未接入总工作流，未改依赖、其他来源、前端或报告模块。
- 清理测试/编译产生的 TASK-03 专属 `__pycache__` 文件，未留下授权范围外生成物。

#### 验证结果

- 语法检查：`python -m compileall -q app/sources/ggzy.py tests/test_ggzy_source.py`，通过。
- 任务测试：`python -m unittest discover -s tests -p 'test_ggzy_source.py' -v`，12/12 通过。
- 后端全量：`python -m unittest discover -s tests -v`，43 项中 41 项通过；`test_api` 因当前运行时缺少 `fastapi`、`test_workflow` 因缺少 `langgraph` 无法导入。两者均为 `backend/requirements.txt` 已声明且不在本任务授权范围内的环境依赖，本任务不安装、不修改依赖文件。
- 双轴复核：Standards 通过；Spec 通过；剩余发现 0 项。
- 实时访问：官方公开页面结构已只读核对；当前执行环境对官方域名的直接 DNS 解析失败，故未宣称完成实时端到端抓取。生产传输使用真实公开 URL，可注入传输边界已由 fixture 覆盖。

#### 阻塞与移交

- `.git` 目录仍缺少有效仓库元数据，无法按实现技能要求创建提交；未尝试初始化或修改 `.git`。
- 集成环境应在遵守平台访问政策、无需验证码且 DNS 可用时执行一次小时间窗低频烟测；若平台返回验证码、频控或访问限制，适配器会停止并显式报错。

## 安全检查

- [x] 未将账号写入仓库或日志。
- [x] 未将 Cookie 写入仓库或日志。
- [x] 未将 Token 写入仓库或日志。
- [x] 未将 API Key 写入仓库或日志。
- [x] 仅记录了无敏感值的配置状态。

## 完成验收

- [x] 可按主题、地区和时间范围检索公开公告。
- [x] 返回符合 DATA_CONTRACT 的 `TenderNotice`。
- [x] 保存来源 URL、发布时间、正文、采购人和附件链接。
- [x] 保存原始来源信息和带时区抓取时间。
- [x] 正确处理分页、空结果、超时和页面结构变化。
- [x] fixture 解析测试通过。
- [x] 不硬编码比赛示例。
- [x] 不绕过验证码或网站访问限制。
- [x] 所有改动都在声明文件范围内。
- [x] 改动文件和验证结果已记录。
- [x] 已完成安全检查。
