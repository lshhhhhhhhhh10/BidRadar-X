# 公共契约冻结清单

公共契约先定义、后并行开发。任何字段变化必须由双方审核。

## JobSpec v1

| 字段 | 类型 | 默认 | 责任 |
|---|---|---|---|
| original_query | string | 无 | 保留原始输入 |
| keywords | string[] | 无 | 正向关键词 |
| exclude_keywords | string[] | [] | 排除词 |
| regions | string[] | ["全国"] | 地区范围 |
| notice_types | string[] | [] | 招标/更正/中标等 |
| source_ids | string[] | 所有启用公开源 | 来源 |
| date_range | object | 近7天 | 查询时间 |
| schedule.mode | immediate/cron | immediate | 执行方式 |
| schedule.cron | string/null | null | 标准 cron |
| schedule.timezone | string | Asia/Shanghai | 时区 |
| output.max_items | integer | 50 | 最大条数 |
| output.format | docx | docx | 输出格式 |
| parse_confidence | number | 0..1 | 解析置信度 |

置信度低于 0.8 或时间条件冲突时只返回预览，不创建任务。

## TenderRecord v1

来源标识、公告ID、URL、标题、项目名称、采购人、地区、公告类型、发布时间、截止时间、金额/币种、附件、抓取时间、内容哈希、相关性分数、项目实体ID、版本号、Evidence[]、缺失/冲突/解析错误标记。

关键字段缺失时使用 `null`，展示层统一显示“未知”；禁止生成推断值。

## SourceAdapter v1

```text
source_id: str
display_name: str
compliance_status: fixture | pending | approved | disabled
async search(job_spec) -> list[RawNotice]
async fetch(raw_notice) -> RawDocument
normalize(raw_document) -> TenderRecord
healthcheck() -> SourceHealth
```

适配器必须自行处理限速、超时和最多两次指数退避；不得让大模型决定网络请求。

## API v1

- `POST /api/jobs/parse`
- `POST /api/jobs`
- `GET /api/jobs/{job_id}`
- `POST /api/jobs/{job_id}/cancel`
- `GET /api/jobs/{job_id}/results`
- `GET /api/reports/{report_id}/download`
- `GET /api/sources`
- `POST /api/results/{record_id}/feedback`

错误统一返回 `{code, message, details, request_id}`。任务状态只允许按状态机规定迁移。

