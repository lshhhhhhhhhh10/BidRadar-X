# BidRadar-X

超聚变企业命题参赛项目：面向服务器、液冷、算力中心和企业 IT 解决方案团队的可信招投标机会雷达。

## 当前阶段

仓库目前处于“报名材料与协作基线”阶段，尚未实现可运行系统。当前已完成：

- 报名表 Part 1 与 Part 2 直接填写稿。
- 6 页开题补充材料初稿。
- `JobSpec`、`TenderRecord`、`SourceAdapter` 和 API v1 契约草案。
- 双人逐功能分工、Agent 交付规范、Issue/PR 模板和 CI 基线。
- 旧选题材料原始归档。

不得将计划指标、接口草案或架构图描述为已经实现的功能。系统实现必须通过对应 Issue、测试和验收后，才能更新本节。

## 报名材料

- [报名表直接填写稿](docs/application/SUBMISSION_COPY.md)
- [开题补充材料底稿](docs/application/SUPPLEMENT_OUTLINE.md)
- [报名前双人分工](docs/application/REGISTRATION_SPRINT.md)
- `docs/application/BidRadar-X_开题补充材料_初稿.docx`

## 协作入口

1. 先阅读 [AGENTS.md](AGENTS.md)。
2. 再阅读 [公共契约](docs/CONTRACTS.md) 与 [逐功能分工](docs/WORK_BREAKDOWN.md)。
3. 每次只领取一个 GitHub Issue，使用独立分支与 PR。
4. 公共契约变化必须由两人审核；测试和 CI 不访问真实网站。

## 方案主链

```text
自然语言需求
  → JobSpec
  → 立即或定时任务
  → 合规公开源 SourceAdapter
  → 网页/PDF解析与标准化
  → 相关性、项目归并和版本识别
  → 字段级证据验证
  → Word 报告与任务记录
```

## 合规边界

- 不绕过登录、验证码、风控、robots 或站点访问控制。
- 登录来源未经明确授权不进入 MVP。
- API Key、Cookie、个人信息、原始抓取页面和生成报告不进入 Git。
- 自动测试和 CI 只使用固定样例。

## 下一步

两名成员先确认 [报名前双人分工](docs/application/REGISTRATION_SPRINT.md)。确认后从 `R-01 公开事实包`、`R-02 竞品矩阵` 和 `R-04 方案契约` 创建首批 Issues；业务开发必须等报名材料的事实和范围冻结后再开始。

