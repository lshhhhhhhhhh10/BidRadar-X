"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { getProjectModule, getRunIdFromLocation, type RequirementModule } from "@/lib/tender-api";


type DetailState = {
  projectTitle: string;
  projectCode?: string;
  module: RequirementModule;
};

export default function RequirementDetailPage() {
  const [runId, setRunId] = useState("");
  const [projectId, setProjectId] = useState("");
  const [detail, setDetail] = useState<DetailState | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const activeRun = getRunIdFromLocation();
    const segments = window.location.pathname.split("/").filter(Boolean).map(decodeURIComponent);
    const activeProject = segments[1] ?? "";
    const activeModule = segments[2] ?? "";
    setRunId(activeRun);
    setProjectId(activeProject);
    if (!activeRun || !activeProject || !activeModule) {
      setError("详情地址不完整，请返回总览页重新选择。");
      return;
    }
    getProjectModule(activeRun, activeProject, activeModule)
      .then((result) => setDetail({ projectTitle: result.project_title, projectCode: result.project_code, module: result.module }))
      .catch((reason: Error) => setError(reason.message));
  }, []);

  return (
    <div className="detail-page">
      <header className="detail-header">
        <Link className="outline-action" href={`/projects/${projectId}?run=${encodeURIComponent(runId)}`}>返回要求总览</Link>
        <div>
          <p className="section-kicker">OBJECTIVE CLAUSES ONLY</p>
          <h1>{detail?.module.title ?? "招标要求详情"}</h1>
          {detail && <p>{detail.projectTitle} · {detail.projectCode}</p>}
        </div>
        <span className="objective-badge">仅陈列甲方客观要求</span>
      </header>

      <main className="detail-main">
        {error && <div className="status-panel error-panel">{error}</div>}
        {!detail && !error && <div className="status-panel">正在读取后端保存的条款与参数…</div>}
        {detail && (
          <>
            <section className="detail-intro"><p>{detail.module.summary}</p></section>
            {detail.module.facts.length > 0 && (
              <section className="fact-list">
                {detail.module.facts.map((fact, index) => (
                  <article className="fact-item" key={`${fact.label}-${index}`}>
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <div><h2>{fact.label}</h2><p>{fact.value}</p><small>原文位置：{fact.source}</small></div>
                  </article>
                ))}
              </section>
            )}
            {detail.module.tables.map((table) => (
              <section className="requirement-table-section" key={table.title}>
                <h2>{table.title}</h2>
                <div className="table-scroll">
                  <table>
                    <thead><tr>{table.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
                    <tbody>
                      {table.rows.map((row, rowIndex) => (
                        <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={`${rowIndex}-${cellIndex}`}>{cell}</td>)}</tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            ))}
          </>
        )}
      </main>
    </div>
  );
}
