# BidRadar-X Agent 工作规范

本仓库由两名学生与各自的编码 Agent 协作。任何 Agent 开工前必须先读本文件、对应 Issue、`docs/CONTRACTS.md` 和 `docs/WORK_BREAKDOWN.md`。

## 作用域规则

- 一次只处理一个 Issue，不顺手实现后续功能。
- 不修改自己 Issue 之外的公共契约；确需修改时先提交 ADR/契约 PR，等待另一位成员确认。
- 保留用户已有改动，不格式化或重写无关文件。
- 禁止提交 `.env`、API Key、Cookie、账号、原始登录会话、个人信息、抓取原文和生成报告。
- 禁止绕过登录、验证码、风控、robots 或站点访问限制。
- 自动测试和 CI 只能使用 `tests/fixtures`，不得访问真实网站。

## 分支与提交

- 分支：`feat/issue-<id>-<slug>`、`fix/issue-<id>-<slug>`、`docs/issue-<id>-<slug>`。
- 一个分支只对应一个 Issue；提交信息使用 `type(scope): summary`。
- PR 应尽量小于 400 行有效改动；公共契约修改必须单独 PR。

## 完成前必须执行

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest
```

若环境尚未建立，明确写成阻塞，不得声称测试通过。

## Agent 最终交付格式

每次任务最终回复必须包含：

1. `完成内容`：只写实际完成的行为。
2. `改动文件`：列出文件和用途。
3. `验证`：列出运行的命令及结果；未运行必须说明原因。
4. `接口影响`：写“无”或列出具体字段/API变化。
5. `风险与后续`：只列真实未完成项，不把后续任务伪装成本次完成。

不得只回复“已完成”，不得把代码生成成功等同于功能验证通过。

