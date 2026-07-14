"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { getProjectModule, getRunForTask, type RequirementModule } from "@/lib/tender-api";


type DetailState = {
  projectTitle: string;
  projectCode?: string;
  module: RequirementModule;
};

export default function RequirementDetailPage() {
  const params = useParams<{ projectId: string; moduleId: string }>();
  const searchParams = useSearchParams();
  const projectId = params.projectId ?? "";
  const moduleId = params.moduleId ?? "";
  const runId = searchParams.get("run") ?? "";
  const taskId = searchParams.get("task") ?? "";
  const [detail, setDetail] = useState<DetailState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      await Promise.resolve();
      if (!cancelled) {
        setLoading(true);
        setError("");
        setDetail(null);
      }
      if (!runId || !taskId || !projectId || !moduleId) {
        if (!cancelled) {
          setError("详情地址不完整，请返回项目总览重新选择。");
          setLoading(false);
        }
        return;
      }
      try {
        const [, result] = await Promise.all([
          getRunForTask(runId, taskId),
          getProjectModule(runId, projectId, moduleId),
        ]);
        if (!cancelled) {
          setDetail({
            projectTitle: result.project_title,
            projectCode: result.project_code,
            module: result.module,
          });
        }
      } catch (reason) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "读取要求详情失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [moduleId, projectId, runId, taskId]);

  return (
    <div className="detail-page">
      <header className="detail-header">
        <Link className="outline-action" href={`/projects/${encodeURIComponent(projectId)}?run=${encodeURIComponent(runId)}&task=${encodeURIComponent(taskId)}`}>返回项目详情</Link>
        <div>
          <p className="section-kicker">OBJECTIVE CLAUSES ONLY</p>
          <h1>{detail?.module.title ?? "招标要求详情"}</h1>
          {detail && <p>{detail.projectTitle} · {detail.projectCode || "项目编号未披露"}</p>}
        </div>
        <span className="objective-badge">仅陈列来源支持的客观要求</span>
      </header>

      <main className="detail-main">
        {loading && <div className="status-panel" role="status">正在读取该 run 保存的条款与参数…</div>}
        {error && <div className="status-panel error-panel" role="alert">{error}</div>}
        {detail && (
          <>
            <section className="detail-intro"><p>{detail.module.summary}</p></section>
            {detail.module.facts.length === 0 && detail.module.tables.length === 0 && (
              <div className="status-panel empty-panel">该章节没有可展示的来源事实。</div>
            )}
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
