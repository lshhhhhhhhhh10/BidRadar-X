# C01：路线图、团队交接与 GitHub 协作治理

负责人/窗口：C01 项目架构梳理与团队交接窗口

开始时间：2026-07-15（Asia/Shanghai）

状态：已完成－真实黑盒验证（远端发布结果以分支 SHA 比对为准）

## 声明的文件范围

- `README.md`
- `docs/PROJECT_CONTEXT.md`
- `docs/WORK_PLAN.md`
- `docs/ROADMAP.md`
- `docs/TEAM_HANDOFF.md`
- `docs/GITHUB_WORKFLOW.md`
- `docs/worklogs/C01-roadmap-handoff.md`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `.github/ISSUE_TEMPLATE/feature-task.md`

明确不修改 `app/`、`lib/`、`backend/app/`、`backend/tests/`、`tests/`、依赖、数据库、迁移、来源适配器、前端、调度器和 DOCX 生产实现。

## 阶段 1：Git 与 GitHub 基线

编辑前执行：

```text
git status --short --branch
git log --oneline --decorate --graph --all
git branch -vv
git remote -v
git rev-parse HEAD
git diff
git diff --check
```

结果：

- 初始分支 `recovery/task-08-baseline`，工作区干净，无 upstream。
- 初始 HEAD `b2cac4befb3874e0abd70f3a60854d8afb470aed`。
- 本地提交：`169698c → 410384d → c3764e0 → eaafca6 → b2cac4b`。
- `origin` 为 `https://github.com/lshhhhhhhhhh10/BidRadar-X.git`；配置 origin 本身不作为已上传证据。
- `gh` 未安装；GitHub connector 没有返回可用仓库/权限详情。
- 首次 sandbox 内 `git fetch` 因 `.git/FETCH_HEAD` 权限失败；经正常权限批准后 `git fetch origin --prune` 成功，没有降低 TLS 或写入凭据。
- 远端默认分支 `main`，远端 HEAD `37a87bb95770c56daac8282f111ea9a97d3ba15c`，提交标题 `docs: establish application and collaboration baseline`。
- `git merge-base HEAD origin/main` 退出码 1、无 merge-base。调查时本地独有 5 个提交，远端独有 1 个提交；两边 root 分别为 `169698c` 和 `37a87bb`。
- 分类为“情况 C：历史不相关”。不 force push、不合并无关历史、不覆盖 `main`、不创建无法正常比较的 PR。
- 远端当时没有同名 C01/恢复分支。
- 从可信本地 HEAD 创建 `recovery/c01-local-project-20260715`，所有 C01 修改在该分支完成。
- 无认证公共 GitHub API 返回 404，而认证 Git 读取成功，故只能推测仓库为私有；当前无法用连接器可靠确认可见性、维护权限或 collaborator 状态。

## 阶段 2：完整阅读与代码核验

完整阅读：

- `README.md`、`docs/PROJECT_CONTEXT.md`、`docs/WORK_PLAN.md`
- `docs/DATA_CONTRACT.md`、`docs/REPORT_FORMAT.md`、`docs/SOURCE_CCGP.md`、`docs/LOGIN_SOURCE_SETUP.md`
- `docs/worklogs/README.md`
- `TASK-01`～`TASK-10` 全部工作日志
- `F01-public-source-contract.md`、`F02-migratable-storage.md`

检查生产与测试目录：`app/**`、`lib/**`、`backend/app/api/**`、`schemas/**`、`services/**`、`sources/**`、`storage/**`、`workflow/**`、`backend/tests/**`、`tests/**`。同时查看五个已知提交的文件范围与 root 历史。

关键核验：

- CCGP 有生产代码、fixture 测试和历史真实抓取，但未满足 F01 全部生产门禁。
- GGZY 有生产代码和 fixture 测试；日志中的真实网络验证失败，不能写成在线成功。
- 剑鱼只有离线解析与授权/会话边界；生产 collect 会拒绝未授权在线抓取。
- `AttachmentSource` 返回模拟附件正文；通用 `DocumentParser` 没有真实 PDF/OCR。
- F02 迁移/溯源存储接口自动测试充分，但新的 collection run 接口主要在测试中使用，生产工作流仍以旧快照/水位线/交付路径为主。
- 当前 `EvidenceRAG` 是本地词法与字符串相似检索，不是企业知识库 RAG。
- TASK-10 提供首页→项目→详情→报告历史→下载链路，不提供 Word 预览、订阅时间线、更新小紫点或企业入口，也不表示 Q01/Q02 完成。

## 阶段 3：编号冲突与遗漏功能

发现并修订：

- 旧 `TASK-*` 同时被当作历史批次和未来路线图编号，容易造成 TASK-10 后任务“消失”。今后只保留历史含义，正式能力统一使用 C/F/R/N/D/I/W/Q/L/M。
- 旧计划没有为第二公开来源 GGZY 提供清晰正式编号，新增 `R04`。
- 登录/授权来源需要独立边界，新增 `R05`。
- 原 TASK-12 企业知识库与 RAG 缺少正式条目，补为 `L04`。
- 原 TASK-14 的比赛材料不应只塞进 Q 验收，补为 `M01`。
- 原始构想中的 Word 预览/报告时间线/更新提醒补为 `W04`。
- 付款、质保、联合体、分包、评分等可信字段补为 `N03`。
- 企业能力匹配与资质覆盖/等价补为 `L05`；历史价格、利润与商业决策补为 `L06`。
- 原 TASK-11 → L01；原 TASK-13 → L02/L03；原 TASK-14 的真实链路/稳定性 → Q01/Q02，材料 → M01。

## 阶段 4：状态修订

- 保留 F01、F02、I01、W01、W02 的“已完成－自动测试验证”。
- 保留 I03、I04、W03 的“已完成－真实黑盒验证”。
- R01、R04、N01、N02、D01、I02、Q01 均降为或保持“部分完成”。
- R05 为“外部条件阻塞”。
- 不把 fixture、离线解析、一次真实链路或简单字符串相似检索写成完整产品能力。
- C01 在文档、自动检查、冷启动黑盒、提交、push 和远端 SHA 验证全部完成前保持进行中。

## 阶段 5：基线验证（编辑前）

Python 使用本地 Codex bundled runtime：
`C:\Users\lisihan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`。

1. 默认数据库后端全量：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH='.;.venv\Lib\site-packages'
& 'C:\Users\lisihan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s tests -p 'test_*.py' -v
```

在 `backend` 执行：111 个，105 通过、6 error；错误均为默认 `%TEMP%\TenderIntelligence\app.db` 的 migration 5 checksum mismatch。未删除或修改该数据库。

2. 过长隔离目录：125 个，124 通过、1 failure；报告 `.lock` 路径触发 Windows `FileNotFoundError`。

3. 短隔离目录（例如 `%TEMP%\bx244ee5`）：125 个，125 通过，耗时 6.321 秒。

4. `python -m compileall -q app tests`：通过，无输出；pycache 定向到临时目录。

5. `npm.cmd run lint`：通过，0 error；只有 npm 版本提示。

6. `npm.cmd test`：build 后 Node 测试 3 个，3 通过、0 失败；有 vinext 动态路由分类 warning 和 npm 版本提示。

7. `npm.cmd run build`：通过；同一 vinext warning。

8. `npx.cmd tsc --noEmit`：失败 3 项：
   - `db/index.ts(1,21)` 找不到 `cloudflare:workers`；
   - `worker/index.ts(6,11)` 找不到 `Fetcher`；
   - `worker/index.ts(7,7)` 找不到 `D1Database`。

测试生成的 `tsconfig.tsbuildinfo` 已删除；生产代码和测试代码未改。另有 Starlette deprecation warning 和 CCGP 预期“跳过不可解析条目”日志。

## 阶段 6：修改文件

- 更新：`README.md`、`docs/PROJECT_CONTEXT.md`、`docs/WORK_PLAN.md`。
- 新增：`docs/ROADMAP.md`、`docs/TEAM_HANDOFF.md`、`docs/GITHUB_WORKFLOW.md`。
- 新增协作模板：`.github/PULL_REQUEST_TEMPLATE.md`、`.github/ISSUE_TEMPLATE/feature-task.md`。
- 新增本日志。
- 未修改任何生产代码、测试代码、依赖、数据库或迁移。

## 阶段 7：编辑后验证

自动与静态检查：

- 后端使用短隔离目录 `%TEMP%\bx1386723957` 重跑完整 unittest：125 个，125 通过，耗时 4.950 秒；Starlette deprecation warning 和 CCGP 预期跳过日志仍存在。
- `python -m compileall -q app tests`：通过，无输出。
- `npm.cmd run lint`：通过，0 error。
- `npm.cmd test`：3 个，3 通过、0 失败；build 与 vinext 动态路由分类 warning 如基线。
- `npm.cmd run build`：通过；同一 vinext warning。
- `npx.cmd tsc --noEmit`：仍失败 3 项，文件/错误与编辑前完全一致；生成的 `tsconfig.tsbuildinfo` 已删除。
- 9 份新增/更新 Markdown 相对链接检查：0 个缺失。
- 原始 A-G 功能清单关键词逐项检查：76/76 已进入 ROADMAP 功能矩阵。
- ROADMAP 包含 TASK-01～10、原 TASK-11～14、L04、M01、R04、R05；WORK_PLAN/ROADMAP/TEAM_HANDOFF 的下一入口均为 R01。
- ROADMAP 中所有“已完成”矩阵行都使用非 E00 证据；修改范围只包含 C01 允许文件。
- 敏感值扫描检查 private key、GitHub/AWS token 格式、含凭据 URL 和 secret 赋值：0 个命中。

README/TEAM_HANDOFF 冷启动黑盒逐项结果：

1. 通过：README 可找到 ROADMAP、WORK_PLAN、TEAM_HANDOFF。
2. 通过：TEAM_HANDOFF 可理解产品目标和投标方/招标方场景。
3. 通过：可找到本地/远端 SHA、分支和“历史不相关”分类。
4. 通过：可找到环境与前后端启动命令。
5. 通过：可找到后端、lint、前端测试、build 和 TypeScript 命令。
6. 通过：明确 CCGP 有历史真实抓取、GGZY 只有 fixture 成功证据。
7. 通过：明确剑鱼受授权阻塞，附件/PDF/OCR 未完成。
8. 通过：可找到原 TASK-11～14 到 L01/L04/L02-L03/Q01-Q02/M01 的映射。
9. 通过：当前唯一下一入口为 R01。
10. 通过：文档明确不依赖聊天，并给出新 Codex 前 30 分钟只读审阅与基线步骤。

提交前 Standards/Spec 双轴只读审查发现并已修复：

- README 的 TEAM_HANDOFF 环境章节锚点缺少 `6-` 前缀。
- TASK-07、TASK-10、原 TASK-14 映射使用了非标准复合状态，已拆成七种状态词的明确组合。
- GitHub 流程误把“C01 不能向无关的 `main` 建 PR”扩大为“后续功能也不能建 PR”；已明确后续同源功能分支可把恢复分支作为 base 建 Draft PR，并补充 GitHub 网页步骤。
- 审查指出 C01 “远端可信”只能在 commit、push、upstream 和 SHA 比对后成立；该项保留为 Git 收口硬门禁，发布失败时必须降级文档状态，不能宣称完成。

## 阶段 8：GitHub 发布与最终提交

提交主题：`docs: reconcile roadmap and team handoff`

本地/远端分支：`recovery/c01-local-project-20260715`

历史不相关，因此不创建 Draft PR、不自动合并，也不改变远端 `main`。发布后以 `git rev-parse HEAD` 和 `git ls-remote origin recovery/c01-local-project-20260715` 的 SHA 完全一致为上传成功标准；准确 SHA 和 push 输出记录在 C01 最终回执。

提交不能在自身内容中写入自己的最终 SHA（写入会改变 SHA）；本日志用分支 tip、提交主题和验证命令唯一标识，最终 C01 回执报告准确本地/远端 SHA。

## 未完成项

- R01 及后续业务能力均未在 C01 中实现。
- 远端 `main` 与本地恢复历史的正式集成策略待用户决定。
- 分支保护、GitHub Actions/CI 和 collaborator 邀请/权限尚未可靠确认或配置。
- 真实来源、附件/PDF/OCR、资格/商业分析、企业画像/RAG、预算/供应商和比赛材料缺口见 ROADMAP。
