"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import {
  getRunForTask,
  getRunReport,
  listProjects,
  resolveApiUrl,
  type ProjectSummary,
  type ReportView,
  type RunSummary,
} from "@/lib/tender-api";


export default function ProjectsPage() {
  const searchParams = useSearchParams();
  const runId = searchParams.get("run") ?? "";
  const taskId = searchParams.get("task") ?? "";
  const [run, setRun] = useState<RunSummary | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [report, setReport] = useState<ReportView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      await Promise.resolve();
      if (!cancelled) {
        setLoading(true);
        setError("");
        setRun(null);
        setProjects([]);
        setReport(null);
      }
      if (!runId || !taskId) {
        if (!cancelled) {
          setError("结果地址缺少 run_id 或 task_id，请从首页重新运行任务。");
          setLoading(false);
        }
        return;
      }
      try {
        const [runResult, projectResult, reportResult] = await Promise.all([
          getRunForTask(runId, taskId),
          listProjects(runId),
          getRunReport(runId),
        ]);
        if (!cancelled) {
          setRun(runResult);
          setProjects(projectResult.items);
          setReport(reportResult);
        }
      } catch (reason) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "读取运行结果失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [runId, taskId]);

  return (
    <div className="collection-page">
      <header className="collection-header">
        <Link className="outline-action" href="/">返回首页</Link>
        <div>
          <p className="section-kicker">COLLECTED PROJECTS</p>
          <h1>本次运行的项目</h1>
          {run && <p>{run.query} · run_id: {run.run_id}</p>}
        </div>
        <span className="storage-status">{run ? `task_id: ${run.task_id}` : "SQLite 持久化结果"}</span>
      </header>

      <main className="collection-main">
        {loading && <div className="status-panel" role="status">正在从本地后端读取本次运行…</div>}
        {error && <div className="status-panel error-panel" role="alert">{error}</div>}
        {!loading && !error && projects.length === 0 && (
          <div className="status-panel empty-panel" role="status">
            本次真实运行已完成，但没有发现符合条件的项目。系统没有生成替代项目。
          </div>
        )}
        {!loading && !error && projects.length > 0 && (
          <ol className="project-list">
            {projects.map((project, index) => (
              <li className="project-row" key={project.project_id}>
                <span className="project-index">{index + 1}</span>
                <dl className="project-row-data">
                  <div><dt>发布时间</dt><dd>{project.published_at.slice(0, 10)}</dd></div>
                  <div><dt>发布网址</dt><dd><a href={project.url} target="_blank" rel="noreferrer">{project.url}</a></dd></div>
                  <div><dt>项目</dt><dd>{project.title}</dd></div>
                </dl>
                <Link
                  className="solid-action row-action"
                  href={`/projects/${encodeURIComponent(project.project_id)}?run=${encodeURIComponent(runId)}&task=${encodeURIComponent(taskId)}`}
                >
                  具体信息
                </Link>
              </li>
            ))}
          </ol>
        )}
      </main>

      <footer className="collection-footer">
        {report?.status === "available" && report.download_url ? (
          <a className="outline-action" href={resolveApiUrl(report.download_url)}>下载本次 Word</a>
        ) : (
          <span className="outline-action report-unavailable" aria-disabled="true">Word 暂不可下载</span>
        )}
        <span>{reportStatusText(report)}</span>
        <Link className="outline-action" href="/reports">查看报告历史</Link>
      </footer>
    </div>
  );
}


function reportStatusText(report: ReportView | null): string {
  if (!report) return "正在读取报告状态。";
  if (report.status === "available") return `报告已生成：${report.filename}`;
  if (report.status === "not_generated") return "本次运行没有生成新报告。";
  if (report.status === "missing") return "报告记录存在，但文件已丢失。";
  return report.error ?? "报告生成失败。";
}
