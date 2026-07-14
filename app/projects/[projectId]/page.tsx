"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { getProject, getRunIdFromLocation, type ProjectProfile } from "@/lib/tender-api";


export default function ProjectOverviewPage() {
  const [runId, setRunId] = useState("");
  const [projectId, setProjectId] = useState("");
  const [project, setProject] = useState<ProjectProfile | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const activeRun = getRunIdFromLocation();
    const segments = window.location.pathname.split("/").filter(Boolean);
    const activeProject = decodeURIComponent(segments[segments.length - 1] ?? "");
    setRunId(activeRun);
    setProjectId(activeProject);
    if (!activeRun || !activeProject) {
      setError("项目地址不完整，请返回项目列表重新选择。");
      return;
    }
    getProject(activeRun, activeProject)
      .then(setProject)
      .catch((reason: Error) => setError(reason.message));
  }, []);

  return (
    <div className="requirements-page">
      <header className="requirements-header">
        <Link className="outline-action" href={`/projects?run=${encodeURIComponent(runId)}`}>返回项目列表</Link>
        <div>
          <p className="section-kicker">PURCHASER REQUIREMENTS</p>
          <h1>{project?.title ?? "招标要求总览"}</h1>
          {project && <p>{project.project_code} · {project.purchaser} · {project.source_name}</p>}
        </div>
      </header>

      <main className="requirements-main">
        {error && <div className="status-panel error-panel">{error}</div>}
        {!project && !error && <div className="status-panel">正在读取八类客观要求…</div>}
        {project && (
          <>
            <section className="project-objective-summary">
              <span>项目摘要</span>
              <p>{project.summary}</p>
              <dl>
                <div><dt>发布时间</dt><dd>{project.published_at.slice(0, 10)}</dd></div>
                <div><dt>投标截止</dt><dd>{project.deadline?.replace("T", " ").slice(0, 16)}</dd></div>
                <div><dt>证据数量</dt><dd>{project.evidence_count} 条</dd></div>
              </dl>
            </section>
            <section className="module-grid" aria-label="八类招标要求">
              {project.modules.map((module, index) => (
                <Link
                  className="module-card"
                  href={`/projects/${projectId}/${module.id}?run=${encodeURIComponent(runId)}`}
                  key={module.id}
                >
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <h2>{module.title}</h2>
                  <p>{module.summary}</p>
                  <strong>查看原文事实 →</strong>
                </Link>
              ))}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
