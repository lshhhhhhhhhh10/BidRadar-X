"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import {
  listReports,
  revealLocalAttachment,
  resolveApiUrl,
  type ProjectSummary,
  type ReportDocumentView,
  type ReportHistoryItem,
  type ReportView,
} from "@/lib/tender-api";
import {
  FAVORITES_CHANGED_EVENT,
  readFavoriteProjects,
  toggleFavoriteProject,
  type FavoriteProject,
} from "@/lib/favorite-projects";
import { AppShell } from "../components/AppShell";
import { InfoTip } from "../components/InfoTip";


export default function ReportsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedRunId = searchParams.get("run") ?? "";
  const [items, setItems] = useState<ReportHistoryItem[]>([]);
  const [activeRunId, setActiveRunId] = useState(requestedRunId);
  const [activeProjectId, setActiveProjectId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [fileFeedback, setFileFeedback] = useState("");
  const [revealingAttachmentId, setRevealingAttachmentId] = useState("");
  const [selectedInsightKeys, setSelectedInsightKeys] = useState<string[]>([]);
  const [favoriteProjects, setFavoriteProjects] = useState<FavoriteProject[]>([]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const result = await listReports();
        if (cancelled) return;
        setItems(result.items);
        const requested = result.items.find((item) => item.run_id === requestedRunId);
        setActiveRunId(requested?.run_id ?? result.items[0]?.run_id ?? "");
      } catch (reason) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "读取项目报告失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [requestedRunId]);

  useEffect(() => {
    const refresh = () => setFavoriteProjects(readFavoriteProjects());
    refresh();
    window.addEventListener(FAVORITES_CHANGED_EVENT, refresh);
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener(FAVORITES_CHANGED_EVENT, refresh);
      window.removeEventListener("storage", refresh);
    };
  }, []);

  const activeReport = useMemo(
    () => items.find((item) => item.run_id === activeRunId) ?? items[0] ?? null,
    [activeRunId, items],
  );

  const activeProject = useMemo(
    () => activeReport?.projects.find((project) => project.project_id === activeProjectId)
      ?? activeReport?.projects[0]
      ?? null,
    [activeProjectId, activeReport],
  );

  const projectCount = useMemo(
    () => items.reduce((total, item) => total + item.projects.length, 0),
    [items],
  );
  const downloadableCount = useMemo(
    () => items.reduce(
      (total, item) => total + reportDocuments(item.report).filter((document) => document.status === "available").length,
      0,
    ),
    [items],
  );
  const latestDocumentRunId = useMemo(
    () => items.find((item) => reportDocuments(item.report).length > 0)?.run_id ?? "",
    [items],
  );
  const activeDocuments = useMemo(
    () => activeReport ? reportDocuments(activeReport.report) : [],
    [activeReport],
  );
  const activeInsights = useMemo(
    () => activeProject ? projectInsights(activeProject) : [],
    [activeProject],
  );
  const visibleInsights = useMemo(
    () => selectVisibleInsights(activeInsights, selectedInsightKeys),
    [activeInsights, selectedInsightKeys],
  );

  function chooseReport(runId: string) {
    setActiveRunId(runId);
    setActiveProjectId("");
    setSelectedInsightKeys([]);
    router.replace(`/reports?run=${encodeURIComponent(runId)}`, { scroll: false });
  }

  async function revealAttachment(attachment: ProjectSummary["attachments"][number]) {
    if (!attachment.reveal_url) return;
    setRevealingAttachmentId(attachment.attachment_id);
    setFileFeedback("");
    try {
      const result = await revealLocalAttachment(attachment.reveal_url);
      setFileFeedback(`已在文件管理器中定位：${result.filename}`);
    } catch (reason) {
      setFileFeedback(reason instanceof Error ? reason.message : "无法打开本地招标文件");
    } finally {
      setRevealingAttachmentId("");
    }
  }

  function toggleProjectFavorite(project: ProjectSummary) {
    if (!activeReport) return;
    const next = toggleFavoriteProject({
      id: project.project_id,
      runId: activeReport.run_id,
      title: project.title,
      region: reportRegion(activeReport),
      sourceName: project.source_name || "项目报告",
      addedAt: new Date().toISOString(),
    });
    setFavoriteProjects(next);
  }

  function projectIsFavorite(project: ProjectSummary): boolean {
    return favoriteProjects.some((item) => item.id === project.project_id && item.runId === activeReport?.run_id);
  }

  return (
    <AppShell active="reports">
      <section className="report-workspace">
        <header className="report-workspace-header">
          <div>
            <span className="title-with-info"><h1>项目报告</h1><InfoTip text="每个新增项目生成一份可追溯 Word；定时任务只推送新获取或发生实质变化的内容。" /></span>
          </div>
          <Link className="new-query-button" href="/">发起新查询</Link>
        </header>

        <div className="report-workspace-grid">
          <aside className="report-archive" aria-label="查询记录">
            <header>
              <div><h2>查询记录</h2></div>
              <span>{items.length}</span>
            </header>

            <div className="report-archive-stats" aria-label="项目报告概况">
              <article><strong>{projectCount}</strong><span>收录项目</span></article>
              <article><strong>{downloadableCount}</strong><span>Word 文档</span></article>
            </div>

            {loading && <div className="report-archive-loading">正在读取记录…</div>}
            {!loading && items.length === 0 && <div className="report-archive-loading">完成第一次查询后，报告会出现在这里。</div>}
            <ol className="report-archive-list">
              {items.map((item) => (
                <li key={item.run_id}>
                  <button
                    className={item.run_id === activeReport?.run_id ? "is-active" : ""}
                    type="button"
                    onClick={() => chooseReport(item.run_id)}
                  >
                    <span>{formatDateTime(item.created_at)}</span>
                    <strong>{item.display_title || "未命名查询"}</strong>
                    <small>{item.projects.length} 个项目 · {runStatusLabel(item.run_status)}</small>
                  </button>
                </li>
              ))}
            </ol>
          </aside>

          <main className="report-document-column">
            {error && <div className="status-panel error-panel" role="alert">{error}</div>}
            {loading && <div className="status-panel" role="status">正在读取查询结果与汇总文档…</div>}
            {!loading && !error && !activeReport && (
              <div className="report-document-empty">
                <h2>还没有可展示的项目文档</h2>
                <p>发起一次自然语言查询后，系统会自动完成检索、清洗查重，并为每个项目生成独立 Word。</p>
                <Link href="/">开始第一次查询</Link>
              </div>
            )}

            {activeReport && (
              <article className="report-document">
                <header className="report-document-titlebar">
                  <div>
                    <h2>{activeReport.display_title || "未命名查询"}</h2>
                    <p>{formatDateTime(activeReport.created_at)} · {frequencyLabel(activeReport.frequency)} · {activeReport.projects.length} 个项目</p>
                  </div>
                  <span className={`report-document-state ${activeDocuments.length > 0 ? "is-ready" : ""}`}>
                    {activeDocuments.length > 0 ? `${activeDocuments.length} 份 Word` : `Word ${reportStatus(activeReport.report)}`}
                  </span>
                </header>

                <section className="report-word-library" aria-labelledby="report-word-library-title">
                  <div className="report-word-library-heading">
                    <div className="title-with-info"><h3 id="report-word-library-title">项目 Word 文档</h3><InfoTip text="每个文件只包含一个项目，可分别下载；新获取的文档排在最前。" /></div>
                    <span>最新文档优先</span>
                  </div>
                  {fileFeedback && <p className="report-file-feedback" role="status">{fileFeedback}</p>}
                  {activeDocuments.length > 0 ? (
                    <ol className="report-word-list">
                      {activeDocuments.map((document) => {
                        const showNew = activeReport.run_id === latestDocumentRunId && document.is_new;
                        const project = activeReport.projects.find(
                          (item) => item.project_id === document.project_id,
                        );
                        const attachments = project?.attachments ?? [];
                        return (
                          <li key={document.document_id} className={showNew ? "is-new" : ""}>
                            <i className="report-new-dot" aria-label={showNew ? "本次新获取" : undefined} />
                            <button
                              type="button"
                              onClick={() => {
                                if (!document.project_id) return;
                                setActiveProjectId(document.project_id);
                                setSelectedInsightKeys([]);
                              }}
                            >
                              <small>{changeTypeLabel(document.change_type)} · {formatDateTime(document.generated_at || activeReport.created_at)}</small>
                              <strong>{document.project_title}</strong>
                              <span title={document.filename}>{document.filename}</span>
                            </button>
                            <div className="report-file-actions">
                              {document.status === "available" ? (
                                <a className="report-word-download" href={resolveApiUrl(document.download_url)}>下载 Word</a>
                              ) : (
                                <span className="report-word-missing">Word 待重新生成</span>
                              )}
                              {attachments.length > 0 ? attachments.map((attachment, index) => (
                                attachment.local_available && attachment.reveal_url ? (
                                <button
                                  className="report-tender-download"
                                  key={attachment.attachment_id}
                                  type="button"
                                  title={attachment.name}
                                  disabled={revealingAttachmentId === attachment.attachment_id}
                                  onClick={() => revealAttachment(attachment)}
                                >
                                  {revealingAttachmentId === attachment.attachment_id
                                    ? "正在打开…"
                                    : attachments.length > 1 ? `招标文件 ${index + 1}` : "招标文件"}
                                </button>
                                ) : (
                                  <span className="report-tender-missing" key={attachment.attachment_id}>
                                    {attachmentArchiveLabel(attachment)}
                                  </span>
                                )
                              )) : (
                                <span className="report-tender-missing">原网站未提供 PDF</span>
                              )}
                            </div>
                          </li>
                        );
                      })}
                    </ol>
                  ) : (
                    <div className="report-word-empty">本次运行没有新增项目，因此没有生成重复文档。</div>
                  )}
                </section>

                <section className="report-ai-overview" aria-label="AI 汇总">
                  <header><span className="title-with-info">AI 汇总<InfoTip text="汇总内容只能引用公告正文、结构化字段或已归档附件中的事实。" /></span></header>
                  <p>{executiveSummary(activeReport)}</p>
                  {activeReport.ai_report?.key_findings && activeReport.ai_report.key_findings.length > 0 && (
                    <ul>
                      {activeReport.ai_report.key_findings.slice(0, 4).map((finding, index) => (
                        <li key={`${index}-${finding.text}`}><span>{String(index + 1).padStart(2, "0")}</span>{finding.text}</li>
                      ))}
                    </ul>
                  )}
                  <footer>
                    {[
                      "语义理解",
                      "智能扩词",
                      "多源检索",
                      "清洗查重",
                      "事实核验",
                      "Word 汇总",
                    ].map((stage) => <span key={stage}><i />{stage}</span>)}
                  </footer>
                </section>

                <section className="report-source-outcomes" aria-labelledby="report-source-outcomes-title">
                  <div className="report-source-outcomes-heading">
                    <div className="title-with-info"><h3 id="report-source-outcomes-title">本次抓取网站</h3><InfoTip text="这里如实展示实际访问的信息源、成功或失败状态，以及原始记录数。" /></div>
                    <span>{activeReport.sources?.length ?? 0} 个来源</span>
                  </div>
                  {activeReport.sources?.length ? (
                    <ul>
                      {activeReport.sources.map((source) => (
                        <li key={source.source_id} className={`is-${source.status}`}>
                          <i aria-hidden="true" />
                          <div><strong>{source.name}</strong><small>{source.requires_login ? "授权来源" : "公开来源"}</small></div>
                          <span>{source.status === "failed" ? "抓取失败" : source.record_count > 0 ? `${source.record_count} 条原始记录` : "未抓取到内容"}</span>
                        </li>
                      ))}
                    </ul>
                  ) : <p className="report-source-empty">该历史记录未保存信息源运行数据。</p>}
                </section>

                {activeReport.projects.length === 0 ? (
                  <div className="query-report-empty">本次查询没有发现符合条件的项目，系统未生成替代内容。</div>
                ) : (
                  <section className="report-project-section" aria-labelledby="report-project-title">
                    <div className="report-project-section-heading">
                      <div className="title-with-info"><h3 id="report-project-title">项目列表</h3><InfoTip text="点击项目卡片，可在右侧查看联系人、项目事实、投标指标和公告重点。" /></div>
                    </div>
                    <ol className="report-project-cards">
                      {activeReport.projects.map((project, index) => {
                        const localAttachments = project.attachments.filter(
                          (attachment) => attachment.local_available && attachment.reveal_url,
                        );
                        return (
                        <li key={project.project_id} className={project.project_id === activeProject?.project_id ? "is-active" : ""}>
                          <button
                            className="report-project-select"
                            type="button"
                            onClick={() => {
                              setActiveProjectId(project.project_id);
                              setSelectedInsightKeys([]);
                            }}
                            aria-pressed={project.project_id === activeProject?.project_id}
                          >
                            <span className="report-project-number">{String(index + 1).padStart(2, "0")}</span>
                            <div className="report-project-card-copy">
                              <small>{project.source_name || "来源名称未披露"} · {formatDate(project.published_at)}</small>
                              <h4>{project.title}</h4>
                              <p>{cleanDisplayText(project.summary) || "原公告未提供可核验的核心内容。"}</p>
                              <dl>
                                <div><dt>采购人</dt><dd>{project.purchaser || "未披露"}</dd></div>
                                <div><dt>预算</dt><dd>{formatBudget(project.budget)}</dd></div>
                                <div><dt>截止时间</dt><dd>{formatDeadline(project.deadline)}</dd></div>
                              </dl>
                            </div>
                            <span className="report-project-open" aria-hidden="true">→</span>
                          </button>
                          <button
                            className={projectIsFavorite(project) ? "report-project-favorite is-favorite" : "report-project-favorite"}
                            type="button"
                            onClick={() => toggleProjectFavorite(project)}
                            aria-label={projectIsFavorite(project) ? `取消收藏${project.title}` : `收藏${project.title}`}
                            aria-pressed={projectIsFavorite(project)}
                          >{projectIsFavorite(project) ? "★" : "☆"}</button>
                          <div className="report-project-links" aria-label={`${project.title}文件与来源`}>
                            {project.url && (
                              <a href={project.url} target="_blank" rel="noreferrer">信息来源 ↗</a>
                            )}
                            {localAttachments.map((attachment, attachmentIndex) => (
                              <button
                                key={attachment.attachment_id}
                                type="button"
                                disabled={revealingAttachmentId === attachment.attachment_id}
                                onClick={() => revealAttachment(attachment)}
                                title={attachment.local_filename || attachment.name}
                              >
                                {revealingAttachmentId === attachment.attachment_id
                                  ? "正在定位…"
                                  : localAttachments.length > 1
                                    ? `本地招标文件 ${attachmentIndex + 1}`
                                    : "本地招标文件"}
                              </button>
                            ))}
                            {project.attachments.length > 0 && localAttachments.length === 0 && (
                              <span>招标文件正在归档或未能保存</span>
                            )}
                            {project.attachments.map((attachment, attachmentIndex) => (
                              <a
                                className="report-attachment-source"
                                href={attachment.url}
                                key={`source-${attachment.attachment_id}`}
                                target="_blank"
                                rel="noreferrer"
                                title={attachment.name}
                              >附件原地址{project.attachments.length > 1 ? ` ${attachmentIndex + 1}` : ""} ↗</a>
                            ))}
                          </div>
                        </li>
                      );
                      })}
                    </ol>
                  </section>
                )}
              </article>
            )}
          </main>

          <aside className="project-intelligence" aria-label="项目重点信息">
            {activeProject && activeReport ? (
              <>
                <header>
                  <span>项目重点</span>
                  <span className="project-evidence-state"><i />{activeProject.evidence_count} 条证据</span>
                </header>
                <h2 title={activeProject.title}>{activeProject.title}</h2>
                <p>{activeProject.source_name || "来源名称未披露"} · {formatDate(activeProject.published_at)}</p>

                <section className="intelligence-contacts">
                  <h3>项目联系人</h3>
                  {activeProject.contacts?.length ? (
                    <ul>
                      {activeProject.contacts.map((contact, index) => (
                        <li key={`${contact.role}-${contact.name}-${index}`}>
                          <div><span>{contact.role}</span><strong>{contact.name}</strong><small>{contact.source}</small></div>
                          {/\d/.test(contact.phone) ? (
                            <a href={`tel:${contact.phone.replace(/[^\d+]/g, "")}`}>{contact.phone}</a>
                          ) : <span>{contact.phone}</span>}
                        </li>
                      ))}
                    </ul>
                  ) : <p>公告正文及已下载 PDF 未披露可核验的联系人姓名或电话。</p>}
                </section>

                <section className="intelligence-facts">
                  <h3>项目事实</h3>
                  <dl>
                    <div><dt>采购人</dt><dd>{activeProject.purchaser || "未披露"}</dd></div>
                    <div><dt>投标截止</dt><dd>{formatDeadline(activeProject.deadline)}</dd></div>
                    <div><dt>本地 PDF</dt><dd>{activeProject.attachments.filter((item) => item.local_available).length} 个</dd></div>
                    <div><dt>结构化模块</dt><dd>{activeProject.module_count ?? 0} 个</dd></div>
                  </dl>
                </section>

                <section className="intelligence-indicators" aria-labelledby="indicator-title">
                  <div className="intelligence-indicator-heading">
                    <span className="title-with-info"><h3 id="indicator-title">投标指标</h3><InfoTip text="默认只展示招标公告或附件中确实披露的最多三项指标；可以多选查看更多。" /></span>
                    <details className="insight-multiselect">
                      <summary aria-label="选择要查看的投标指标">
                        {selectedInsightKeys.length ? `已选 ${selectedInsightKeys.length} 项` : "智能精选"}
                      </summary>
                      <div className="insight-multiselect-menu">
                        <button type="button" onClick={() => setSelectedInsightKeys([])}>智能精选（最多 3 项）</button>
                        <button type="button" onClick={() => setSelectedInsightKeys(activeInsights.map((item) => item.key))}>全部指标</button>
                        {activeInsights.map((insight) => (
                          <label key={insight.key}>
                            <input
                              type="checkbox"
                              checked={selectedInsightKeys.includes(insight.key)}
                              onChange={() => setSelectedInsightKeys((current) => current.includes(insight.key)
                                ? current.filter((key) => key !== insight.key)
                                : [...current, insight.key])}
                            />
                            <span>{insight.label}</span>
                          </label>
                        ))}
                      </div>
                    </details>
                  </div>
                  <dl className="intelligence-metrics">
                    {visibleInsights.map((insight) => (
                      <div key={insight.key}>
                        <dt>{insight.label}</dt>
                        <dd>{insight.value}</dd>
                        <small>{insight.source}</small>
                        <i className={insight.available ? "state-ready" : "state-neutral"} aria-hidden="true" />
                      </div>
                    ))}
                  </dl>
                  {visibleInsights.length === 0 && <div className="intelligence-metrics-empty">公告及已归档附件没有披露可核验的投标指标。</div>}
                </section>

                <section className="intelligence-summary">
                  <span className="title-with-info">公告重点<InfoTip text="已移除网页样式、脚本和重复导航，仅保留可读的公告正文摘要。" /></span>
                  <p>{cleanDisplayText(activeProject.summary) || "原公告未提供可核验的核心内容。"}</p>
                </section>

                <div className="intelligence-actions">
                  <Link href={`/projects/${encodeURIComponent(activeProject.project_id)}?run=${encodeURIComponent(activeReport.run_id)}&task=${encodeURIComponent(activeReport.task_id)}`}>查看结构化详情</Link>
                  {activeProject.url && <a href={activeProject.url} target="_blank" rel="noreferrer">打开原公告 ↗</a>}
                </div>
              </>
            ) : (
              <div className="project-intelligence-empty">
                <h2>选择项目查看重点</h2>
                <p>项目卡片将在检索完成后出现在项目列表中。</p>
              </div>
            )}
          </aside>
        </div>
      </section>
    </AppShell>
  );
}


function reportDocuments(report: ReportView): ReportDocumentView[] {
  if (report.documents?.length) return report.documents;
  if (report.status === "available" && report.download_url && report.filename) {
    return [{
      document_id: report.delivery_fingerprint?.slice(0, 16) || report.filename,
      project_id: "legacy",
      project_title: "历史项目报告",
      filename: report.filename,
      download_url: report.download_url,
      notice_count: report.notice_count ?? 0,
      change_type: "legacy",
      is_new: false,
      status: "available",
    }];
  }
  return [];
}


function attachmentArchiveLabel(attachment: ProjectSummary["attachments"][number]): string {
  if (attachment.archive_error === "source_has_no_pdf") return "原网站未提供 PDF";
  if (attachment.archive_status === "unsupported") return "源站仅提供非 PDF 文件";
  if (attachment.archive_error === "access_denied") return "PDF 下载被源站拒绝";
  if (attachment.archive_error === "network_error") return "PDF 网络下载失败";
  if (attachment.archive_error === "write_failed") return "PDF 本地保存失败";
  if (attachment.archive_error === "too_large") return "PDF 超过 50 MB 限制";
  return "PDF 下载失败";
}


function changeTypeLabel(value: string): string {
  if (value === "new_project") return "新获取";
  if (value === "material_change") return "有重要更新";
  return "历史文档";
}


function executiveSummary(item: ReportHistoryItem): string {
  const summary = item.ai_report?.executive_summary?.trim();
  if (summary) return summary;
  if (item.projects.length === 0) return "本次自动检索没有发现符合条件且可由来源证据支持的项目。";
  const sourceCount = new Set(item.projects.map((project) => project.source_name).filter(Boolean)).size;
  return `本次检索经自动清洗与查重后收录 ${item.projects.length} 个项目，覆盖 ${sourceCount} 个信息来源。下方卡片保留公告标题、发布时间、来源链接、核心内容与附件入口。`;
}


function projectInsights(project: ProjectSummary) {
  if (project.bidder_insights?.length) return project.bidder_insights;
  return [
    {
      key: "budget",
      label: "采购预算 / 最高限价",
      value: formatBudget(project.budget),
      source: project.budget ? "公告结构化字段" : "未找到可核验原文",
      available: Boolean(project.budget),
    },
    {
      key: "deadline",
      label: "投标 / 响应截止",
      value: formatDeadline(project.deadline),
      source: project.deadline ? "公告结构化字段" : "未找到可核验原文",
      available: Boolean(project.deadline),
    },
  ];
}


function selectVisibleInsights(
  insights: ReturnType<typeof projectInsights>,
  selectedKeys: string[],
) {
  if (selectedKeys.length) return insights.filter((insight) => selectedKeys.includes(insight.key));
  const priority = ["budget", "deadline", "qualification", "duration", "evaluation", "bond", "location", "payment"];
  return [...insights]
    .filter((insight) => insight.available)
    .sort((left, right) => {
      return priority.indexOf(left.key) - priority.indexOf(right.key);
    })
    .slice(0, 3);
}


function cleanDisplayText(value?: string): string {
  if (!value) return "";
  return value
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/(?:^|\s)[.#]?[\w-]+\s*\{[^{}]{0,1000}\}/g, " ")
    .replace(/(?:font-family|font-size|font-weight|line-height|border|width|height|display|color|background)\s*:[^;{}]+;?/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}


function formatBudget(value: ProjectSummary["budget"], fallback = "公告未披露"): string {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "number") {
    return new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY", maximumFractionDigits: 0 }).format(value);
  }
  return String(value);
}


function formatDeadline(value?: string): string {
  if (!value) return "以原公告为准";
  return formatDateTime(value);
}


function formatDate(value: string): string {
  if (!value) return "时间未披露";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 10);
  return date.toLocaleDateString("zh-CN");
}


function formatDateTime(value: string): string {
  if (!value) return "来源未披露";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  });
}


function frequencyLabel(value: ReportHistoryItem["frequency"]): string {
  if (value === "daily") return "每日更新";
  if (value === "weekly") return "每周更新";
  return "单次查询";
}


function reportRegion(item: ReportHistoryItem): string {
  const title = item.display_title || "";
  const match = title.match(/(?:全国|[一-龥]{2,8}(?:省|市|自治区))/);
  return match?.[0] || "项目报告";
}


function runStatusLabel(value: string): string {
  if (value === "completed") return "查询完成";
  if (value === "failed") return "查询失败";
  return value || "状态未知";
}


function reportStatus(report: ReportView): string {
  if (report.status === "missing") return "文件已丢失";
  if (report.status === "failed") return "生成失败";
  return "未生成";
}
