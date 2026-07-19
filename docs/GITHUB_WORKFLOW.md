# BidRadar-X GitHub 协作与分支规范

更新时间：2026-07-19（Asia/Shanghai）

适用仓库：<https://github.com/lshhhhhhhhhh10/BidRadar-X>

## 当前分支结构

- `main`：唯一正式主线，评委和新开发者默认克隆此分支。
- `agent/*`、`feat/*`、`fix/*`、`docs/*`：短期开发分支，通过 Pull Request 合并到 `main`。
- `archive/*`：只读历史快照，不作为新工作的开发基线。

旧的恢复分支已经完成主线迁移。禁止继续把 `recovery/*` 当作当前入口，也不需要 `--allow-unrelated-histories` 或 force push。

## 首次克隆

```bash
git clone https://github.com/lshhhhhhhhhh10/BidRadar-X.git
cd BidRadar-X
git remote -v
git branch -vv
```

如果私有仓库返回 404，先确认当前 GitHub 账号已被授权；不要把 Token 写入 remote URL、源码或聊天记录。

## 开始新任务

```bash
git status --short --branch
git fetch origin --prune
git switch main
git pull --ff-only
git switch -c feat/short-description
```

工作区不干净时先确认每项修改的归属，不要用 `git reset --hard` 或强制覆盖队友工作。

## 分支与提交命名

推荐分支：

- `feat/<能力>-<名称>`
- `fix/<能力>-<名称>`
- `docs/<名称>`
- `agent/<交付名称>`

推荐提交：

- `feat(scope): ...`
- `fix(scope): ...`
- `docs(scope): ...`
- `test(scope): ...`
- `refactor(scope): ...`

避免 `final`、`final2`、`new`、`update`、`fix bug` 等不可审计名称。

## 提交前门禁

1. `git diff --check` 无空白错误。
2. 后端全量测试通过。
3. 前端构建和渲染测试通过。
4. `.env`、Token、API Key、数据库、报告和本地日志没有进入暂存区。
5. README 与真实功能一致，明确写出需凭据和未完成边界。

推荐命令：

```bash
cd backend
.venv/bin/python -m unittest discover -s tests -q
cd ..
npm test
git diff --check
git status --short
```

## 暂存与推送

优先显式暂存任务文件。只有确认整个工作区都属于同一交付时，才使用 `git add -A`。

```bash
git add path/to/file ...
git diff --cached --stat
git diff --cached --check
git commit -m "feat(scope): describe outcome"
git push -u origin HEAD
```

禁止对协作分支和 `main` 使用 `--force` 或 `--force-with-lease`。

## Pull Request

默认创建 Draft PR，base 统一为 `main`。PR 至少说明：

- 修改了什么；
- 为什么修改；
- 用户或评委能看到什么；
- 根因与失败路径；
- 自动测试和黑盒验证；
- 需要的凭据、迁移和明确未完成项。

合并后删除已经完成的短期开发分支；`archive/*` 保留作为历史证据。没有审查和测试结果时不直接推送 `main`。

## 敏感信息规则

- 真实密钥只放 `backend/.env` 或部署平台 Secret。
- `.env.example` 只能包含空值和说明。
- 前端禁止出现 `NEXT_PUBLIC_*` 形式的 AI/API 密钥。
- Git 历史中若发现密钥，应立即吊销密钥；仅删除最新文件不能清除历史泄露。
