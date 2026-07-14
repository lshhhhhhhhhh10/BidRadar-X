# BidRadar-X 双人 GitHub 协作流程

更新时间：2026-07-15（Asia/Shanghai）

适用仓库：`https://github.com/lshhhhhhhhhh10/BidRadar-X`

当前可信恢复/交接分支：`recovery/c01-local-project-20260715`

> 当前本地恢复历史与远端 `main` 没有共同祖先。不要直接合并、force push 或运行 `git merge --allow-unrelated-histories`。在团队明确决定正式主线前，新队员应从上面的恢复/交接分支克隆和核验。

## 1. GitHub 在本项目中负责什么

GitHub 保存代码、文档和提交历史，让两台电脑同步；分支把不同任务隔开；Pull Request（PR）让另一名队员在合并前查看差异、测试和风险；出错时可以回到已知提交。

GitHub 不能代替工作日志和自动测试。聊天也不是项目事实源：完成状态必须写进 WORK_PLAN/ROADMAP、工作日志、提交和 PR。

## 2. 第一次克隆

不要把 ZIP 当作长期协作方式。仓库访问授权完成后，在 PowerShell 执行：

```powershell
git clone --branch recovery/c01-local-project-20260715 https://github.com/lshhhhhhhhhh10/BidRadar-X.git BidRadar-X
Set-Location BidRadar-X
git remote -v
git branch -vv
git rev-parse HEAD
git config --get user.name
git config --get user.email
git ls-remote origin recovery/c01-local-project-20260715
```

最后两条输出的 SHA 必须一致。若私有仓库返回 404 或认证失败，请仓库所有者在 GitHub 邀请准确用户名；不要共享 Token/密码，也不要关闭 TLS。

`user.name` 和 `user.email` 只决定提交作者，不是登录凭据。每名学生应使用自己的 GitHub 用户名/显示名和 GitHub 已验证邮箱或 GitHub noreply 邮箱；不要沿用恢复仓库的 `bidradar-x@local.invalid`，也不要把 Token 填进 email 或 remote URL。

安装依赖和运行基线：

```powershell
npm.cmd install
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt

Push-Location backend
$env:TENDER_DATA_DIR = Join-Path $env:TEMP ("bx" + (Get-Random))
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.\.venv\Scripts\python.exe -m compileall -q app tests
Pop-Location

npm.cmd run lint
npm.cmd test
npm.cmd run build
npx.cmd tsc --noEmit
```

已知基线见 [TEAM_HANDOFF](TEAM_HANDOFF.md#7-自动测试命令与已知基线)，不能因为已知 TypeScript 错误而跳过记录。

## 3. 每天开始工作

```powershell
git status --short --branch
git fetch origin --prune
git branch -vv
git log --oneline --decorate --graph --all
```

如果有不属于自己的未提交修改，先停止并找文件负责人，不能覆盖。确认工作区干净后，从团队最新确认的可信远端分支建立新的能力分支；在正式主线尚未决定时，基于恢复分支：

```powershell
git switch recovery/c01-local-project-20260715
git pull --ff-only
git switch -c feat/r01-ccgp-collector
```

`pull --ff-only` 被拒绝时说明历史发生分叉，停止并比较双方提交，不要用 reset 或 force 解决。

## 4. 分支命名

统一使用：

- `feat/<能力编号>-<简短名称>`
- `fix/<能力编号>-<简短名称>`
- `docs/<能力编号>-<简短名称>`
- `test/<能力编号>-<简短名称>`

示例：

- `feat/r01-ccgp-collector`
- `feat/r02-attachment-download`
- `docs/c01-roadmap-handoff`
- `fix/w03-report-download`

不要使用 `new`、`test`、`final`、`final2`、`my-branch`、`teammate`、`task11`。旧 TASK 编号不是未来能力编号。

## 5. 开发过程

1. 一个能力一个 Codex 任务，一个能力一个 Git 分支。
2. 从 [worklogs/TEMPLATE.md](worklogs/TEMPLATE.md) 创建独立日志，先声明能力 ID、负责人/窗口和文件范围。
3. 运行基线并记录准确命令、通过/失败数和警告。
4. 业务实现任务先写测试并真实运行出预期红灯，再写生产实现；不得只声称 TDD。
5. 只修改日志声明的文件。需要扩大范围时先记录并确认无人重叠。
6. 运行本任务测试、全量回归、黑盒、失败路径和敏感信息扫描。
7. 更新工作日志和 WORK_PLAN/ROADMAP 中由协调人负责的状态。
8. `git diff` 逐文件审查，只暂存本任务文件，创建清晰提交。

## 6. 提交规范

推荐格式：

- `feat(scope): ...`
- `fix(scope): ...`
- `docs(scope): ...`
- `test(scope): ...`
- `refactor(scope): ...`

示例：

- `feat(r01): harden CCGP public collection`
- `fix(w03): reject missing report artifacts`
- `docs(c01): reconcile roadmap and handoff`

提交说明描述结果和范围。不要只写 `update`、`修改`、`final`、`test`、`fix bug`。

安全暂存示例：

```powershell
git status --short
git diff --check
git add backend/app/sources/ccgp.py backend/tests/test_ccgp.py docs/worklogs/R01-public-source.md
git diff --cached --stat
git diff --cached
git commit -m "feat(r01): harden CCGP public collection"
```

不要习惯性使用 `git add .`；它容易带入数据库、报告、凭据或队友文件。

## 7. 推送与远端验证

功能分支第一次推送并设置 upstream：

```powershell
git push -u origin feat/r01-ccgp-collector
```

以后在同一分支：

```powershell
git push
```

推送后必须验证：

```powershell
git status --short --branch
git branch -vv
$localSha = git rev-parse HEAD
$remoteLine = git ls-remote origin feat/r01-ccgp-collector
$localSha
$remoteLine
```

本地 SHA 与远端行首 SHA 完全相同，才算上传成功。配置了 `origin` 或只看到“push 命令无报错”都不够。

不直接 push `main`，因为它绕过审查并可能覆盖队友工作。永远不要使用 `--force` 或 `--force-with-lease`；若 push 被拒绝，先 fetch、查看分叉和 PR，而不是改写远端历史。

## 8. Pull Request

PR 中：

- **base** 是准备接收修改的团队可信主线。
- **head** 是你的功能分支。
- 首先创建 **Draft PR**，表示仍在等待测试或审查。
- 在 `Files changed` 逐文件检查是否越界、是否误带敏感文件。
- 使用仓库模板填写七项验收、能力编号、日志、base commit、迁移/依赖/凭据要求。
- 邀请另一名队员审查；测试未通过、证据不足或状态冲突时不合并。
- 能力负责人修正，审查者确认，团队约定的合并负责人最终点击合并；Codex 不自动合并。

当前恢复分支和远端 `main` 历史不相关，因此 C01 **不创建指向 `main` 的虚假 PR**。但是，从 `recovery/c01-local-project-20260715` 创建的后续功能分支与恢复分支同源，可以安全地把恢复分支作为 base 建 Draft PR；这样两名队员现在就能审查和合并功能分支。团队以后若建立新的共同主线，再更新 base 约定。

GitHub 网页创建 Draft PR 的实际步骤：

1. push 功能分支后打开 `https://github.com/lshhhhhhhhhh10/BidRadar-X/pulls`。
2. 点击 **New pull request**。
3. `base` 选择 `recovery/c01-local-project-20260715`，`compare` 选择刚推送的功能分支；例如 `feat/r01-ccgp-collector`。
4. 先检查 Commits 和 Files changed 只包含本能力内容。
5. 填完仓库七项模板后，使用 **Create draft pull request**，不要创建为可立即合并状态。
6. 邀请另一名队员审查；审查、测试和门禁通过后才由约定负责人合并到恢复分支。

合并后，其他电脑更新：

```powershell
git fetch origin --prune
git switch recovery/c01-local-project-20260715
git pull --ff-only
```

当前实际接手和 PR base 都是 `recovery/c01-local-project-20260715`。团队以后若建立共同主线，必须先更新本文的真实分支名；在解决无关历史前，不要把 `main` 猜成可信开发主线。

## 9. PR 七项验收怎么填

1. 用户可见结果：用户现在能做什么。
2. 修改文件：新增/更新/明确未改的范围。
3. 自动测试结果：命令、通过/失败数、警告。
4. 手工黑盒验证：从用户入口按步骤验证的真实结果。
5. 失败路径验证：网络、输入、认证、重复执行等失败如何表现。
6. 明确未完成项：不能把后续工作藏起来。
7. 下一能力入口或交接入口：只写 WORK_PLAN ID 和入口，不擅自扩展范围。

“是否允许合并”只有在测试、黑盒、日志、敏感扫描和审查全部满足时才能勾选。

## 10. 两人同时开发与 worktree

只有文件范围不重叠时才并行。Schema、API 公共契约、迁移、依赖文件属于高冲突区域，默认串行。不要让两个 Codex 窗口在同一个工作目录修改相同文件，也不要同时执行 commit、merge 或迁移修改。

推荐每个任务单独 worktree：

```powershell
git fetch origin --prune
git worktree add ..\BidRadar-X-r01 -b feat/r01-ccgp-collector recovery/c01-local-project-20260715
git worktree add ..\BidRadar-X-docs -b docs/c02-example recovery/c01-local-project-20260715
git worktree list
```

每个 Codex 窗口只打开自己的 worktree。文件边界重叠时，即使 worktree 不同也禁止并行，因为最终仍会冲突。

## 11. 冲突处理

1. 遇到冲突立即停止自动修改。
2. 不使用 `git reset --hard`，不使用 `git checkout --` 覆盖队友修改，不删除队友分支。
3. `git status` 找出冲突文件，分别阅读当前分支和对方分支的意图。
4. 由负责该模块的人确认取舍；公共 Schema/迁移必须双方共同确认。
5. 逐文件解决，重新运行本任务和全量测试。
6. 在工作日志和 PR 中记录冲突原因、解决选择、验证结果。

本地与远端无共同祖先时不是普通文本冲突。未经用户明确确认，不运行 `git merge --allow-unrelated-histories`；先保留两条分支并形成差异报告。

## 12. 敏感信息和大文件

不得提交：

- `.env`、Cookie、Token、API Key、密码、浏览器会话。
- `backend/.venv`、`node_modules`、缓存、`__pycache__`。
- 本地数据库、测试临时库、生成的报告和下载。
- 未授权的企业真实内部资料或飞书导出。

提交前至少执行：

```powershell
git status --short
git diff --cached --check
git diff --cached
```

敏感扫描只报告文件名和规则，不把实际凭据打印进日志或终端共享内容。Git remote URL 不得嵌入用户名、Token 或密码。

## 13. 每天交接

交接者：更新工作日志，跑测试和黑盒，检查 `git status`，commit、push、更新 Draft PR，并告诉另一人分支、commit SHA、测试结果、阻塞和未完成项。

接手者：fetch，阅读 PR 和日志，比对 SHA，复现基线，再继续。不要从聊天猜测状态，也不要在未拉取远端时继续旧工作副本。

## 14. GitHub 权限与协作者

C01 没有得到可靠的 collaborator 查询结果，也没有改变权限。若队友尚未受邀，仓库所有者在 GitHub 网页执行：

`Settings → Collaborators and teams → Add people → 输入队友准确用户名 → 邀请`

给予至少能够创建分支和 PR 的协作权限；不要共享账号、Token 或密码。分支保护、required review 和 GitHub Actions 尚未配置，需在共同主线确定后单独处理。

## 15. 断网备选

长期协作仍以 GitHub 为准。临时断网时可以用 `git bundle` 保存完整历史，例如：

```powershell
git bundle create BidRadar-X-backup.bundle --all
git bundle verify BidRadar-X-backup.bundle
```

不要压缩 `node_modules`、`.venv`、数据库、报告和缓存。ZIP 只能做一次性只读快照，不适合长期双向合并。
