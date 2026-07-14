# BidRadar-X

BidRadar-X 是面向投标方和招标方的可解释招投标情报工作台。投标方可以用自然语言发起真实公告检索、查看项目与历史报告并下载 DOCX；招标方能力将基于有证据的历史项目做预算区间估计和供应商发现。系统的底线是保留来源与字段证据，不把 fixture、猜测或无依据的精确数字冒充真实结果。

## 当前 GitHub 入口

当前可信开发与交接分支是：

```text
recovery/c01-local-project-20260715
```

首次接手请使用：

```powershell
git clone --branch recovery/c01-local-project-20260715 https://github.com/lshhhhhhhhhh10/BidRadar-X.git BidRadar-X
```

远端默认分支 `main` 与当前本地恢复历史没有共同祖先，仍保留比赛报名与协作基线的旧内容。最新代码、路线图和本 README 已发布到上述恢复/交接分支，但**尚未合并到 `main`**。在团队决定正式主线前，不得 force push、覆盖 `main` 或自动合并无关历史。

## 当前项目进度

更新时间：2026-07-15（Asia/Shanghai）

### 已完成－真实黑盒验证

| 能力 | 已实现结果 | 边界 |
|---|---|---|
| C01 | 路线图、团队交接、GitHub 协作说明和模板 | 已从真实远端分支 fresh clone 验证 |
| I03 | 持久化定时任务 | 可保存并执行 daily/weekly/once 任务 |
| I04 | 自然语言调度解析 | 后端可把中文频率转换为订阅；首页尚未直接接入 |
| W03 | 首页、项目列表、详情、报告历史和 DOCX 下载链路 | TASK-10 完成的是产品下载链路，不是整个产品 |

### 已完成－自动测试验证

| 能力 | 已实现结果 | 边界 |
|---|---|---|
| F01 | CCGP 正式来源、合规采集和证据契约 | 契约已完成，不等于 R01 生产采集门禁已满足 |
| F02 | 版本化迁移、溯源模型和存储可靠性底座 | 新存储接口尚未在生产工作流全程接线 |
| I01 | 项目快照、来源水位线和新项目识别 | 复杂变化和恢复仍由 I02 完成 |
| W01/W02 | DOCX 内容契约、生成器和文档校验 | 报告内容完整度仍依赖真实附件和字段证据 |

### 部分完成或外部阻塞

| 能力 | 状态 | 当前已有 | 仍缺什么 |
|---|---|---|---|
| R01 CCGP | 部分完成 | 生产适配器、fixture 测试、历史真实抓取 | 全局限速、缓存重试、完整证据、运行持久化和正式黑盒门禁 |
| R03 文档解析 | 部分完成 | CCGP/GGZY HTML 解析样板 | 真实附件、PDF、扫描件 OCR 和解析失败分类 |
| R04 GGZY | 部分完成 | 生产适配器和 fixture 测试 | 尚无成功真实网络证据 |
| R05 登录来源 | 外部条件阻塞 | 剑鱼离线解析和会话安全边界 | 缺合法授权/API/可用凭据 |
| N01/N02/D01/I02 | 部分完成 | 字段、词法证据、相似归并和变化规则样板 | 真实附件证据、跨站标注、资格/技术变化和完整恢复验收 |
| Q01 | 部分完成 | CCGP→DOCX→网页下载曾单次跑通 | 多来源、附件、重复性、部署和失败路径尚未形成比赛级 E2E |

### 尚未开始的主要产品能力

- `W04`：Word 预览、报告时间线和更新提醒。
- `L01`：企业画像分步骤向导。
- `L04`：企业知识库、飞书资料、文档索引和真正的企业 RAG。
- `L05/L06`：资质覆盖或等价判断、企业能力匹配、历史价格、利润和商业决策。
- `L02/L03`：招标方预算区间、置信度和潜在供应商发现。
- `M01`：完整 Demo、设计/操作/部署文档、报名材料和演示素材。

当前唯一关键路径入口仍是 **R01：CCGP 公开来源生产加固**。详细依赖、证据和 76 项功能盘点以 [ROADMAP](docs/ROADMAP.md) 和 [WORK_PLAN](docs/WORK_PLAN.md) 为准。

## 历史 TASK 去向

- `TASK-01`～`TASK-10` 已作为历史执行编号保留，分别完成数据契约、CCGP/GGZY/登录来源样板、DOCX、纵向集成、增量、调度、自然语言订阅和产品下载链路。
- 原 `TASK-11 企业画像向导` → `L01`。
- 原 `TASK-12 企业知识库与 RAG` → `L04`。
- 原 `TASK-13 预算估计与供应商推荐` → `L02/L03`。
- 原 `TASK-14 Demo 与比赛材料` → `Q01/Q02/M01`。
- `F01/F02` 是对既有样板追加的正式契约和生产加固，不是从头重写项目。

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
