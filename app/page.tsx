"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { frequencyToApi, runTask, type ExtractedFields } from "@/lib/tender-api";

const EMPTY_FIELD = "无（可编辑）";

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
  [/GPU服务器|高性能服务器|机架式服务器|存储服务器|服务器/, "服务器采购"],
  [/充电桩|充电站|新能源充电/, "充电桩建设"],
  [/人工智能|大模型|AI平台|智能计算/, "人工智能平台"],
  [/医疗设备|医学影像|医院设备/, "医疗设备采购"],
  [/智慧交通|轨道交通|交通平台/, "智慧交通建设"],
  [/数据中心|云计算|算力中心/, "数据中心建设"],
  [/校园网|网络升级|网络改造/, "网络建设"],
];

function extractInformation(text: string): ExtractedFields {
  const compactText = text.replace(/\s+/g, " ").trim();
  const subject = subjectMatchers.find(([pattern]) => pattern.test(compactText))?.[1] ?? EMPTY_FIELD;
  const region = compactText.match(regionPattern)?.[1] ?? EMPTY_FIELD;

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
  const [clock, setClock] = useState({ time: "--:--:--", date: "----年--月--日" });
  const [query, setQuery] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [recommendationOffset, setRecommendationOffset] = useState(0);
  const [collecting, setCollecting] = useState(false);
  const [collectionError, setCollectionError] = useState("");
  const [collectionSuccess, setCollectionSuccess] = useState("");
  const [fields, setFields] = useState<ExtractedFields>({
    subject: EMPTY_FIELD,
    region: EMPTY_FIELD,
    time: EMPTY_FIELD,
    frequency: EMPTY_FIELD,
  });
  const firstInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

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
      const result = await runTask(effectiveQuery, frequencyToApi(fields.frequency));
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
    </div>
  );
}
