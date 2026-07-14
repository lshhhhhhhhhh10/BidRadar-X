# TASK-06 真实链路集成

- 更新时间：2026-07-14（Asia/Shanghai）
- 状态：公开来源闭环已完成；登录来源受外部授权阻塞
- 负责人/窗口：Codex TASK-06 窗口
- 依赖任务：TASK-01 数据契约、TASK-02 CCGP、TASK-03 GGZY、TASK-04 登录来源实验、TASK-05 DOCX
- 声明文件范围：
  - `backend/app/workflow/**`
  - `backend/app/sources/__init__.py`
  - `backend/app/services/publisher.py`
  - `backend/requirements.txt`
  - `backend/app/api/**`
  - `backend/tests/**`
  - `docs/worklogs/TASK-06-integration.md`
- 明确不修改：前端页面及上述范围外文件

## 阶段记录

### 2026-07-14 — 阶段 1：上下文、适配器与集成边界核对

#### 已完成

- 阅读项目上下文、统一数据契约、TASK-02 至 TASK-05 工作日志、三个新增真实/登录适配器及其测试、DOCX 发布器与现有工作流/API 测试。
- 确认生产路由仍使用 `PublicPlatformSource`、`EnterprisePortalSource`、`CommercialPlatformSource` 三个 `example.local` 模拟适配器。
- 确认真实公开来源为 CCGP 与 GGZY；剑鱼来源属于真实登录型来源，但依据 TASK-04 的授权结论，在线采集必须保持明确失败，不能把离线 fixture 或普通会员会话伪装为生产成功。
- 确认集成测试公共边界为工作流入口、任务 API 与报告工件；来源单元测试继续覆盖适配器契约。

#### 集成决策

- 生产注册表只包含 CCGP、GGZY 和剑鱼登录来源，不删除旧模拟适配器文件，但生产路径不导入它们。
- 多来源采集使用逐来源结果隔离；一个来源异常不会取消其他来源，API 明确返回成功和失败来源。
- 工作流内部保留可 JSON 序列化的 `TenderNotice` 契约数据，DOCX 只从这些真实采集字段生成；不调用固定项目模板生成报告内容。
- 剑鱼在未获得书面授权前作为“已接入但失败关闭”的登录来源出现，失败不会阻断两个公开来源。

#### 验证结果

- 当前根目录 `.git` 目录缺少可解析的 `HEAD`，`git status` 报告不是有效仓库；暂不初始化或修改 Git 元数据。
- `backend/requirements.txt` 尚未声明 TASK-05 所需的 `python-docx`。

#### 下一步

- 先补真实来源注册、失败隔离、DOCX 与 API 契约测试并确认红灯，再逐个完成实现。

### 2026-07-14 — 阶段 2：真实来源、失败隔离与 DOCX API 接线

#### 已完成

- 先新增工作流/API 端到端测试并确认红灯：生产注册函数缺失，原工作流仍不能返回 DOCX 来源汇总。
- 新增生产来源注册表，只创建 CCGP、GGZY 与剑鱼登录来源；旧 `example.local` 适配器文件保留，但生产模块不再导入。
- 将自然语言需求转换为 `TaskSpec`，支持显式 `YYYY-MM-DD` 日期和默认最近 30 天窗口，并向真实适配器传递规范化地区、主题和检索计划。
- 多源并发采集增加逐来源 60 秒上限、契约校验和异常隔离；成功来源的 `TenderNotice` 转为可序列化工作流文档，失败来源保留类型和非敏感错误说明。
- 来源结果写回 `selected_sources`，避免 LangGraph 状态模式丢弃未声明键；报告/API 可返回来源总数、成功来源、失败来源与命中数。
- 去重项目改用项目稳定指纹生成跨运行稳定的 `project_id`；DOCX 从每个去重项目的真实 `TenderNotice` 中选择权威主记录生成，不使用固定项目模板。
- 将工作流发布器替换为 `DocxPublisher` 桥接，并补充 URL 编码的下载地址、DOCX 格式、公告数与来源汇总。
- `backend/requirements.txt` 增加 `python-docx>=1.2,<2.0`；任务 API 不再调用会补造模拟字段的 `build_project_profiles`。

#### 验证结果

- 定向测试：`python -m unittest tests.test_integration tests.test_api -v`，3/3 通过。
- 覆盖：生产注册表无 demo 源、至少一个登录来源、登录来源失败隔离、两公开来源成功、跨源去重、真实字段 DOCX、API 来源汇总和静态下载。
- 仅出现既有 Starlette/httpx 弃用警告，不影响结果。

#### 下一步

- 更新旧工作流测试以使用真实契约来源替身，运行全部适配器、DOCX、工作流和 API 测试，再进行双轴代码审查。

### 2026-07-14 — 阶段 3：完整回归、重复运行与真实网络烟测

#### 已完成

- 将旧工作流测试迁移到真实 `TenderNotice` 契约来源替身，避免测试套件访问外网或依赖 `example.local`。
- 为重复运行增加唯一工件名：DOCX 先在按 `run_id` 隔离的暂存目录生成并回读验证，再移动为带短运行 ID 的最终文件；Word 内仍保留原始用户查询。
- API 回归覆盖同一分钟重复执行同一查询，两个 DOCX 文件名不同且都可下载。
- 完成生产路径 demo 引用扫描、凭据值扫描与 Python 编译检查。

#### 验证结果

- 后端完整测试：`python -m unittest discover -s tests -p 'test_*.py' -v`，46/46 通过。
- 语法检查：`python -m compileall -q backend/app/workflow backend/app/sources/__init__.py backend/app/services/publisher.py backend/app/api backend/tests`，通过。
- 生产路径扫描：`backend/app/workflow`、`backend/app/sources/__init__.py`、`backend/app/services/publisher.py`、`backend/app/api` 中无 `example.local` 和三个旧模拟类引用。
- 凭据扫描：TASK-06 改动范围内未发现内嵌 Cookie、Token、API Key 或密码值。
- 真实网络烟测 1：`查询 2026-07-14 全国服务器采购公告` 完成并生成可验证 DOCX；CCGP 成功返回 0 条，GGZY 网络请求失败，剑鱼因未配置外部会话且授权关闭而失败；来源汇总为 1 成功、2 失败，任务未崩溃。
- 真实网络烟测 2：`最近1个月全国服务器招标信息` 得到相同的来源可用性结果并生成空结果 DOCX，证明当前环境下失败隔离和空结果交付有效；不把 0 条结果宣称为真实命中。
- 当前根目录 `.git` 仍无有效 `HEAD`，不能生成基线 diff 或提交；未修改 Git 元数据。

#### 下一步

- 完成 Standards / Spec 双轴只读审查，修复发现后再次运行完整测试并收口日志。

### 2026-07-14 — 阶段 4：双轴审查修复与最终验证

#### 已完成

- 完成 Standards / Spec 双轴只读审查；因 `.git` 无有效 `HEAD`，审查以 TASK-06 当前文件集合代替基线 diff。
- 将采集、标准化和筛选节点改为只传递 `TenderNotice` 契约 JSON，并在节点边界重新校验，不再维护一套可能漂移的自由公告字典。
- 项目归并改为按 `project_stable_fingerprint` 分组，并以 `notice_stable_fingerprint` 区分生命周期事件和跨站镜像。
- DOCX 每个公告生命周期只保留一条权威主记录，同时把该事件的全部真实发布来源写入 `reference` 章节和字段级证据，既去镜像又保留来源可追溯性。
- 发布器只报告 `changes` 中的新项目/实质变化；无变化的重复运行复用已有工件，不重复生成或发送相同事件。
- 工件名和复用条件包含完整稳定 `task_id`；同查询不同频率或长查询前缀相同的任务不会跨任务误复用。
- 交付工件使用由 `task_id`、交付类型、项目/公告稳定指纹和规范化变化内容计算的 `delivery_fingerprint`；确定性文件名和排他 `.lock` 保证并发相同交付只生成一个 DOCX，竞争运行复用同一工件。
- 全来源失败时任务状态为 `failed`，API 返回失败来源汇总且 `filename/download_url` 为 `null`，不生成伪成功 DOCX。
- 修复适配器注册表双重绑定，测试只需替换一个来源注册缝；新增全来源失败和重复运行工件复用回归。

#### 最终验证

- 后端完整测试：47/47 通过。
- 编译、生产路径 demo 引用扫描和凭据扫描通过；仅有既有 Starlette/httpx 弃用警告。
- 真实查询 `采购`：CCGP 实际采集 15 条，`raw=15`、`normalized=15`、`relevant=15`、`projects=15`，质量检查通过，生成并回读验证包含 15 条公告的 DOCX。
- 同次真实查询中 GGZY 网络请求失败、剑鱼未配置外部会话；两者均作为失败来源返回，未中断 CCGP 闭环。

#### 未解除阻塞

- 剑鱼 `collect()` 依据 TASK-04 的许可审查必须保持在线拒绝；当前没有平台书面自动化授权或已签约官方 API，因此不能诚实宣称“登录来源真实采集成功”。生产注册和失败隔离已接入，但登录来源成功验收仍受外部授权阻塞。
- 未绕过验证码、登录限制或平台条款，也未把离线 fixture 计作真实成功。解除条件：取得书面授权或合法 API 凭据后，在独立任务中实现并实测在线采集。
- `.git` 目录没有有效仓库元数据，无法按实现技能创建提交；未擅自初始化或修复 `.git`。

## 可复制的真实查询验证命令

后端运行于 `http://127.0.0.1:8000` 时执行：

```powershell
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/tasks/run' -ContentType 'application/json; charset=utf-8' -Body (@{ query = '采购'; frequency = 'once' } | ConvertTo-Json)
```

响应的 `report` 包含 `filename`、`download_url`、`source_count`、`successful_sources`、`failed_sources`、`notice_count`、`delivery_fingerprint` 和是否复用既有工件的 `reused_artifact`。

## 安全检查

- [x] 未将账号、Cookie、Token 或 API Key 写入仓库或日志。
- [x] 登录来源只记录配置项名称与授权状态，不记录凭据值。
