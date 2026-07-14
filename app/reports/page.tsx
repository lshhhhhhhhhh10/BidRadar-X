"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { listReports, resolveApiUrl, type ReportHistoryItem, type ReportView } from "@/lib/tender-api";
import { AppShell } from "../components/AppShell";


export default function ReportsPage() {
  const [items, setItems] = useState<ReportHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const result = await listReports();
        if (!cancelled) setItems(result.items);
      } catch (reason) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "读取报告历史失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, []);

  return (
    <AppShell active="reports">
      <section className="report-history-page">
        <p className="eyebrow">DELIVERY MEMORY</p>
        <h1>真实运行与报告历史</h1>
        <p className="report-history-intro">以下记录来自本地 SQLite。刷新页面后会重新读取后端，不依赖浏览器会话状态。</p>
        {loading && <div className="status-panel" role="status">正在读取运行、报告与 delivery 记录…</div>}
        {error && <div className="status-panel error-panel" role="alert">{error}</div>}
        {!loading && !error && items.length === 0 && (
          <div className="status-panel empty-panel">数据库中还没有运行或报告记录。</div>
        )}
        {!loading && !error && items.length > 0 && (
          <ol className="report-history-list">
            {items.map((item) => (
              <li className="report-history-item" key={item.run_id}>
                <div className="report-history-heading">
                  <div>
                    <span>{new Date(item.created_at).toLocaleString("zh-CN", { hour12: false })}</span>
                    <h2>{item.query || "未命名任务"}</h2>
                  </div>
                  <strong className={`report-status report-status-${item.report.status}`}>{reportStatus(item.report)}</strong>
                </div>
                <dl>
                  <div><dt>run_id</dt><dd>{item.run_id}</dd></div>
                  <div><dt>task_id</dt><dd>{item.task_id}</dd></div>
                  <div><dt>运行状态</dt><dd>{item.run_status}</dd></div>
                  <div><dt>项目数量</dt><dd>{item.project_count}</dd></div>
                </dl>
                <div className="report-history-actions">
                  <Link href={`/projects?run=${encodeURIComponent(item.run_id)}&task=${encodeURIComponent(item.task_id)}`}>查看本次项目</Link>
                  {item.report.status === "available" && item.report.download_url && (
                    <a href={resolveApiUrl(item.report.download_url)}>再次下载 Word</a>
                  )}
                </div>
                {item.report.status === "failed" && <p className="report-failure">{item.report.error}</p>}
                {item.report.status === "missing" && <p className="report-failure">报告记录存在，但 DOCX 文件已丢失。</p>}
                {item.report.status === "not_generated" && <p className="report-note">本次运行未生成新的报告文件。</p>}
              </li>
            ))}
          </ol>
        )}
      </section>
    </AppShell>
  );
}


function reportStatus(report: ReportView): string {
  if (report.status === "available") return "可下载";
  if (report.status === "not_generated") return "未生成";
  if (report.status === "missing") return "文件丢失";
  return "生成失败";
}
