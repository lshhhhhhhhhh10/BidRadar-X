# BidRadar-X

BidRadar-X 是面向投标方和招标方的可解释招投标情报工作台。投标方可以用自然语言发起真实公告检索、查看项目与历史报告并下载 DOCX；招标方能力将基于有证据的历史项目做预算区间估计和供应商发现。系统的底线是保留来源与字段证据，不把 fixture、猜测或无依据的精确数字冒充真实结果。

当前仓库已经具备 CCGP/GGZY 来源样板、统一数据契约、增量与调度、DOCX 生成、项目详情及报告下载链路；生产级来源契约、附件/PDF/OCR、跨站归并、企业能力和招标方高级能力仍未完成。准确状态以 [ROADMAP](docs/ROADMAP.md) 为准。

## 新队员从这里开始

1. 阅读 [TEAM_HANDOFF](docs/TEAM_HANDOFF.md)，先理解产品、架构、Git 基线、已知阻塞和下一入口。
2. 阅读 [ROADMAP](docs/ROADMAP.md)，核对原始构想、旧 TASK 与新能力编号的完整映射。
3. 阅读 [WORK_PLAN](docs/WORK_PLAN.md)，只从依赖已满足的正式能力编号开始新任务。
4. 按 [GITHUB_WORKFLOW](docs/GITHUB_WORKFLOW.md) 使用独立分支、工作日志和 Draft Pull Request 协作。
5. 所有历史与当前工作日志见 [docs/worklogs/README.md](docs/worklogs/README.md)。C01 的调查证据见 [C01-roadmap-handoff](docs/worklogs/C01-roadmap-handoff.md)。

不要依赖历史聊天判断完成度，也不要继续创建含义模糊的 `TASK-11`、`TASK-12` 等未来编号。旧 `TASK-01`～`TASK-10` 只保留为历史执行编号，今后统一使用 C/F/R/N/D/I/W/Q/L/M 能力编号。

## 快速启动（Windows PowerShell）

要求 Node.js `>=22.13.0` 和 Python 3.11+。

```powershell
npm.cmd install
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
$env:TENDER_DATA_DIR = Join-Path $env:LOCALAPPDATA "BidRadar-X\data"
npm.cmd run dev
```

前端默认访问 `http://localhost:3000`，FastAPI 默认访问 `http://127.0.0.1:8000`。请使用较短的 `TENDER_DATA_DIR`，并避免复用迁移校验和不匹配的旧本地数据库；详见 [TEAM_HANDOFF](docs/TEAM_HANDOFF.md#6-环境准备与启动)。

## 基线验证

```powershell
# 后端：切换到 backend 目录，并使用一个新的短路径测试数据目录
Push-Location backend
$env:TENDER_DATA_DIR = Join-Path $env:TEMP ("bx" + (Get-Random))
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.\.venv\Scripts\python.exe -m compileall -q app tests
Pop-Location

# 前端：在仓库根目录执行
npm.cmd run lint
npm.cmd test
npm.cmd run build
npx.cmd tsc --noEmit
```

当前基线中 `npx.cmd tsc --noEmit` 存在 3 个 Cloudflare 环境类型错误；默认旧数据库也可能触发迁移校验和错误。这些是已记录的环境/基线问题，不应在文档任务中被掩盖。

## 核心文档

- [PROJECT_CONTEXT](docs/PROJECT_CONTEXT.md)：产品边界与事实来源。
- [DATA_CONTRACT](docs/DATA_CONTRACT.md)：公告、证据和报告的公共契约。
- [REPORT_FORMAT](docs/REPORT_FORMAT.md)：DOCX 输出结构。
- [SOURCE_CCGP](docs/SOURCE_CCGP.md)：CCGP 正式来源契约。
- [LOGIN_SOURCE_SETUP](docs/LOGIN_SOURCE_SETUP.md)：登录来源授权边界。
