"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { WorkspaceSidebar } from "@/app/components/WorkspaceSidebar";
import { InfoTip } from "@/app/components/InfoTip";

import {
  deleteReportHistory,
  frequencyToApi,
  getLiveTask,
  listReports,
  listSourceCatalog,
  listSubscriptions,
  pauseLiveTask,
  startLiveTask,
  type LiveTask,
  type LiveTaskStage,
  type ReportHistoryItem,
  type SourceCatalogItem,
  type SubscriptionSummary,
} from "@/lib/tender-api";
import {
  FAVORITES_CHANGED_EVENT,
  readFavoriteProjects,
  removeFavoriteProject,
  type FavoriteProject,
} from "@/lib/favorite-projects";
import {
  INITIAL_MARKED_PROJECTS,
  markedProjectStatus,
  type MarkedProject,
} from "@/lib/marked-projects";

const FALLBACK_SOURCES: SourceCatalogItem[] = [
  {
    id: "ccgp",
    name: "中国政府采购网",
    category: "government",
    category_label: "政府 / 公共平台",
    url: "https://www.ccgp.gov.cn/",
    host: "ccgp.gov.cn",
    requires_auth: false,
    status: "ready",
    status_label: "已接入 · 可采集",
    detail: "财政部政府采购公告正式来源，已接入生产工作流。",
    collection_mode: "公开网页",
  },
  {
    id: "cmcc-b2b",
    name: "中国移动采购与招标网",
    category: "enterprise",
    category_label: "企业官网 / 行业协会",
    url: "https://b2b.10086.cn/",
    host: "b2b.10086.cn",
    requires_auth: false,
    status: "ready",
    status_label: "官方公开接口 · 可采集",
    detail: "公开公告与公告 PDF 已接入官方白名单接口；供应商业务区仍需单独授权。",
    collection_mode: "官方公开 API + PDF 归档",
  },
  {
    id: "tianyancha-bids",
    name: "天眼查开放平台 · 招投标搜索",
    category: "commercial",
    category_label: "商业聚合网站",
    url: "https://open.tianyancha.com/open/1063",
    host: "open.tianyancha.com",
    requires_auth: true,
    status: "needs_auth",
    status_label: "登录申请 Token",
    detail: "登录开放平台并申请接口 1063，在数据中心的“我的接口”获取 Token。",
    collection_mode: "开放平台 API 1063 · 约 ¥0.2/次",
  },
  {
    id: "ted-eu",
    name: "TED · 欧盟招标公告",
    category: "overseas",
    category_label: "海外采购 / 招标平台",
    url: "https://ted.europa.eu/",
    host: "ted.europa.eu",
    requires_auth: false,
    status: "ready",
    status_label: "官方 API · 可采集",
    detail: "欧盟出版局 Search API 支持匿名检索和公告复用。",
    collection_mode: "TED Search API v3",
  },
  {
    id: "ctba-news",
    name: "中国招标投标协会",
    category: "news",
    category_label: "新闻 / 行业资讯",
    url: "https://www.ctba.org.cn/",
    host: "ctba.org.cn",
    requires_auth: false,
    status: "ready",
    status_label: "公开资讯 · 可采集",
    detail: "行业政策、标准及招标投标动态公开来源。",
    collection_mode: "公开资讯页",
  },
];

const recommendations = [
  "上海市 太古里充电桩项目",
  "安徽省 高性能服务器项目",
  "江苏省 智慧医院建设项目",
  "浙江省 城市照明改造项目",
  "广东省 数据中心扩容项目",
  "北京市 人工智能平台项目",
  "四川省 新能源公交项目",
  "湖北省 校园网络升级项目",
  "山东省 工业机器人项目",
  "福建省 港口信息化项目",
  "湖南省 医疗设备采购项目",
  "河南省 云计算中心项目",
  "陕西省 智慧交通项目",
  "河北省 污水处理改造项目",
  "江西省 职业教育实训项目",
  "重庆市 应急指挥平台项目",
  "天津市 轨道交通维护项目",
  "云南省 文旅数字化项目",
];

function getBeijingClock() {
  const now = new Date();
  const timeParts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(now);
  const dateParts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const part = (parts: Intl.DateTimeFormatPart[], type: Intl.DateTimeFormatPartTypes) =>
    parts.find((item) => item.type === type)?.value ?? "--";

  return {
    time: `${part(timeParts, "hour")}:${part(timeParts, "minute")}:${part(timeParts, "second")}`,
    date: `${part(dateParts, "year")}年${part(dateParts, "month")}月${part(dateParts, "day")}日`,
  };
}

export default function Home() {
  const router = useRouter();
  const [clock, setClock] = useState({ time: "--:--:--", date: "----年--月--日" });
  const [query, setQuery] = useState("");
  const [selectedRecommendation, setSelectedRecommendation] = useState(recommendations[0]);
  const [favoriteRecommendations, setFavoriteRecommendations] = useState<string[]>([]);
  const [recommendationOffset, setRecommendationOffset] = useState(0);
  const [collecting, setCollecting] = useState(false);
  const [liveTask, setLiveTask] = useState<LiveTask | null>(null);
  const [collectionError, setCollectionError] = useState("");
  const [collectionSuccess, setCollectionSuccess] = useState("");
  const [sourcePanelOpen, setSourcePanelOpen] = useState(false);
  const [sourceWebsites, setSourceWebsites] = useState<SourceCatalogItem[]>(FALLBACK_SOURCES);
  const [sourceCatalogOnline, setSourceCatalogOnline] = useState(false);
  const [historyItems, setHistoryItems] = useState<ReportHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyManaging, setHistoryManaging] = useState(false);
  const [deletingRunId, setDeletingRunId] = useState("");
  const [visualStageIndex, setVisualStageIndex] = useState(0);
  const [subscriptions, setSubscriptions] = useState<SubscriptionSummary[]>([]);
  const [favoriteProjects, setFavoriteProjects] = useState<FavoriteProject[]>([]);
  const [favoritesManaging, setFavoritesManaging] = useState(false);
  const [addSourceOpen, setAddSourceOpen] = useState(false);
  const [sourceUrl, setSourceUrl] = useState("");
  const [sourceName, setSourceName] = useState("信息来源网站1");
  const [sourceError, setSourceError] = useState("");
  const [markedProjects] = useState<MarkedProject[]>(() => [
    ...INITIAL_MARKED_PROJECTS,
  ]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const sourceUrlRef = useRef<HTMLInputElement>(null);
  const sourceNavigationRef = useRef<HTMLElement>(null);
  const sourceSequenceRef = useRef(1);
  const workflowCarouselRef = useRef<HTMLOListElement>(null);
  const workflowScrollFrame = useRef<number | null>(null);
  const workflowUserUntil = useRef(0);
  const workflowProgrammaticUntil = useRef(0);

  useEffect(() => {
    const updateClock = () => setClock(getBeijingClock());
    updateClock();
    const timer = window.setInterval(updateClock, 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    let active = true;
    listSourceCatalog()
      .then(({ items }) => {
        if (!active || items.length === 0) return;
        setSourceWebsites(items);
        setSourceCatalogOnline(true);
      })
      .catch(() => setSourceCatalogOnline(false));
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    listReports()
      .then(({ items }) => {
        if (active) setHistoryItems(items.slice(0, 12));
      })
      .catch(() => {
        if (active) setHistoryItems([]);
      })
      .finally(() => {
        if (active) setHistoryLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!sourcePanelOpen) return;
    const closeOnOutside = (event: MouseEvent) => {
      if (!sourceNavigationRef.current?.contains(event.target as Node)) {
        setSourcePanelOpen(false);
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSourcePanelOpen(false);
    };
    document.addEventListener("mousedown", closeOnOutside);
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutside);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [sourcePanelOpen]);

  useEffect(() => {
    if (!addSourceOpen) return;
    sourceUrlRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setAddSourceOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [addSourceOpen]);

  useEffect(() => {
    let active = true;
    listSubscriptions()
      .then(({ items }) => {
        if (active) setSubscriptions(items.filter((item) => item.status !== "completed"));
      })
      .catch(() => {
        if (active) setSubscriptions([]);
      });
    return () => { active = false; };
  }, []);

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

  const visibleRecommendations = useMemo(
    () =>
      Array.from(
        { length: 6 },
        (_, index) => recommendations[(recommendationOffset + index) % recommendations.length],
      ),
    [recommendationOffset],
  );
  const readySourceCount = sourceWebsites.filter((source) => source.status === "ready").length;
  const sourceCategoryCount = new Set(sourceWebsites.map((source) => source.category)).size;

  function chooseRecommendation(item: string) {
    const [region, ...projectWords] = item.split(" ");
    setSelectedRecommendation(item);
    setQuery(`请帮我查找最近1个月${region}的${projectWords.join(" ")}招标信息，每周更新。`);
    textareaRef.current?.focus();
  }

  function toggleFavoriteRecommendation(item: string) {
    setFavoriteRecommendations((current) =>
      current.includes(item) ? current.filter((value) => value !== item) : [item, ...current],
    );
  }

  function addSourceWebsite(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const url = sourceUrl.trim();
    if (!url) {
      setSourceError("请输入信息来源网站的网址。");
      sourceUrlRef.current?.focus();
      return;
    }

    const sequence = sourceSequenceRef.current;
    const name = sourceName.trim() || `信息来源网站${sequence}`;
    let host = url;
    try {
      host = new URL(url).host;
    } catch {
      setSourceError("请输入完整且有效的网址。");
      sourceUrlRef.current?.focus();
      return;
    }
    const source: SourceCatalogItem = {
      id: `source-${sequence}`,
      name,
      url,
      host,
      category: "custom",
      category_label: "自定义来源",
      requires_auth: false,
      status: "restricted",
      status_label: "待评估 · 未采集",
      detail: "已登记网址；需要确认授权、页面结构和频率限制后才能接入。",
      collection_mode: "待评估",
    };

    sourceSequenceRef.current += 1;
    setSourceWebsites((current) => [source, ...current]);
    setSourceUrl("");
    setSourceName(`信息来源网站${sequence + 1}`);
    setSourceError("");
    setAddSourceOpen(false);
    setSourcePanelOpen(true);
  }

  function openMarkedProject(project: MarkedProject) {
    router.push(`/marked-projects/${encodeURIComponent(project.id)}`);
  }

  async function removeHistoryItem(item: ReportHistoryItem) {
    setDeletingRunId(item.run_id);
    try {
      await deleteReportHistory(item.run_id);
      setHistoryItems((current) => current.filter((candidate) => candidate.run_id !== item.run_id));
    } catch (reason) {
      setCollectionError(reason instanceof Error ? reason.message : "暂时无法移除该条记录");
    } finally {
      setDeletingRunId("");
    }
  }

  async function startCollection() {
    const effectiveQuery = query.trim();
    if (!effectiveQuery) {
      setCollectionError("请输入要查询的招投标主题或条件。");
      return;
    }
    setCollecting(true);
    setVisualStageIndex(0);
    setLiveTask(null);
    setCollectionError("");
    setCollectionSuccess("");
    try {
      let result = await startLiveTask(effectiveQuery, frequencyToApi(effectiveQuery));
      setLiveTask(result);
      while (result.status === "running" || result.status === "pausing") {
        await new Promise((resolve) => window.setTimeout(resolve, 650));
        result = await getLiveTask(result.job_id);
        setLiveTask(result);
      }
      if (result.status === "paused") {
        setCollectionSuccess("");
        setCollectionError(result.error_message || "检索已安全暂停，可修改条件后重新开始。 ");
        setCollecting(false);
        return;
      }
      if (result.status === "failed") {
        throw new Error(result.error_message || "真实检索链路执行失败");
      }
      if (result.subscription) {
        setSubscriptions((current) => [
          result.subscription!,
          ...current.filter((item) => item.task_id !== result.subscription!.task_id),
        ]);
      }
      setCollectionSuccess(
        result.status === "empty"
          ? "已完成全部信息源检索，未发现符合条件的在招项目。"
          : `真实检索完成，找到 ${result.project_count} 个有效项目。`,
      );
      setCollecting(false);
      window.setTimeout(() => {
        if (result.redirect_url) window.location.assign(result.redirect_url.replace("run_id=", "run="));
      }, 4600);
    } catch (reason) {
      setCollectionError(reason instanceof Error ? reason.message : "本地后端暂时无法完成收集任务");
      setCollecting(false);
    }
  }

  async function pauseCollection() {
    if (!liveTask || !collecting) return;
    try {
      const result = await pauseLiveTask(liveTask.job_id);
      setLiveTask(result);
      setCollectionSuccess("已发送暂停指令；当前请求结束后会安全停止，不会进入项目报告。");
    } catch (reason) {
      setCollectionError(reason instanceof Error ? reason.message : "暂时无法暂停检索");
    }
  }

  const displayedStages = liveTask?.stages ?? pendingStages();
  const activeStageIndex = displayedStages.findIndex(
    (stage) => stage.status === "running" || stage.status === "error",
  );
  const furthestReadyStage = activeStageIndex >= 0
    ? activeStageIndex
    : Math.max(
      0,
      displayedStages.reduce(
        (furthest, stage, index) => stage.status === "pending" ? furthest : index,
        0,
      ),
    );

  useEffect(() => {
    if (Date.now() < workflowUserUntil.current) return;
    setVisualStageIndex(furthestReadyStage);
  }, [furthestReadyStage]);

  useEffect(() => {
    const target = workflowCarouselRef.current?.querySelector<HTMLElement>(
      `[data-stage-index="${visualStageIndex}"]`,
    );
    workflowProgrammaticUntil.current = Date.now() + 800;
    target?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
  }, [visualStageIndex]);

  function markWorkflowInteraction() {
    workflowUserUntil.current = Date.now() + 3500;
  }

  function syncWorkflowFocus() {
    const carousel = workflowCarouselRef.current;
    if (
      !carousel
      || workflowScrollFrame.current !== null
      || Date.now() < workflowProgrammaticUntil.current
    ) return;
    workflowScrollFrame.current = window.requestAnimationFrame(() => {
      workflowScrollFrame.current = null;
      const center = carousel.getBoundingClientRect().left + carousel.clientWidth / 2;
      const items = Array.from(carousel.querySelectorAll<HTMLElement>("[data-stage-index]"));
      const nearest = items.reduce<{ index: number; distance: number }>(
        (current, item) => {
          const rect = item.getBoundingClientRect();
          const distance = Math.abs(rect.left + rect.width / 2 - center);
          const index = Number(item.dataset.stageIndex || 0);
          return distance < current.distance ? { index, distance } : current;
        },
        { index: visualStageIndex, distance: Number.POSITIVE_INFINITY },
      );
      setVisualStageIndex(nearest.index);
    });
  }

  return (
    <div className="brief-page">
      <WorkspaceSidebar active="workbench" />
      <div className="workbench-shell">
        <aside className="project-library" aria-label="检索历史">
          <header>
            <h2>检索历史</h2>
            <span className="library-count">{historyItems.length}</span>
            <button
              className={historyManaging ? "history-manage-button is-active" : "history-manage-button"}
              type="button"
              onClick={() => setHistoryManaging((current) => !current)}
            >{historyManaging ? "完成" : "管理"}</button>
          </header>
          {historyLoading && <p className="history-empty">正在读取最近记录…</p>}
          {!historyLoading && historyItems.length === 0 && (
            <p className="history-empty">完成第一次检索后，记录会出现在这里。</p>
          )}
          <ol className="search-history-list">
            {historyItems.map((item) => (
              <li key={item.run_id}>
                <Link href={`/reports?run=${encodeURIComponent(item.run_id)}`}>
                  <span>{formatHistoryDate(item.created_at)}</span>
                  <strong>{item.display_title || "未命名检索"}</strong>
                  <small>{item.project_count} 个项目 · 点击查看报告</small>
                </Link>
                {historyManaging && (
                  <button
                    className="history-delete-button"
                    type="button"
                    disabled={deletingRunId === item.run_id}
                    onClick={() => removeHistoryItem(item)}
                    aria-label={`删除${item.display_title || "该条检索"}`}
                  >{deletingRunId === item.run_id ? "…" : "×"}</button>
                )}
              </li>
            ))}
          </ol>
        </aside>

        <main className="workbench-center">
          <header className="workbench-topline">
            <div>
              <h1>招投标情报工作台</h1>
            </div>
            <div className="compact-clock" aria-label="北京时间">
              <time dateTime={clock.time}>{clock.time}</time>
              <span>{clock.date}</span>
            </div>
            <nav ref={sourceNavigationRef} className="source-navigation" aria-label="信息来源网站">
              <button
                className="source-pill"
                type="button"
                aria-expanded={sourcePanelOpen}
                aria-controls="source-catalog-panel"
                onClick={() => setSourcePanelOpen((current) => !current)}
              >
                <span className="source-pill-radar" aria-hidden="true"><i /><i /><i /></span>
                <span className="source-pill-copy"><strong>信息来源</strong><small>{sourceCategoryCount} 类 · {readySourceCount} 个可采集</small></span>
                <span className={`source-pill-live${sourceCatalogOnline ? " is-online" : ""}`} aria-hidden="true" />
                <span className={`source-pill-chevron${sourcePanelOpen ? " is-open" : ""}`} aria-hidden="true">⌄</span>
              </button>
              {sourcePanelOpen && (
                <section id="source-catalog-panel" className="source-catalog-panel" aria-label="信息来源详情">
                  <header className="source-catalog-header">
                    <div><span className="title-with-info"><h2>信息来源网络</h2><InfoTip text="只有经过真实接口验证或获得明确授权的来源，才会显示为可采集。" /></span></div>
                    <div className="source-catalog-legend" aria-label="状态说明"><span><i className="is-ready" />可采集</span><span><i className="is-blocked" />需授权 / 未接入</span></div>
                  </header>
                  <div className="source-catalog-grid">
                    {sourceWebsites.map((source) => (
                      <article className={`source-card status-${source.status}`} key={source.id}>
                        <div className="source-card-topline"><span className="source-category">{source.category_label}</span><span className="source-auth-badge">{source.id === "cmcc-b2b" ? "已登录" : source.requires_auth ? "需登录" : "免登录"}</span></div>
                        <h3>{source.name}</h3>
                        <a href={source.url} target="_blank" rel="noopener noreferrer">{source.host}<span aria-hidden="true">↗</span></a>
                        <p>{source.detail}</p>
                        <footer>
                          <span className="source-card-status"><i className="source-status-dot" aria-hidden="true" />{source.status_label}</span>
                          <small>{source.collection_mode}</small>
                          {source.requires_auth && source.status !== "ready" && <a className="source-connect-link" href={source.url} target="_blank" rel="noopener noreferrer">{source.id === "tianyancha-bids" ? "登录并申请 Token" : "打开登录 / 授权页"}</a>}
                        </footer>
                      </article>
                    ))}
                  </div>
                  <div className="source-catalog-actions"><p>账号、Cookie 和 API Key 不保存在浏览器中。</p><button className="add-source-button" type="button" onClick={() => { setSourceError(""); setAddSourceOpen(true); }}><span aria-hidden="true">＋</span>添加来源</button></div>
                </section>
              )}
            </nav>
          </header>

          <section className="search-composer" aria-label="投标对象输入">
            <span className="title-with-info composer-kicker">智能检索<InfoTip text="系统会自动理解条件、扩展关键词、检索来源、清洗查重，并为有效项目生成文档。" /></span>
            <textarea ref={textareaRef} value={query} onChange={(event) => { setQuery(event.target.value); if (!collecting) setLiveTask(null); }} placeholder="描述你想追踪的项目、地区、时间和更新频率…" aria-label="请输入您的投标对象" disabled={collecting} />
            <div className="composer-actions"><span /><div className="composer-action-buttons">{collecting && <button className="pause-button" type="button" onClick={pauseCollection} disabled={liveTask?.status === "pausing"}>{liveTask?.status === "pausing" ? "正在暂停…" : "暂停"}</button>}<button className="next-button" type="button" onClick={startCollection} disabled={collecting}>{collecting ? "正在自动处理…" : "开始检索"} <i aria-hidden="true">→</i></button></div></div>
            {collectionError && <p className="composer-feedback is-error" role="alert">{collectionError}</p>}
            {collectionSuccess && <p className="composer-feedback is-success" role="status">{collectionSuccess}</p>}
          </section>

          {(collecting || liveTask) ? (
            <section className="automation-progress" role="status" aria-live="polite" aria-label="自动检索进度">
              <ol ref={workflowCarouselRef} onScroll={syncWorkflowFocus} onPointerDown={markWorkflowInteraction} onTouchStart={markWorkflowInteraction} onWheel={markWorkflowInteraction}>
                {displayedStages.map((stage, index) => {
                  const distance = Math.abs(index - visualStageIndex);
                  return (
                  <li
                    className={`workflow-stage is-${stage.status} ${index === visualStageIndex ? "is-focus" : `is-distance-${Math.min(distance, 3)}`}`}
                    key={stage.id}
                    data-stage-index={index}
                  >
                    <span className="automation-step-marker" aria-label={stageStatusLabel(stage.status)}>
                      {stage.status === "success" ? "✓" : stage.status === "empty" || stage.status === "error" ? "×" : stage.number}
                    </span>
                    <div className="workflow-stage-copy">
                      <strong>{stage.title}</strong>
                      <small>{stage.summary}</small>
                      {index === visualStageIndex && <StageDetails stage={stage} />}
                      {stage.ai.status !== "pending" && (
                        <span className={`workflow-ai-proof is-${stage.ai.status}`}>
                          {stage.ai.label}
                          {stage.ai.model ? ` · ${stage.ai.model}` : ""}
                          {stage.ai.latency_ms ? ` · ${(stage.ai.latency_ms / 1000).toFixed(1)}s` : ""}
                        </span>
                      )}
                    </div>
                  </li>
                  );
                })}
              </ol>
            </section>
          ) : <section className="recommendation-section" aria-labelledby="recommendation-title">
            <div className="recommendation-controls">
              <div><h2 id="recommendation-title">为你推荐</h2></div>
              <button className="refresh-button" type="button" onClick={() => setRecommendationOffset((current) => (current + 6) % recommendations.length)}>换一批</button>
            </div>
            <div className="recommendation-grid">
              {visibleRecommendations.map((item) => (
                <article className={selectedRecommendation === item ? "recommendation-card is-selected" : "recommendation-card"} key={item}>
                  <button className="recommendation-card-main" type="button" onClick={() => chooseRecommendation(item)}>
                    <span>{item.split(" ")[0]}</span><strong>{item.split(" ").slice(1).join(" ")}</strong><small>查看检索预览</small>
                  </button>
                  <button className={favoriteRecommendations.includes(item) ? "recommendation-favorite is-favorite" : "recommendation-favorite"} type="button" aria-label={favoriteRecommendations.includes(item) ? `取消收藏${item}` : `收藏${item}`} onClick={() => toggleFavoriteRecommendation(item)}>☆</button>
                </article>
              ))}
            </div>
          </section>}
        </main>

        <aside className="result-inspector workbench-right-rail" aria-label="定时推送与收藏项目">
          <section className="scheduled-push-panel">
            <header><span className="title-with-info"><h2>定时推送</h2><InfoTip text="这里集中展示已启用的每日或每周自动检索任务，以及内置演示任务。" /></span><div className="rail-header-actions"><span className="library-count">{subscriptions.length + markedProjects.length}</span></div></header>
            <div className="scheduled-push-list">
              {subscriptions.map((item) => (
                <article key={item.task_id}>
                  <span>{frequencyDisplay(item.frequency)} · {item.local_time}</span>
                  <strong>{summarizeSubscription(item.query)}</strong>
                  <small>{item.status === "active" ? `下次 ${formatCompactDateTime(item.next_run_at)}` : "已暂停"}</small>
                </article>
              ))}
              {markedProjects.map((project) => (
                <button type="button" key={project.id} onClick={() => openMarkedProject(project)}><span>{project.region} · {project.frequency}</span><strong>{project.title}</strong><small>{markedProjectStatus(project)}</small></button>
              ))}
              {!subscriptions.length && !markedProjects.length && <p className="rail-empty">暂无定时任务。</p>}
            </div>
          </section>
          <section className="saved-projects-panel">
            <header>
              <span className="title-with-info"><h2>收藏项目</h2><InfoTip text="点击项目卡片进入报告；管理模式下点击右上角叉号可直接取消收藏。" /></span>
              <div className="rail-header-actions">
                <span className="library-count">{favoriteProjects.length + favoriteRecommendations.length}</span>
                <button className={favoritesManaging ? "history-manage-button is-active" : "history-manage-button"} type="button" onClick={() => setFavoritesManaging((current) => !current)}>{favoritesManaging ? "完成" : "管理"}</button>
              </div>
            </header>
            <div className="saved-project-list">
              {favoriteProjects.map((project) => (
                <div className="saved-project-card" key={`${project.runId}-${project.id}`}>
                  <button type="button" onClick={() => router.push(`/reports?run=${encodeURIComponent(project.runId)}`)}><span>{project.region || project.sourceName}</span><strong>{project.title}</strong><small>打开项目报告</small></button>
                  {favoritesManaging && <button className="favorite-remove-button" type="button" onClick={() => setFavoriteProjects(removeFavoriteProject(project))} aria-label={`取消收藏${project.title}`}>×</button>}
                </div>
              ))}
              {favoriteRecommendations.map((item) => (
                <div className="saved-project-card" key={item}><button type="button" onClick={() => chooseRecommendation(item)}><span>收藏检索</span><strong>{item}</strong><small>点击带回检索条件</small></button>{favoritesManaging && <button className="favorite-remove-button" type="button" onClick={() => setFavoriteRecommendations((current) => current.filter((value) => value !== item))} aria-label={`取消收藏${item}`}>×</button>}</div>
              ))}
              {!favoriteProjects.length && !favoriteRecommendations.length && <p className="rail-empty">暂无收藏项目</p>}
            </div>
          </section>
        </aside>
      </div>

      {addSourceOpen && (
        <div className="modal-backdrop source-modal-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setAddSourceOpen(false);
        }}>
          <section className="source-modal" role="dialog" aria-modal="true" aria-labelledby="source-modal-title">
            <div className="modal-heading">
              <p className="section-kicker">SOURCE CONNECTION</p>
              <h2 id="source-modal-title">添加信息来源网站</h2>
              <p>先登记网址，系统会将其标记为待评估；确认授权、登录方式和抓取频率后再接入。</p>
            </div>
            <form className="source-form" onSubmit={addSourceWebsite}>
              <label>
                <span>网站地址</span>
                <input
                  ref={sourceUrlRef}
                  type="url"
                  value={sourceUrl}
                  onChange={(event) => {
                    setSourceUrl(event.target.value);
                    setSourceError("");
                  }}
                  placeholder="请输入网址"
                  required
                />
              </label>
              <label>
                <span>来源名称</span>
                <input
                  value={sourceName}
                  onChange={(event) => setSourceName(event.target.value)}
                  placeholder="信息来源网站1"
                />
              </label>
              {sourceError && <p className="modal-error" role="alert">{sourceError}</p>}
              <div className="modal-actions">
                <button className="secondary-button" type="button" onClick={() => setAddSourceOpen(false)}>取消</button>
                <button className="primary-button" type="submit">确认</button>
              </div>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}


function pendingStages(): LiveTaskStage[] {
  return ["理解检索意图", "扩展同义词与相关词", "检索已接入信息源", "清洗、审核与查重", "生成项目 Word 文档"].map((title, index) => ({
    id: (["intent", "expansion", "sources", "cleaning", "documents"] as LiveTaskStage["id"][])[index],
    number: index + 1,
    title,
    status: index === 0 ? "running" : "pending",
    summary: index === 0 ? "正在调用智谱 AI 识别检索条件" : "等待上一步完成",
    details: {},
    ai: { status: "pending", label: "等待 AI 调用", call_count: 0 },
  }));
}


function StageDetails({ stage }: { stage: LiveTaskStage }) {
  const details = stage.details;
  return (
    <div className="workflow-stage-details">
      {details.fields && <dl>{details.fields.map((field) => <div key={field.label}><dt>{field.label}</dt><dd>{field.value}</dd></div>)}</dl>}
      {details.added_keywords && details.added_keywords.length > 0 && <KeywordTypewriter words={details.added_keywords} />}
      {details.search_phrases && details.search_phrases.length > 0 && <div className="workflow-phrases"><span>检索组合</span>{details.search_phrases.slice(0, 4).map((phrase) => <p key={phrase}>{phrase}</p>)}</div>}
      {details.sources && details.sources.length > 0 && <ul className="workflow-source-results">{details.sources.map((source) => <li key={source.source_id}><i className={`is-${source.status}`} /><strong>{source.name}</strong><span>{source.status === "failed" ? source.failure_reason || "抓取失败" : source.status === "empty" ? "未找到相关内容" : source.relevant_count !== null ? `${source.relevant_count} 条相关` : `${source.collected_count} 条候选`}</span></li>)}</ul>}
      {details.counts && <dl className="workflow-counts">{details.counts.map((count) => <div key={count.label}><dt>{count.label}</dt><dd>{count.value}</dd></div>)}</dl>}
    </div>
  );
}


function KeywordTypewriter({ words }: { words: string[] }) {
  const [visibleCount, setVisibleCount] = useState(0);
  const signature = words.join("\u0000");
  useEffect(() => {
    const timer = window.setInterval(() => {
      setVisibleCount((current) => {
        if (current >= words.length) {
          window.clearInterval(timer);
          return current;
        }
        return current + 1;
      });
    }, 260);
    return () => window.clearInterval(timer);
  }, [signature, words.length]);
  return (
    <div className="workflow-keywords" aria-live="polite">
      <span>新增检索词</span>
      <p>{words.slice(0, visibleCount).map((word) => <i key={word}>{word}</i>)}{visibleCount < words.length && <b className="typing-cursor" aria-hidden="true" />}</p>
    </div>
  );
}


function stageStatusLabel(status: LiveTaskStage["status"]): string {
  return { pending: "等待中", running: "执行中", success: "已完成", empty: "未找到内容", error: "执行失败" }[status];
}


function frequencyDisplay(value: SubscriptionSummary["frequency"]): string {
  return value === "daily" ? "每日" : value === "weekly" ? "每周" : "单次";
}


function summarizeSubscription(value: string): string {
  const cleaned = value.replace(/[，,]?每(天|日|周).*/, "").replace(/^(?:请|帮我|请帮我)+/, "").trim();
  return cleaned.length > 28 ? `${cleaned.slice(0, 28)}…` : cleaned || "定时招投标检索";
}


function formatCompactDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
}


function formatHistoryDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((item) => item.type === type)?.value ?? "--";
  return `${part("year")}.${part("month")}.${part("day")} ${part("hour")}:${part("minute")}:${part("second")}`;
}
