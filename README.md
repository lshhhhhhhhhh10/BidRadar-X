# 招投标情报工作台（本地原型）

一个仅在本地运行的招投标情报网站骨架。当前使用模拟数据跑通需求理解、来源选择、采集、文档解析、相关性判断、跨站去重、项目事件图谱、Evidence RAG、事实核验、增量检测与报告生成。

## 本地启动

需要 Node.js 22+ 与 Python 3.11+。

前端：

```powershell
& 'C:\Program Files\nodejs\npm.cmd' run dev
```

后端（另开一个终端）：

```powershell
Set-Location backend
python run.py
```

打开 `http://localhost:3000`，后端接口文档位于 `http://127.0.0.1:8000/docs`。

## 目录职责

- `app/`：三个本地网站页面及交互。
- `backend/app/workflow/`：LangGraph工作流节点和连线。
- `backend/app/intelligence/`：五个核心算法模块。
- `backend/app/sources/`：真实数据源的替换接口，目前返回模拟数据。
- `backend/app/storage/`：SQLite任务、运行记录和项目快照。
- `backend/data/`：本地数据库与生成结果。

## 当前边界

- 采集内容是模拟数据，不访问真实招投标网站。
- RAG使用本地轻量混合检索模拟，尚未连接真实LLM和Embedding模型。
- 报告当前输出结构化JSON，Word渲染接口已预留。
- 每日/每周频率当前只生成计划，常驻调度器将在后续阶段实现。
