"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { getProject, getRunForTask, type ProjectProfile } from "@/lib/tender-api";


export default function ProjectOverviewPage() {
  const params = useParams<{ projectId: string }>();
  const searchParams = useSearchParams();
  const projectId = params.projectId ?? "";
  const runId = searchParams.get("run") ?? "";
  const taskId = searchParams.get("task") ?? "";
  const [project, setProject] = useState<ProjectProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      await Promise.resolve();
      if (!cancelled) {
        setLoading(true);
        setError("");
        setProject(null);
      }
      if (!runId || !taskId || !projectId) {
        if (!cancelled) {
          setError("项目地址缺少 run_id、task_id 或 project_id，请返回列表重新选择。");
          setLoading(false);
        }
        return;
      }
      try {
        const [, result] = await Promise.all([
          getRunForTask(runId, taskId),
          getProject(runId, projectId),
        ]);
        if (!cancelled) setProject(result);
      } catch (reason) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "读取项目失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [projectId, runId, taskId]);

  return (
    <div className="requirements-page">
      <header className="requirements-header">
        <Link className="outline-action" href={`/projects?run=${encodeURIComponent(runId)}&task=${encodeURIComponent(taskId)}`}>返回项目列表</Link>
        <div>
          <p className="section-kicker">PURCHASER REQUIREMENTS</p>
          <h1>{project?.title ?? "项目详情"}</h1>
          {project && <p>{project.project_code || "项目编号未披露"} · {project.purchaser} · {project.source_name}</p>}
        </div>
      </header>

      <main className="requirements-main">
        {loading && <div className="status-panel" role="status">正在读取该 run 保存的真实项目详情…</div>}
        {error && <div className="status-panel error-panel" role="alert">{error}</div>}
        {project && (
          <>
            <section className="project-objective-summary">
              <span>项目摘要</span>
              <p>{project.summary}</p>
              <dl>
                <div><dt>发布时间</dt><dd>{project.published_at.slice(0, 10) || "未披露"}</dd></div>
                <div><dt>投标截止</dt><dd>{project.deadline?.replace("T", " ").slice(0, 16) || "未披露"}</dd></div>
                <div><dt>证据数量</dt><dd>{project.evidence_count} 条</dd></div>
              </dl>
            </section>
            {project.modules.length === 0 ? (
              <div className="status-panel empty-panel">来源尚未提供可展示的字段级要求章节，系统没有使用固定模板补造内容。</div>
            ) : (
              <section className="module-grid" aria-label="来源支持的招标要求">
                {project.modules.map((module, index) => (
                  <Link
                    className="module-card"
                    href={`/projects/${encodeURIComponent(projectId)}/${encodeURIComponent(module.id)}?run=${encodeURIComponent(runId)}&task=${encodeURIComponent(taskId)}`}
                    key={module.id}
                  >
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <h2>{module.title}</h2>
                    <p>{module.summary}</p>
                    <strong>查看原文事实 →</strong>
                  </Link>
                ))}
              </section>
            )}
          </>
        )}
      </main>
    </div>
  );
}
