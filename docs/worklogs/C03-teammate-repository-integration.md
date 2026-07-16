# C03 队友仓库改动整合

- 更新时间：2026-07-16（Asia/Shanghai）
- 状态：已验证，PR #6 待审阅合并
- 负责人/窗口：Codex `integration-feishu`
- 基线：`origin/main`（`3b410d3fdf319b7cb862f7b18efea74e153317f6`）
- 来源：`DzSexton/feishu-` 的 `main`（`cf5d0daeedb5477e24628aa480bb2341831893a3`）
- 依赖：基于当前远端 main 独立集成；不依赖尚未合并的 C02 PR

## 目标与边界

队友仓库是通过网页上传形成的独立历史，不能安全地整体 merge 或 cherry-pick。本次逐文件比较并移植产品改动，不纳入运行日志、生成的 DOCX、截图、重复上下文、含队友本机路径的 QA 记录或 Agent skills。

CEB 与上海公共资源交易两个采集器仅作为实验模块和测试保留。它们未注册进生产 source registry，也不改变主线现有 CCGP、GGZY、Jianyu 采集链。上海物业页面和接口使用明确标记的合成演示数据，不绑定真实公告 URL，不得作为真实证据。

## 纳入文件

### 前端与公共资源

- `.gitignore`
- `app/globals.css`
- `app/page.tsx`
- `app/projects/page.tsx`
- `app/projects/[projectId]/page.tsx`
- `app/marked-projects/[projectId]/page.tsx`
- `app/reports/demo-shanghai-property/page.tsx`
- `app/reports/demo-shanghai-property/page.module.css`
- `lib/tender-api.ts`
- `lib/demo-tenders.ts`
- `lib/marked-projects.ts`
- `lib/mock-requirements-parser.ts`
- `public/assets/word-report-thumbnail.png`
- `package-lock.json`
- `tests/rendered-html.test.mjs`

### 后端、测试与启动脚本

- `backend/app/api/projects.py`
- `backend/app/api/reports.py`
- `backend/app/api/tasks.py`
- `backend/app/schemas/task.py`
- `backend/app/schemas/tender.py`
- `backend/app/schemas/workflow.py`
- `backend/app/services/demo_shanghai_property.py`
- `backend/app/services/docx_publisher.py`
- `backend/app/services/task_runner.py`
- `backend/app/sources/ceb.py`
- `backend/app/sources/shanghai_ggzy.py`
- `backend/app/workflow/nodes/requirement.py`
- `backend/run.py`
- `backend/tests/__init__.py`
- `backend/tests/test_api.py`
- `backend/tests/test_ceb_source.py`
- `backend/tests/test_demo_shanghai_property_report.py`
- `backend/tests/test_product_chain.py`
- `backend/tests/test_requirement_overrides.py`
- `backend/tests/test_shanghai_ggzy_source.py`
- `scripts/start-backend-detached.ps1`
- `scripts/start-dev-detached.ps1`
- `scripts/start-frontend-detached.ps1`

### 文档

- `docs/SOURCE_OFFICIAL_TENDER_RESEARCH.md`
- `docs/adr/0001-trust-source-taxonomy-and-active-state.md`
- `docs/worklogs/C03-teammate-repository-integration.md`

## 审查与修正

- 两轴代码审查发现演示数据曾把合成预算、资质和评分字段绑定真实公告 URL；已改为 `example.invalid`、零权威度和显式“合成演示”标记。
- 两个新增采集器尚缺生产级生命周期覆盖、页面挑战检测与完整持久化，故保持未注册状态。
- 恢复主线生产来源注册表与精确回归测试，避免替换 CCGP/GGZY。
- DOCX 输出保留技术要求兼容标题、字段证据引用、定位与链接；缺证据明确显示“无”。
- 启动脚本不再依赖固定的本机 Python/npm 路径。

## 验证结果

- 后端：`python -m unittest discover -s backend/tests -t backend -v`，134/134 通过。
- 后端语法：`python -m compileall -q backend/app backend/tests`，通过。
- 前端 lint：`eslint . --ignore-pattern dist --ignore-pattern .next`，通过。
- 前端生产构建：`vinext build`，通过。
- 页面渲染回归：`node --test tests/rendered-html.test.mjs`，3/3 通过。
- `tsc --noEmit` 仍报告主线已有的 `cloudflare:workers`、`Fetcher` 与 `D1Database` 类型缺口；`db/index.ts`、`worker/index.ts` 在本分支相对 main 无变化，不列为本次回归。
- `git diff --check`，通过（仅出现 Git 的 CRLF 转换提示）。

## 安全检查

- [x] 未将账号、Cookie、Token 或 API Key 写入仓库。
- [x] 未纳入队友仓库中的运行日志、生成 DOCX、截图或本机临时路径记录。
- [x] 实验数据源未接入生产采集链。
- [x] 演示数据与真实公告证据彻底隔离。
- [x] 推送前完成最终敏感信息扫描（未发现高风险凭据模式）。

## 完成验收

- [x] 所有改动都在上述声明范围内。
- [x] 专项测试与完整回归通过。
- [x] 前后端在本地启动并通过健康检查（前端 200，后端 `/api/health` 200）。
- [x] 已推送 `integration-feishu` 并创建 PR #6。
