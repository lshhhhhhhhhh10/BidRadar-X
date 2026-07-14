# 登录型招标来源安全配置

更新时间：2026-07-14（Asia/Shanghai）

## 结论

TASK-04 不应把剑鱼标讯的普通会员网页接入自动采集。

剑鱼官网可以确认免费会员能力：帮助中心写明“全国招标信息免费看，不遮挡”，登录支持微信扫码、验证码或密码；公开详情页也提示“登录后即可免费查看完整信息”。但其《用户使用许可协议》第 7 条同时禁止通过未经北京剑鱼授权或认可的第三方软件、系统登录或使用服务，并禁止复制服务过程中进入终端内存的数据和客户端与服务器的交互数据。该约束覆盖用 Playwright 复用普通会员会话批量采集的核心行为。

因此本仓库只保留离线、可审计的实验接口：

- 从仓库外文件加载 Playwright storage state 的引用；
- 解析已获授权、人工脱敏保存的列表和详情 HTML；
- 识别登录墙或过期会话并明确失败；
- 在线 `collect()` 默认拒绝，不返回模拟公告，也不接入现有工作流。

如要继续使用剑鱼数据，应先取得北京剑鱼书面许可，或申请其官方开发者 API。官网开发者文档公开了标准/定制数据 API，但要求 `appid`、`key` 和签名；文档没有证明该 API 属于免费会员权益，不能将网页会员登录态替代 API 授权。

## 合法替代方向

本实验选择 StoneDT 发布的“全国招投标数据免费接口”作为后续登录型来源候选，而不是绕过剑鱼限制。其公开文档明确提供带 `Authorization` 的列表、详情 API，普通开发者免费账号每天最多 5000 条、单页最多 20 条，并列出可对接 CRM/BI 的程序化使用场景。这比模拟浏览器读取会员页面具有更清晰的自动化授权边界。

该候选没有在 TASK-04 中接入：当前允许的实现文件名和测试范围均限定为剑鱼实验，而且用户要求不要接入总工作流。后续应单独验证 StoneDT 当前注册可用性、HTTPS 接口、服务条款、数据溯源质量和真实账号配额；未完成这些验证前，不能把它标记为生产可用。

## storage state 配置

环境变量名：`BIDRADAR_JIANYU_STORAGE_STATE_FILE`

变量值必须是仓库外的绝对路径，不能是 JSON、Cookie 或 Token 本身。示例（路径仅作说明）：

```powershell
$env:BIDRADAR_JIANYU_STORAGE_STATE_FILE = 'C:\Users\<用户名>\.bidradar\jianyu-storage-state.json'
```

状态文件应由用户在获得平台书面许可后，使用本机 Playwright 正常打开登录页并人工完成登录，再保存到仓库外目录。不得自动填写账号密码，不得自动处理短信/图片/滑块验证码，也不得导出或复制用户现有浏览器配置。调用方可这样取得经过校验的文件引用：

```python
from app.sources.jianyu import JianyuLoginSession

session = JianyuLoginSession.from_environment()
# 仅在已获书面授权的独立采集任务中：
# context = await browser.new_context(storage_state=str(session.storage_state_path))
```

加载器会拒绝：缺少环境变量、内联 JSON、相对路径、仓库内文件、符号链接、超大文件、非 Playwright JSON、意外域名，以及不含任何登录材料的空状态。返回对象只保留文件路径，不把 Cookie/Token 写入日志或业务记录。

## 运行与失效处理

- 未配置凭证时，`JianyuSource.from_environment()` 和 `collect()` 明确抛出 `JianyuSessionError`。
- 页面仍出现“登录后即可免费查看完整信息”或“会话已失效”时，解析器抛出 `JianyuAuthenticationError`，不得返回部分正文或模拟成功。
- 即使存在 storage state，当前 `collect()` 仍抛出 `JianyuAutomationNotAuthorizedError`；只有取得书面许可并另行评审后才能新增联网实现。
- storage state 到期或账号退出后，应在仓库外删除并重新人工生成；不要提交、复制到 fixture、粘贴到工单或聊天中。

若未来获准联网，默认限制为单并发、两次请求至少间隔 2 秒；遇到 429/403、验证码或安全校验立即停止，遵循 `Retry-After`，不得更换 IP、伪造设备指纹或绕过限制。

## fixture 规则

`backend/tests/fixtures/jianyu/` 内只有人工重建的最小 HTML：单位、编号、金额、链接和附件均为测试值；不包含真实账号、个人联系人、手机号、Cookie、Token、storage state 或完整网页快照。测试只验证本地解析和失败路径，不访问外网。

## 调查证据

- 剑鱼标讯用户使用许可协议：<https://www.jianyu360.cn/front/staticPage/permission_rules.html>
- 剑鱼标讯帮助中心（免费查询、登录方式、开发者 API）：<https://www.jianyu360.cn/helpCenter/index>
- 剑鱼开发者 API 帮助页：<https://www.jianyu360.cn/helpCenter/detail/QltCXFFNUQhXBhVaFV9TRFYBAQYRCkMK.html>
- StoneDT 免费招投标接口说明：<https://gitee.com/completely-open-source/free-bidding-data-interface/blob/master/README.md>

