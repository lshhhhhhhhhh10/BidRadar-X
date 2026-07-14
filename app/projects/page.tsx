"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { getRunIdFromLocation, listProjects, type ProjectSummary } from "@/lib/tender-api";


export default function ProjectsPage() {
  const [runId, setRunId] = useState("");
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const activeRun = getRunIdFromLocation();
    setRunId(activeRun);
    if (!activeRun) {
      setError("没有找到已运行的检索任务，请先从首页创建任务。");
      setLoading(false);
      return;
    }
    listProjects(activeRun)
      .then((result) => setProjects(result.items))
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="collection-page">
      <header className="collection-header">
        <Link className="outline-action" href="/?modal=1">返回</Link>
        <div>
          <p className="section-kicker">COLLECTED PROJECTS</p>
          <h1>收集到的项目：</h1>
        </div>
        <span className="storage-status">SQLite 已保存</span>
      </header>

      <main className="collection-main">
        {loading && <div className="status-panel">正在从本地后端读取项目…</div>}
        {error && <div className="status-panel error-panel">{error}</div>}
        {!loading && !error && (
          <ol className="project-list">
            {projects.map((project, index) => (
              <li className="project-row" key={project.project_id}>
                <span className="project-index">{index + 1}</span>
                <dl className="project-row-data">
                  <div><dt>发布时间</dt><dd>{project.published_at.slice(0, 10)}</dd></div>
                  <div><dt>发布网址</dt><dd><a href={project.url} target="_blank" rel="noreferrer">{project.url}</a></dd></div>
                  <div><dt>项目</dt><dd>{project.title}</dd></div>
                </dl>
                <Link className="solid-action row-action" href={`/projects/${project.project_id}?run=${encodeURIComponent(runId)}`}>
                  具体信息
                </Link>
              </li>
            ))}
          </ol>
        )}
      </main>

      <footer className="collection-footer">
        <button className="outline-action" type="button" disabled title="模拟阶段暂未接入 Word 生成">
          下载成 Word
        </button>
        <span>当前为模拟阶段，下载功能将在报告模块接入。</span>
      </footer>
    </div>
  );
}
