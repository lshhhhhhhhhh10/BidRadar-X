# TASK-04 登录型招标来源实验

- 更新时间：2026-07-14 12:22（Asia/Shanghai）
- 状态：已完成（实验结论：不接入剑鱼普通会员网页）
- 负责人/窗口：TASK-04 登录来源窗口
- 依赖任务：TASK-01 数据契约
- 声明文件范围：
  - `backend/app/sources/jianyu.py`
  - `backend/tests/fixtures/jianyu/`
  - `backend/tests/test_jianyu_source.py`
  - `docs/LOGIN_SOURCE_SETUP.md`
  - `docs/worklogs/TASK-04-login-source.md`
- 明确不修改：
  - 现有工作流、`requirements.txt`、前端、其他数据源及上述范围外的全部文件

## 阶段记录

### 2026-07-14 12:12 — 启动与边界确认

#### 已完成

- 阅读项目上下文、统一数据契约、现有登录型模拟来源和 `.gitignore`。
- 读取 `playwright-interactive` 与 `security-best-practices` 技能说明；确认使用持久 Node REPL 做浏览器调查，并按 Python/FastAPI 安全基线实现。
- 确认仓库禁止提交 `.env*`，任务不会保存账号、密码、Cookie、Token 或真实 storage state。

#### 改动文件

- `docs/worklogs/TASK-04-login-source.md`：创建独立任务日志并声明修改边界。

#### 验证结果

- 命令/检查：只读检查指定文件、测试布局和技能运行时。
- 结果：通过
- 证据：持久 Node REPL 可用；现有来源仍是 `example.local` 模拟实现；本任务尚未接入总工作流。

#### 阻塞

- `agent-reach` 命令行入口不在当前 PowerShell PATH；改用其文档规定的网页读取路线，并结合官方页面与 Playwright 实测留证。

#### 下一步

- 调查剑鱼标讯的公开使用条款、未登录/登录边界和列表/详情页面结构。

### 2026-07-14 12:16 — 合规与技术调查

#### 已完成

- 官网帮助中心确认免费会员能力与登录方式；公开详情明确显示“登录后即可免费查看完整信息”。
- 官网《用户使用许可协议》第 7 条禁止未授权第三方软件/系统登录或使用服务，并禁止复制终端内存数据及客户端与服务端交互数据；据此判定 Playwright 复用普通会员会话自动采集不合适。
- 官网开发者帮助页确认存在标准/定制 API，但需要 `appid`、`key` 和签名；没有证据证明它属于免费会员权益。
- 选择 StoneDT 公开的“全国招投标数据免费接口”作为后续候选：文档明确允许程序化列表/详情调用，并给出免费账号配额。当前未取得账号，且公开文档示例为 HTTP，因此只登记候选，不标记为生产可用。
- 按 `playwright-interactive` 技能尝试持久 Node REPL；加载 Playwright 时因 Codex 安装目录 `lstat` 权限错误失败，随后清理 REPL。未尝试绕过沙箱或安全机制。

#### 改动文件

- `docs/LOGIN_SOURCE_SETUP.md`：记录剑鱼许可证据、拒绝在线采集的决策、官方 API 路径和替代候选。
- `docs/worklogs/TASK-04-login-source.md`：持续记录调查结论与限制。

#### 验证结果

- 命令/检查：官方页面搜索/读取；持久 Node REPL Playwright 启动检查。
- 结果：通过（合规结论）；浏览器实测受本机会话权限限制
- 证据：许可协议禁止条款、帮助中心免费登录说明、开发者 API 文档均已在安全配置文档中保留 URL。

#### 阻塞

- 无剑鱼书面自动化授权，因此在线 `collect()` 必须保持禁用。
- StoneDT 候选尚需真实账号、HTTPS、当前条款和数据质量验证，不能在本任务中宣称已生产验证。

#### 下一步

- 实现仓库外会话引用、登录墙识别和脱敏离线解析器；无授权时默认拒绝。

### 2026-07-14 12:22 — 实现与验收

#### 已完成

- 实现 `JianyuLoginSession.from_environment()`：只接受仓库外绝对路径，校验大小、JSON 结构、域名和登录材料，不把状态内容保存在返回对象中。
- 实现列表与详情 HTML 解析器：提取标题、URL、发布时间、地区、项目编号、采购人、预算、截止时间、正文和附件。
- 实现登录墙、非剑鱼 URL、无会话和未授权在线采集的明确失败路径；`collect()` 不返回模拟成功。
- 增加 3 份人工重建的脱敏 HTML fixture；未保存真实页面快照、账号、联系人、Cookie、Token 或 storage state。
- 安全加固包括 HTTPS/域名/端口限制、禁止 URL 内凭据、5 MiB HTML 上限和仓库内状态文件拒绝。
- 未导入或修改来源注册、工作流、前端、`requirements.txt` 或其他数据源。

#### 改动文件

- `backend/app/sources/jianyu.py`：安全会话引用、离线解析器和默认拒绝的来源实验。
- `backend/tests/fixtures/jianyu/`：3 份脱敏 HTML fixture。
- `backend/tests/test_jianyu_source.py`：会话安全、解析器和失败路径测试。
- `docs/LOGIN_SOURCE_SETUP.md`：安全配置和合规决策。
- `docs/worklogs/TASK-04-login-source.md`：完成记录。

#### 验证结果

- 命令/检查：Bundled Python `-m py_compile app\sources\jianyu.py tests\test_jianyu_source.py`
- 结果：通过
- 证据：无语法错误。
- 命令/检查：Bundled Python `-m unittest tests.test_jianyu_source -v`
- 结果：通过
- 证据：9 项测试全部通过。
- 命令/检查：Bundled Python `-m unittest discover -s tests -v`
- 结果：部分环境阻塞
- 证据：25 项中 23 项运行并通过；`test_api` 与 `test_workflow` 因有效 Python 环境缺少 `fastapi`/`langgraph` 无法导入。项目 `.venv` 启动器指向不存在的其他用户目录，未修改依赖或环境。
- 命令/检查：高信号凭据模式扫描与 fixture 字段检查。
- 结果：通过
- 证据：未发现凭据值；fixture 只在说明注释中出现“Cookie/Token”字样。

#### 阻塞

- 无实现阻塞。剑鱼在线自动化保持合规禁用，解除条件是平台书面授权或官方 API 合同。

#### 下一步

- 由协调窗口决定是否单独立项验证 StoneDT 免费 API 或直接推进官方公共数据接口；本任务不接入总工作流。

## 安全检查

- [x] 未将账号写入仓库或日志。
- [x] 未将 Cookie 写入仓库或日志。
- [x] 未将 Token 写入仓库或日志。
- [x] 未将 API Key 写入仓库或日志。
- [x] 仅记录了无敏感值的环境变量名或配置状态。

## 完成验收

- [x] TASK-04 的实验验收条件全部满足；在线来源结论为安全拒绝。
- [x] 所有改动都在声明文件范围内。
- [x] 改动文件和验证结果已记录。
- [x] 已完成安全检查。
- [ ] 已通知协调窗口更新总计划状态。
