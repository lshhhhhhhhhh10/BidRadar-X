# 飞书多维表格增量交付

> 当前状态：可靠投递 Outbox、Bitable 客户端、CLI 和自动测试已经进入代码；真实企业租户的应用凭据、目标表字段和知识库权限尚未完成线上验收。比赛演示中应称为“待企业授权联调的下一阶段能力”，不能宣称企业知识库自动归档已经上线。

## 结论

飞书群自定义机器人 Webhook 只能发送消息，不能直接编辑多维表格。本系统使用企业自建应用的 `tenant_access_token` 调用 Bitable Records API 写表；Webhook 仅作为可选的成功通知通道。

只有定时任务发现新增项目或实质变化，且对应 Word 已成功生成时，才创建飞书交付事件。无新增内容不会写表。

## 飞书后台准备

1. 在飞书开放平台创建企业自建应用，可选开启“机器人”能力。
2. 为应用申请“查看、评论、编辑和管理多维表格”相关权限，并由企业管理员审核。
3. 把该应用加入目标多维表格的协作者，授予编辑权限。知识库开启高级权限时，还要给应用知识库节点的可管理或编辑权限。
4. 在企业知识库中新建或选择一份多维表格，并创建以下文本字段：

   - 项目标题
   - 来源网站
   - 发布时间
   - 原文链接
   - 核心摘要
   - Word下载地址
   - 检索任务
   - 定时任务ID
   - 运行ID
   - 抓取时间
   - 变更类型
   - 项目ID
   - 交付指纹

默认要求这些列为文本类型，避免不同飞书字段类型对 URL、日期值格式的额外约束。列名不同时可用 `BIDRADAR_FEISHU_FIELD_MAP_JSON` 覆盖映射。

## 获取标识

- 普通多维表格 URL 中可直接取得 `app_token` 与 `table_id`。
- 知识库 URL 以 `/wiki/` 开头时，需通过飞书“获取知识空间节点信息”接口取得节点的 `obj_token`；当 `obj_type=bitable` 时，`obj_token` 才是这里需要的 `app_token`。

## 后端环境变量

复制 `.env.example` 中的飞书部分并填写：

```dotenv
BIDRADAR_FEISHU_ENABLED=auto
BIDRADAR_FEISHU_APP_ID=cli_xxx
BIDRADAR_FEISHU_APP_SECRET=xxx
BIDRADAR_FEISHU_APP_TOKEN=app_xxx
BIDRADAR_FEISHU_TABLE_ID=tbl_xxx
BIDRADAR_PUBLIC_BASE_URL=https://bids.example.internal
```

`BIDRADAR_PUBLIC_BASE_URL` 必须是企业成员浏览器能访问到的后端地址，不能填写 `127.0.0.1`。它用于生成 Word 下载链接。

可选配置群机器人成功通知：

```dotenv
BIDRADAR_FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
BIDRADAR_FEISHU_WEBHOOK_SECRET=xxx
BIDRADAR_FEISHU_TABLE_URL=https://your-company.feishu.cn/base/xxx
```

## 本地 CLI

在 `backend` 目录运行：

```bash
python -m app.integrations.feishu_cli status
python -m app.integrations.feishu_cli check
python -m app.integrations.feishu_cli outbox
python -m app.integrations.feishu_cli flush
```

- `status`：只显示脱敏配置和缺少项，不请求飞书。
- `check`：获取租户令牌、读取字段并校验权限和列名，不写数据。
- `outbox`：查看持久化推送状态，不显示项目正文载荷。
- `flush`：立即串行发送所有到期的待推送事件。

## 可靠性链路

1. 定时抓取、清洗、查重与 Word 生成完成。
2. 系统根据 `changes` 只选择新增或实质变化项目。
3. 在“定时运行成功”同一 SQLite 事务中写入 Outbox，避免成功运行与待推送事件出现断点。
4. 以 `delivery_fingerprint + project_id` 生成幂等键，重复运行不会重复入队。
5. 单写通道按最多 20 行一批写入飞书，避免同一多维表格并发写冲突。
6. 批量失败时逐行隔离错误数据；网络或限流失败进入指数退避，最多重试 10 次。
7. 飞书失败不会把已经成功的抓取、事实核验和 Word 生成改成失败。

后端进程必须持续运行，才能按时触发定时任务并重试 Outbox；前端页面可以关闭。

## 官方依据

- [飞书多维表格接入指南](https://open.feishu.cn/document/server-docs/docs/bitable-v1/notification)
- [飞书多维表格列出记录接口](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/list)
- [飞书机器人概述](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/bot-v3/bot-overview)
