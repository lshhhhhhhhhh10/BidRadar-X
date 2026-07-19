# BidRadar-X 评委安装与验收指南

本指南用于在一台全新电脑上启动 BidRadar-X，并用最短路径验证赛题能力。全程不需要修改源代码。

## 1. 环境要求

| 组件 | 最低要求 | 检查命令 |
|---|---:|---|
| Git | 2.x | `git --version` |
| Node.js | 22.13.0 | `node --version` |
| npm | 随 Node 安装 | `npm --version` |
| Python | 3.11 | `python3 --version` 或 `python --version` |

首次安装依赖需要访问 npm 和 PyPI。运行时前端监听 `3000`，后端监听 `8000`。

## 2. 安装

### macOS / Linux

```bash
git clone https://github.com/lshhhhhhhhhh10/BidRadar-X.git
cd BidRadar-X
npm install
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip
backend/.venv/bin/python -m pip install -r backend/requirements.txt
cp .env.example backend/.env
```

### Windows PowerShell

```powershell
git clone https://github.com/lshhhhhhhhhh10/BidRadar-X.git
Set-Location BidRadar-X
npm.cmd install
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install --upgrade pip
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
Copy-Item .env.example backend/.env
```

## 3. 可选凭据

不填写任何凭据也能启动页面、使用公开来源和运行规则链。以下能力需要用户自己的合法凭据：

| 能力 | 环境变量 | 不配置时 |
|---|---|---|
| 智谱 AI | `BIDRADAR_AI_API_KEY` | 自动使用规则链，不伪装成 AI 结果 |
| AI 备用凭据 | `BIDRADAR_AI_SECONDARY_API_KEY` | 主凭据失败时没有第二凭据可切换 |
| 天眼查招投标 API | `BIDRADAR_TIANYANCHA_TOKEN` | 卡片显示需要 Token，不进入生产路由 |
| SAM.gov | `BIDRADAR_SAM_GOV_API_KEY` | 卡片显示等待 API Key，不进入生产路由 |
| 飞书多维表格 | `BIDRADAR_FEISHU_*` | 不向企业飞书交付；不影响核心检索和 Word |

所有值写入 `backend/.env`。仓库已忽略 `.env`，前端没有读取密钥的接口。

## 4. 启动

在仓库根目录运行：

```bash
npm run dev
```

Windows PowerShell 使用：

```powershell
npm.cmd run dev
```

看到以下两个地址后启动完成：

```text
http://localhost:3000
http://127.0.0.1:8000
```

如果端口已被占用，先关闭旧的 BidRadar-X 进程再重新启动，不要同时启动两份后端。

## 5. 五分钟页面验收

### A. 信息来源真实性

1. 打开 <http://localhost:3000>。
2. 点击页面顶部“信息来源”药丸。
3. 确认能看到五类来源。
4. 默认应看到三个生产可采集来源：
   - 中国政府采购网；
   - 全国公共资源交易平台；
   - 中国移动采购与招标网。
5. TED 和中国招标投标协会应显示“待接入生产适配器”，不能显示为已经采集。
6. 天眼查和 SAM.gov 在未配置凭据时应显示需要 Token/API Key。

### B. 自然语言与 AI 链路

输入：

```text
查找最近三个月全国范围内的服务器采购招标公告
```

观察五阶段卡片：

1. 需求理解展示主题、地区、时间和排除条件；
2. 扩词阶段逐个展示同义词与相关采购表达；
3. 来源阶段逐站展示成功、空结果或失败原因；
4. 清洗阶段展示候选、在招、相关和去重数量；
5. 有项目时生成独立 Word，无项目时直接终止且不写入报告历史。

模型限流或超时时，页面应显示真实原因；系统可以切换备用凭据或降级，但不得把规则结果标成 AI 成功。

### C. 项目报告

1. 打开“项目报告”。
2. 选择一次有结果的查询。
3. 确认每个项目有独立 Word 下载按钮、来源链接和附件状态。
4. 点击项目卡片，右侧应显示联系人、项目事实和有证据的投标指标。
5. 下载 Word，检查：标题、发布时间、来源、核心内容、附件、AI 辅助摘要和风险研判。

### D. 定时任务

输入：

```text
每 3 分钟查找一次全国范围内的人工智能采购信息
```

首次查询结束后，右侧“定时推送”会出现任务。点击进入详情页可暂停、恢复、删除和查看每次触发结果。关闭浏览器不会停止调度；停止后端或关机期间不能访问外网，恢复后会扫描到期任务。

### E. 预算保护

打开“接口”页面，设置每日预算。付费来源在调用前通过数据库事务检查预算；当下一次调用将超过上限时，请求会被拒绝，而不是调用后再提示超支。

## 6. API 快速检查

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/ai/status
curl http://127.0.0.1:8000/api/sources
curl http://127.0.0.1:8000/api/reports
curl http://127.0.0.1:8000/api/subscriptions
```

`/api/ai/status` 只能返回启用状态、模型和阶段，不能返回密钥。

## 7. 自动测试

### 后端

```bash
cd backend
.venv/bin/python -m unittest discover -s tests -q
```

Windows：

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

### 前端

```bash
npm test
```

`npm test` 会先执行生产构建，再运行渲染结构测试。

## 8. 常见问题

### 页面无法打开

确认运行 `npm run dev` 的终端仍然开启，并检查 3000、8000 端口。前端和后端都需要运行；定时任务只要求后端持续运行。

### AI 显示未成功

先访问 `/api/ai/status`。常见原因是没有配置 Key、额度/限流、网络超时或模型返回非法结构。系统会记录具体原因；不要把“免费额度”视为永久承诺，实际额度以智谱账户控制台为准。

### 某个网站没有结果

“没有相关公告”与“抓取失败”是两种状态。前者是合法业务结果；后者必须显示 HTTP、超时、解析或访问限制等归一化原因。第三方站点仍可能临时限流，仓库不能承诺外部系统永远在线。

### Word 里的蓝色换行箭头

这是 Word 开启了“显示格式标记”，不是文档内容。点击 Word 工具栏的 `¶` 即可隐藏。

## 9. 当前未完成或需外部条件的能力

- TED、中国招标投标协会尚未注册生产采集适配器。
- 天眼查、SAM.gov 真实采集依赖用户凭据和账户权限。
- 飞书多维表格可靠投递底座已有代码和测试，但企业知识库自动归档仍需真实租户凭据、表字段和知识库权限验收。
- AI 摘要和风险研判是辅助信息，不替代原始招标文件与人工审查。
