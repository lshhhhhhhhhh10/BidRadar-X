"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AppShell } from "@/app/components/AppShell";
import {
  deleteSubscription,
  getSubscriptionDetail,
  pauseSubscription,
  resumeSubscription,
  type SubscriptionDetail,
  type SubscriptionRunSummary,
} from "@/lib/tender-api";
import {
  readStarredSubscriptionIds,
  removeStarredSubscription,
  STARRED_SUBSCRIPTIONS_CHANGED_EVENT,
  toggleStarredSubscription,
} from "@/lib/starred-subscriptions";


export default function SubscriptionDetailPage() {
  const params = useParams<{ taskId: string }>();
  const router = useRouter();
  const taskId = params.taskId;
  const [detail, setDetail] = useState<SubscriptionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [starred, setStarred] = useState(false);

  useEffect(() => {
    const refresh = () => setStarred(readStarredSubscriptionIds().includes(taskId));
    refresh();
    window.addEventListener(STARRED_SUBSCRIPTIONS_CHANGED_EVENT, refresh);
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener(STARRED_SUBSCRIPTIONS_CHANGED_EVENT, refresh);
      window.removeEventListener("storage", refresh);
    };
  }, [taskId]);

  useEffect(() => {
    let active = true;
    async function refresh() {
      try {
        const result = await getSubscriptionDetail(taskId);
        if (!active) return;
        setDetail(result);
        setError("");
      } catch (reason) {
        if (active) setError(reason instanceof Error ? reason.message : "读取定时任务失败");
      } finally {
        if (active) setLoading(false);
      }
    }
    void refresh();
    const timer = window.setInterval(refresh, 10_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [taskId]);

  async function toggleStatus() {
    if (!detail) return;
    setBusy(true);
    setError("");
    try {
      const subscription = detail.subscription.status === "active"
        ? await pauseSubscription(taskId)
        : await resumeSubscription(taskId);
      setDetail((current) => current ? { ...current, subscription } : current);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "修改任务状态失败");
    } finally {
      setBusy(false);
    }
  }

  async function removeTask() {
    setBusy(true);
    setError("");
    try {
      await deleteSubscription(taskId);
      removeStarredSubscription(taskId);
      router.push("/");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "删除定时任务失败");
      setBusy(false);
    }
  }

  if (loading) {
    return <AppShell active="workbench"><section className="subscription-detail-state">正在读取定时任务…</section></AppShell>;
  }

  if (!detail) {
    return (
      <AppShell active="workbench">
        <section className="subscription-detail-state">
          <h1>没有找到该定时任务</h1>
          <p>{error || "它可能已被删除。"}</p>
          <Link className="solid-action" href="/">返回检索页</Link>
        </section>
      </AppShell>
    );
  }

  const { subscription, runs } = detail;
  return (
    <AppShell active="workbench">
      <div className="subscription-detail-page">
        <header className="subscription-detail-header">
          <div>
            <Link className="subscription-back-link" href="/">← 返回检索页</Link>
            <h1>定时推送详情</h1>
            <p>{subscription.query}</p>
          </div>
          <div className="subscription-detail-actions">
            <button
              className={`subscription-star-button ${starred ? "is-starred" : ""}`}
              type="button"
              aria-label={starred ? "取消星标定时任务" : "星标定时任务"}
              aria-pressed={starred}
              onClick={() => setStarred(toggleStarredSubscription(taskId).includes(taskId))}
            >
              {starred ? "★ 已星标" : "☆ 星标"}
            </button>
            <span className={`subscription-status is-${subscription.status}`}>
              {subscriptionStatus(subscription.status)}
            </span>
            {subscription.status !== "completed" && (
              <button type="button" disabled={busy} onClick={toggleStatus}>
                {subscription.status === "active" ? "暂停任务" : "恢复任务"}
              </button>
            )}
            <button className="is-danger" type="button" disabled={busy} onClick={removeTask}>删除任务</button>
          </div>
        </header>

        {error && <p className="subscription-detail-error" role="alert">{error}</p>}

        <section className="subscription-schedule-card">
          <div><span>执行频率</span><strong>{frequencyLabel(subscription.frequency, subscription.interval_minutes)}</strong></div>
          <div><span>下次触发</span><strong>{subscription.status === "active" ? formatDateTime(subscription.next_run_at) : "当前不执行"}</strong></div>
          <div><span>上次触发</span><strong>{formatDateTime(subscription.last_run_at)}</strong></div>
          <div><span>累计触发</span><strong>{runs.length} 次</strong></div>
        </section>

        <section className="subscription-run-section">
          <header>
            <div><h2>每次触发结果</h2><p>最新一次排在最上方；页面每 10 秒自动刷新。</p></div>
            <span>{runs.length}</span>
          </header>
          <div className="subscription-run-list">
            {runs.map((run) => <RunCard key={run.run_id} run={run} />)}
            {!runs.length && (
              <div className="subscription-empty-runs">
                <strong>尚未触发</strong>
                <p>到达下一次执行时间后，这里会显示新增项目或“本次无新增内容”。</p>
              </div>
            )}
          </div>
        </section>
      </div>
    </AppShell>
  );
}


function RunCard({ run }: { run: SubscriptionRunSummary }) {
  const isNew = run.outcome === "new_content";
  return (
    <article className={`subscription-run-card is-${run.outcome}`}>
      <div className="subscription-run-marker" aria-hidden="true" />
      <header>
        <div>
          <span>{formatDateTime(run.started_at)}</span>
          <h3>{runTitle(run)}</h3>
        </div>
        <span className={`subscription-run-badge is-${run.outcome}`}>{runBadge(run)}</span>
      </header>

      {isNew && (
        <div className="subscription-new-projects">
          {run.projects.map((project) => (
            <article key={project.project_id}>
              <div>
                <span>{project.source_name}{project.published_at ? ` · ${formatDate(project.published_at)}` : ""}</span>
                <strong>{project.title}</strong>
                {project.summary && <p>{project.summary}</p>}
              </div>
              {project.url && <a href={project.url} target="_blank" rel="noreferrer">打开来源 ↗</a>}
            </article>
          ))}
        </div>
      )}

      {run.outcome === "no_change" && <p className="subscription-run-note">已完成检索、清洗与历史去重，本次没有发现新增或实质变化的项目。</p>}
      {run.outcome === "running" && <p className="subscription-run-note">系统正在检索和核验，本次结果完成后会自动更新。</p>}
      {run.outcome === "failed" && <p className="subscription-run-note is-error">{run.error || "本次执行失败，系统会按重试策略再次运行。"}</p>}
      {isNew && run.report_available && <Link className="subscription-report-link" href={`/reports?run=${encodeURIComponent(run.run_id)}`}>查看本次项目报告</Link>}
    </article>
  );
}


function runTitle(run: SubscriptionRunSummary): string {
  if (run.outcome === "new_content") return `发现 ${run.project_count} 个新增项目`;
  if (run.outcome === "no_change") return "本次无新增内容";
  if (run.outcome === "running") return "正在执行本次检索";
  return "本次检索未完成";
}


function runBadge(run: SubscriptionRunSummary): string {
  if (run.outcome === "new_content") return `新增 ${run.project_count}`;
  if (run.outcome === "no_change") return "无新增";
  if (run.outcome === "running") return "执行中";
  return "失败";
}


function subscriptionStatus(status: string): string {
  return { active: "运行中", paused: "已暂停", completed: "已完成", failed: "等待恢复" }[status] ?? status;
}


function frequencyLabel(frequency: string, intervalMinutes?: number | null): string {
  if (frequency === "interval") return `每 ${intervalMinutes || 3} 分钟`;
  return { daily: "每日", weekly: "每周", once: "单次" }[frequency] ?? frequency;
}


function formatDateTime(value?: string | null): string {
  if (!value) return "暂无";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).format(date).replaceAll("/", ".");
}


function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", month: "numeric", day: "numeric" }).format(date);
}
