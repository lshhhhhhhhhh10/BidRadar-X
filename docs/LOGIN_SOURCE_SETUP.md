# 登录型招标来源配置

更新时间：2026-07-17（Asia/Shanghai）

## 国内来源：天眼查开放平台

BidRadar-X 使用天眼查开放平台的“招投标搜索”接口（接口 ID 1063），不复用
普通网页 Cookie，也不保存用户的天眼查账号或密码。

申请步骤：

1. 打开 <https://open.tianyancha.com/open/1063> 并登录开放平台；
2. 申请“招投标搜索”接口；
3. 在“数据中心 → 我的接口”复制 Token；
4. 通过后端环境变量 `BIDRADAR_TIANYANCHA_TOKEN` 配置 Token；
5. 重启后端。首页会从“登录申请 Token”切换为“Token 已配置 · 可采集”。

官方页面当前标示该接口按次计费，约 ¥0.2/次；实际价格、套餐和权限以用户账号
中的开放平台信息为准。接口采用 HTTPS，请求头使用 `Authorization: <token>`，支持
按关键词、标题、采购人、供应商、发布日期、省份及公告类型查询。

Token 只在服务端读取，不返回前端、不拼进 URL、不写入业务数据库或日志。没有
Token 时采集器不会进入生产来源路由；Token 失效、接口未申请或账号无权限时会明确
失败，不返回模拟数据。

## 海外来源：SAM.gov

SAM.gov Contract Opportunities API v2 使用注册用户在 Account Details 中生成的
个人 API Key。环境变量名：`BIDRADAR_SAM_GOV_API_KEY`。

配置后重启后端，首页会从“需登录获取 API Key”切换为“已授权 · 可采集”。密钥
只通过后端环境变量读取，不返回前端、不写入数据库或日志。

## 已放弃来源：剑鱼标讯

剑鱼标讯已从首页信息源和生产来源路由中移除。普通会员网页登录态不能由本站
安全复用，其公开使用协议也不支持未经授权的第三方网页自动化。本项目不再把剑鱼
作为待接入来源；历史工作日志只作为审计记录保留。

## 密钥安全要求

- 不要把 Token、API Key、Cookie 或密码提交到 Git；
- 不要把密钥粘贴到聊天、工单、测试 fixture 或截图中；
- 正式部署应使用平台 Secret Manager，并为不同环境配置不同密钥；
- 账号停用、Token 轮换或权限变更后，应立即替换服务端密钥并重启服务；
- 遇到无权限、余额不足、频率过快等错误时停止调用，不绕过平台限制。

## 官方依据

- 天眼查招投标搜索 API：<https://open.tianyancha.com/open/1063>
- SAM.gov Opportunities API：<https://open.gsa.gov/api/get-opportunities-public-api/>
