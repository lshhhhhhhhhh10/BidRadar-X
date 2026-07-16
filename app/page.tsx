"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { frequencyToApi, runTask, type ExtractedFields } from "@/lib/tender-api";
import {
  isShanghaiPropertyDemoQuery,
  SHANGHAI_PROPERTY_DEMO_FIELDS,
  SHANGHAI_PROPERTY_DEMO_ID,
} from "@/lib/demo-tenders";
import {
  INITIAL_MARKED_PROJECTS,
  markedProjectStatus,
  type MarkedProject,
} from "@/lib/marked-projects";

const EMPTY_FIELD = "无（可编辑）";

type SourceWebsite = {
  id: string;
  name: string;
  url: string;
  loggedIn: boolean;
};

type LoginTarget = { type: "source"; sourceId: string; name: string; url: string };

const SWORDFISH_URL = "https://www.jianyu360.com/";

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

const regionPattern = /(北京市|天津市|上海市|重庆市|安徽省|江苏省|浙江省|广东省|四川省|湖北省|山东省|福建省|湖南省|河南省|陕西省|河北省|江西省|云南省|贵州省|海南省|青海省|甘肃省|辽宁省|吉林省|黑龙江省|山西省|内蒙古自治区|广西壮族自治区|西藏自治区|宁夏回族自治区|新疆维吾尔自治区|香港特别行政区|澳门特别行政区)/;

const subjectMatchers: Array<[RegExp, string]> = [
  [/GPU服务器|高性能服务器|机架式服务器|存储服务器|服务器/, "服务器"],
  [/充电桩|充电站|新能源充电/, "充电桩"],
  [/人工智能|大模型|AI平台|智能计算/, "人工智能"],
  [/医疗设备|医学影像|医院设备/, "医疗设备"],
  [/智慧交通|轨道交通|交通平台/, "交通"],
  [/数据中心|云计算|算力中心/, "数据中心"],
  [/校园网|网络升级|网络改造/, "网络"],
];

function extractInformation(text: string): ExtractedFields {
  if (isShanghaiPropertyDemoQuery(text)) {
    return { ...SHANGHAI_PROPERTY_DEMO_FIELDS };
  }

  const compactText = text.replace(/\s+/g, " ").trim();
  const region = compactText.match(regionPattern)?.[1] ?? EMPTY_FIELD;
  const matchedSubject = subjectMatchers.find(([pattern]) => pattern.test(compactText))?.[1];
  const regionTail = region === EMPTY_FIELD
    ? compactText
    : compactText.slice(compactText.indexOf(region) + region.length);
  const inferredSubject = regionTail
    .match(/^(?:区域内|范围内|内)?的?(.{2,30}?)(?:招标信息|招标公告|采购信息)/)?.[1]
    ?.replace(/项目$/, "")
    .trim();
  const subject = matchedSubject ?? inferredSubject ?? EMPTY_FIELD;

  let time = EMPTY_FIELD;
  const relativeTime = compactText.match(/(?:最近|近)\s*([一二三四五六七八九十\d]+)\s*(天|周|个月|月|年)/);
  const dateRange = compactText.match(/(20\d{2}年\d{1,2}月\d{1,2}日?\s*(?:至|到|—|-)\s*20\d{2}年\d{1,2}月\d{1,2}日?)/);
  if (relativeTime) time = `最近${relativeTime[1]}${relativeTime[2]}`;
  else if (dateRange) time = dateRange[1];
  else if (/本月/.test(compactText)) time = "本月";
  else if (/本周/.test(compactText)) time = "本周";

  let frequency = EMPTY_FIELD;
  if (/每天|每日/.test(compactText)) frequency = "每日";
  else if (/每周|每星期/.test(compactText)) frequency = "每周";
  else if (/每月|每个月/.test(compactText)) frequency = "每月";
  else if (/立即|马上|现在/.test(compactText)) frequency = "立即执行";
  else if (/一次性|仅一次|只查一次/.test(compactText)) frequency = "仅一次";

  return { subject, region, time, frequency };
}

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
  const [modalOpen, setModalOpen] = useState(false);
  const [recommendationOffset, setRecommendationOffset] = useState(0);
  const [collecting, setCollecting] = useState(false);
  const [collectionError, setCollectionError] = useState("");
  const [collectionSuccess, setCollectionSuccess] = useState("");
  const [swordfishLoggedIn, setSwordfishLoggedIn] = useState(false);
  const [sourceWebsites, setSourceWebsites] = useState<SourceWebsite[]>([]);
  const [addSourceOpen, setAddSourceOpen] = useState(false);
  const [sourceUrl, setSourceUrl] = useState("");
  const [sourceName, setSourceName] = useState("信息来源网站1");
  const [sourceError, setSourceError] = useState("");
  const [loginTarget, setLoginTarget] = useState<LoginTarget | null>(null);
  const [markedProjects, setMarkedProjects] = useState<MarkedProject[]>(() => [
    ...INITIAL_MARKED_PROJECTS,
  ]);
  const [fields, setFields] = useState<ExtractedFields>({
    subject: EMPTY_FIELD,
    region: EMPTY_FIELD,
    time: EMPTY_FIELD,
    frequency: EMPTY_FIELD,
  });
  const firstInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const sourceUrlRef = useRef<HTMLInputElement>(null);
  const loginButtonRef = useRef<HTMLButtonElement>(null);
  const sourceSequenceRef = useRef(1);

  useEffect(() => {
    const updateClock = () => setClock(getBeijingClock());
    updateClock();
    const timer = window.setInterval(updateClock, 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!modalOpen) return;
    firstInputRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setModalOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [modalOpen]);

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
    if (!loginTarget) return;
    loginButtonRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setLoginTarget(null);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [loginTarget]);

  const visibleRecommendations = useMemo(
    () =>
      Array.from(
        { length: 6 },
        (_, index) => recommendations[(recommendationOffset + index) % recommendations.length],
      ),
    [recommendationOffset],
  );

  function openConfirmation() {
    setFields(extractInformation(query));
    setModalOpen(true);
  }

  function chooseRecommendation(item: string) {
    const [region, ...projectWords] = item.split(" ");
    setQuery(`请帮我查找最近1个月${region}的${projectWords.join(" ")}招标信息，每周更新。`);
    textareaRef.current?.focus();
  }

  function updateField(field: keyof ExtractedFields, value: string) {
    setFields((current) => ({ ...current, [field]: value }));
  }

  function openSourceLogin(source: SourceWebsite) {
    setLoginTarget({
      type: "source",
      sourceId: source.id,
      name: source.name,
      url: source.url,
    });
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
    const source: SourceWebsite = {
      id: `source-${sequence}`,
      name,
      url,
      loggedIn: false,
    };

    sourceSequenceRef.current += 1;
    setSourceWebsites((current) => [source, ...current]);
    setSourceUrl("");
    setSourceName(`信息来源网站${sequence + 1}`);
    setSourceError("");
    setAddSourceOpen(false);
  }

  function completeMockLogin() {
    if (!loginTarget) return;
    setSourceWebsites((current) =>
      current.map((source) =>
        source.id === loginTarget.sourceId ? { ...source, loggedIn: true } : source,
      ),
    );
    setLoginTarget(null);
  }

  function openMarkedProject(project: MarkedProject) {
    router.push(`/marked-projects/${encodeURIComponent(project.id)}`);
  }

  function removeMarkedProject(
    event: React.MouseEvent<HTMLButtonElement>,
    projectId: string,
  ) {
    event.stopPropagation();
    setMarkedProjects((current) => current.filter((project) => project.id !== projectId));
  }

  async function startCollection() {
    const effectiveQuery = query.trim();
    if (!effectiveQuery) {
      setCollectionError("请输入要查询的招投标主题或条件。");
      return;
    }
    setCollecting(true);
    setCollectionError("");
    setCollectionSuccess("");
    try {
      if (isShanghaiPropertyDemoQuery(effectiveQuery)) {
        setCollectionSuccess("演示数据已就绪，正在打开 10 条核验公告…");
        window.location.assign(`/projects?demo=${SHANGHAI_PROPERTY_DEMO_ID}`);
        return;
      }
      const subject = fields.subject === EMPTY_FIELD ? undefined : fields.subject.trim() || undefined;
      const region = fields.region === EMPTY_FIELD ? undefined : fields.region.trim() || undefined;
      const result = await runTask(effectiveQuery, frequencyToApi(fields.frequency), {
        subject,
        region,
      });
      setCollectionSuccess("任务运行成功，正在打开本次真实结果…");
      window.setTimeout(() => {
        window.location.assign(
          `/projects?run=${encodeURIComponent(result.run_id)}&task=${encodeURIComponent(result.task_id)}`,
        );
      }, 50);
    } catch (reason) {
      setCollectionError(reason instanceof Error ? reason.message : "本地后端暂时无法完成收集任务");
      setCollecting(false);
    }
  }

  return (
    <div className="brief-page">
      <nav className="source-navigation" aria-label="信息来源网站登录">
        <div className="source-navigation-list">
          {sourceWebsites.map((source) => (
            <button
              className={`source-login-button${source.loggedIn ? " is-logged-in" : ""}`}
              type="button"
              key={source.id}
              onClick={() => openSourceLogin(source)}
              title={source.url}
            >
              <span className="source-status-dot" aria-hidden="true" />
              {`${source.name}（${source.loggedIn ? "已登录" : "未登录"}）`}
            </button>
          ))}
          <a
            className={`source-login-button${swordfishLoggedIn ? " is-logged-in" : ""}`}
            href={SWORDFISH_URL}
            target="_blank"
            rel="noopener noreferrer"
            onClick={() => setSwordfishLoggedIn(true)}
          >
            <span className="source-status-dot" aria-hidden="true" />
            {`剑鱼（${swordfishLoggedIn ? "已登录" : "未登录"}）`}
          </a>
          <button
            className="add-source-button"
            type="button"
            onClick={() => {
              setSourceError("");
              setAddSourceOpen(true);
            }}
          >
            <span aria-hidden="true">＋</span>
            添加信息来源网站
          </button>
        </div>
      </nav>

      <header className="clock-header" aria-label="北京时间">
        <p className="clock-zone">北京时间</p>
        <time className="clock-time" dateTime={clock.time}>{clock.time}</time>
        <time className="clock-date" dateTime={clock.date}>{clock.date}</time>
      </header>

      <main className="brief-main">
        <section className="input-section" aria-label="投标对象输入">
          <div className="textarea-frame">
            <textarea
              ref={textareaRef}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="对话框，请输入您的投标对象。"
              aria-label="请输入您的投标对象"
            />
            <button className="next-button" type="button" onClick={openConfirmation}>
              下一步
            </button>
          </div>
        </section>

        <section className="recommendation-section" aria-labelledby="recommendation-title">
          <div className="recommendation-controls">
            <div>
              <p className="section-kicker">DISCOVER</p>
              <h2 id="recommendation-title">热门推荐</h2>
            </div>
            <button
              className="refresh-button"
              type="button"
              onClick={() => setRecommendationOffset((current) => (current + 6) % recommendations.length)}
            >
              换一批
            </button>
          </div>
          <div className="recommendation-grid">
            {visibleRecommendations.map((item) => (
              <button className="recommendation-card" type="button" key={item} onClick={() => chooseRecommendation(item)}>
                <span>{item.split(" ")[0]}</span>
                <strong>{item.split(" ").slice(1).join(" ")}</strong>
              </button>
            ))}
          </div>
        </section>

        <section className="marked-project-section" aria-labelledby="marked-project-title">
          <div className="marked-project-heading">
            <p className="section-kicker">MARKED PROJECTS</p>
            <h2 id="marked-project-title">标记的项目</h2>
          </div>
          {markedProjects.length > 0 ? (
            <div className="marked-project-grid">
              {markedProjects.map((project) => (
                <article
                  className={`marked-project-card${project.hasUpdates ? " has-updates" : ""}`}
                  key={project.id}
                  role="link"
                  tabIndex={0}
                  aria-label={`打开${project.title}最后一次更新页面`}
                  onClick={() => openMarkedProject(project)}
                  onKeyDown={(event) => {
                    if (event.target !== event.currentTarget) return;
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      openMarkedProject(project);
                    }
                  }}
                >
                  <button
                    className="marked-project-close"
                    type="button"
                    aria-label={`取消标记${project.title}`}
                    onClick={(event) => removeMarkedProject(event, project.id)}
                  >
                    <span aria-hidden="true">×</span>
                  </button>
                  <header className="marked-project-card-title">
                    <span>{project.region}</span>
                    <h3>{project.title}</h3>
                  </header>
                  <div className="marked-project-brief">
                    <p className="marked-project-brief-label">LATEST UPDATE</p>
                    <p>{project.summary}</p>
                    <dl>
                      <div><dt>执行频率</dt><dd>{project.frequency}</dd></div>
                      <div><dt>本次新增</dt><dd>{project.newItemCount} 条</dd></div>
                      <div><dt>过滤重复</dt><dd>{project.filteredDuplicateCount} 条</dd></div>
                      <div><dt>更新区域</dt><dd>{project.region}</dd></div>
                    </dl>
                  </div>
                  <footer className="marked-project-status">
                    <strong>{markedProjectStatus(project)}</strong>
                    <small>{project.hasUpdates ? `${project.newItemCount} 条新增内容` : "本次无新增"}</small>
                  </footer>
                </article>
              ))}
            </div>
          ) : (
            <div className="marked-project-empty">暂无标记项目。</div>
          )}
        </section>
      </main>

      {modalOpen && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setModalOpen(false);
        }}>
          <section className="extraction-modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
            <div className="modal-heading">
              <p className="section-kicker">LOCAL RULE EXTRACTION</p>
              <h2 id="modal-title">请确认识别结果</h2>
              <p>以下内容由前端关键词规则模拟提取，所有字段均可修改。</p>
            </div>
            <div className="field-list">
              {([
                ["subject", "主题"],
                ["region", "区域"],
                ["time", "时间"],
                ["frequency", "频率"],
              ] as Array<[keyof ExtractedFields, string]>).map(([field, label], index) => (
                <label className="field-row" key={field}>
                  <span>{label}</span>
                  <input
                    ref={index === 0 ? firstInputRef : undefined}
                    value={fields[field]}
                    onChange={(event) => updateField(field, event.target.value)}
                  />
                </label>
              ))}
            </div>
            {collectionError && <p className="modal-error" role="alert">{collectionError}</p>}
            {collectionSuccess && <p className="modal-success" role="status">{collectionSuccess}</p>}
            <div className="modal-actions">
              <button className="secondary-button" type="button" onClick={() => setModalOpen(false)}>返回修改</button>
              <button className="primary-button" type="button" onClick={startCollection} disabled={collecting}>
                {collecting ? "正在收集…" : "下一步"}
              </button>
            </div>
          </section>
        </div>
      )}

      {addSourceOpen && (
        <div className="modal-backdrop source-modal-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setAddSourceOpen(false);
        }}>
          <section className="source-modal" role="dialog" aria-modal="true" aria-labelledby="source-modal-title">
            <div className="modal-heading">
              <p className="section-kicker">SOURCE CONNECTION</p>
              <h2 id="source-modal-title">添加信息来源网站</h2>
              <p>添加后会在首页生成独立登录入口。本演示不会访问或验证外部网站。</p>
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

      {loginTarget && (
        <div className="mock-login-screen" role="dialog" aria-modal="true" aria-labelledby="mock-login-title">
          <div className="mock-login-topbar">
            <button type="button" onClick={() => setLoginTarget(null)} aria-label="返回首页">← 返回首页</button>
            <span>模拟外部登录页面</span>
          </div>
          <div className="mock-login-stage">
            <section className="mock-login-card">
              <div className="mock-login-brand" aria-hidden="true">{loginTarget.name.slice(0, 1)}</div>
              <p className="section-kicker">OFFICIAL LOGIN · DEMO</p>
              <h2 id="mock-login-title">登录 {loginTarget.name}</h2>
              <p className="mock-login-description">这是用于产品演示的模拟登录页面。点击登录后将直接返回招投标情报工作台。</p>
              <div className="mock-login-domain">{loginTarget.url}</div>
              <div className="mock-credential-fields" aria-label="模拟账号信息">
                <label>
                  <span>账号</span>
                  <input value="demo_user" readOnly />
                </label>
                <label>
                  <span>密码</span>
                  <input type="password" value="demopass" readOnly />
                </label>
              </div>
              <button ref={loginButtonRef} className="mock-login-submit" type="button" onClick={completeMockLogin}>
                登录
              </button>
              <small>仅模拟状态切换，不会发送账号、密码或访问外部站点。</small>
            </section>
          </div>
        </div>
      )}
    </div>
  );
}
