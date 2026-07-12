# Agent 任务提示词模板

把下面内容连同 GitHub Issue 一起交给各自 Agent：

```text
你正在 BidRadar-X 仓库处理 Issue #<编号>：<标题>。

开工前完整阅读 AGENTS.md、docs/CONTRACTS.md、docs/WORK_BREAKDOWN.md 和本 Issue。
只实现本 Issue；不得顺手实现后续功能，不得修改未授权公共契约。

输入：<文件/接口/fixture>
输出：<文件/接口/行为>
验收：<可运行的测试与阈值>
禁止：真实网站进入CI、提交密钥/Cookie、绕过登录/验证码、用LLM替代确定性网络与核验逻辑。

完成后按 AGENTS.md 的五段格式报告，并给出实际测试命令和结果。
```

审查 Agent 使用：

```text
只审查 PR 是否满足关联 Issue、公共契约、测试和安全边界。按 P0/P1/P2 标出问题；不要直接扩展需求。若接口发生未声明变化，必须阻止合并。
```

