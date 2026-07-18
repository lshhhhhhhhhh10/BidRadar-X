"use client";

import { useEffect, useMemo, useState } from "react";

import { AppShell } from "../components/AppShell";
import { InfoTip } from "../components/InfoTip";
import {
  connectSourceCredential,
  disconnectSourceCredential,
  getAIStatus,
  getSpendBudget,
  listSourceCatalog,
  setSpendBudget,
  type AIStatus,
  type SpendBudget,
  type SourceCatalogItem,
} from "@/lib/tender-api";

const FALLBACK_INTERFACES: SourceCatalogItem[] = [
  {
    id: "tianyancha-bids",
    name: "天眼查 · 招投标搜索",
    category: "commercial",
    category_label: "国内商业数据",
    url: "https://open.tianyancha.com/open/1063",
    host: "open.tianyancha.com",
    requires_auth: true,
    status: "needs_auth",
    status_label: "等待用户 Token",
    detail: "费用由当前使用者承担，按实际调用次数从其开放平台账户扣除。",
    collection_mode: "接口 1063 · 约 ¥0.2/次",
  },
];

export default function InterfacesPage() {
  const [items, setItems] = useState<SourceCatalogItem[]>(FALLBACK_INTERFACES);
  const [dailyLimit, setDailyLimit] = useState("20");
  const [selectedInterface, setSelectedInterface] = useState<SourceCatalogItem | null>(null);
  const [credential, setCredential] = useState("");
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [aiStatus, setAIStatus] = useState<AIStatus | null>(null);
  const [budget, setBudget] = useState<SpendBudget | null>(null);
  const [budgetSaving, setBudgetSaving] = useState(false);

  useEffect(() => {
    listSourceCatalog()
      .then(({ items: sources }) => {
        const managed = sources.filter((source) => source.id === "tianyancha-bids");
        if (managed.length > 0) setItems(managed);
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    getAIStatus().then(setAIStatus).catch(() => undefined);
    getSpendBudget().then((value) => {
      setBudget(value);
      setDailyLimit(value.daily_limit);
    }).catch(() => undefined);
  }, []);

  async function saveBudget() {
    setBudgetSaving(true);
    setFeedback("");
    try {
      const value = await setSpendBudget(dailyLimit);
      setBudget(value);
      setDailyLimit(value.daily_limit);
      setFeedback(`每日预算上限已保存为 ¥${value.daily_limit}。下一次付费请求若会超限，将在发出前被强制中断。`);
    } catch (reason) {
      setFeedback(reason instanceof Error ? reason.message : "预算上限保存失败");
    } finally {
      setBudgetSaving(false);
    }
  }

  async function saveCredential(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedInterface || !credential.trim()) return;
    setSaving(true);
    setFeedback("");
    try {
      const result = await connectSourceCredential(selectedInterface.id, credential.trim());
      setItems((current) => current.map((item) => item.id === selectedInterface.id
        ? {
            ...item,
            status: "ready",
            status_label: "凭据已载入 · 未发起测试",
            detail: `凭据 ${result.masked_credential} 仅保存在本次本地后端进程中；重启后需重新连接。`,
          }
        : item));
      setFeedback(`${selectedInterface.name} 已连接。保存过程没有调用付费接口。`);
      setCredential("");
      setSelectedInterface(null);
    } catch (reason) {
      setFeedback(reason instanceof Error ? reason.message : "连接失败，请稍后重试。");
    } finally {
      setSaving(false);
    }
  }

  async function disconnect(item: SourceCatalogItem) {
    setSaving(true);
    setFeedback("");
    try {
      await disconnectSourceCredential(item.id);
      setItems((current) => current.map((source) => source.id === item.id
        ? {
            ...source,
            status: "needs_auth",
            status_label: source.id === "tianyancha-bids" ? "等待用户 Token" : "等待用户 API Key",
            detail: "凭据已从本地后端进程移除，不会继续调用该账户。",
          }
        : source));
      setFeedback(`${item.name} 已断开。`);
    } catch (reason) {
      setFeedback(reason instanceof Error ? reason.message : "断开失败，请稍后重试。");
    } finally {
      setSaving(false);
    }
  }

  const connectedCount = useMemo(
    () => items.filter((item) => item.status === "ready").length,
    [items],
  );
  const paidCount = useMemo(
    () => items.filter((item) => item.collection_mode.includes("¥")).length,
    [items],
  );

  return (
    <AppShell active="interfaces">
      <section className="interface-page">
        <header className="interface-page-header">
          <div>
            <h1>接口管理</h1>
            <p>每位使用者连接自己的数据账户、承担自己的调用费用。系统只负责调用和记录。</p>
          </div>
          <span className="privacy-chip">密钥仅由服务端读取</span>
        </header>

        {feedback && <div className="interface-feedback" role="status">{feedback}</div>}

        <article className="ai-readiness-card" aria-label="AI 处理引擎状态">
          <div className="managed-interface-icon" aria-hidden="true">AI</div>
          <div>
            <h2>智能处理引擎</h2>
            <p>
              已接入需求理解、检索扩词、检索规划、相关性复核、歧义去重、事实核验和证据化报告。
              API Key 仅由后端本机载入，前端代码与浏览器均不会保存。
            </p>
          </div>
          <div className={`ai-readiness-state ${aiStatus?.enabled ? "is-ready" : "is-waiting"}`}>
            <i aria-hidden="true" />
            <strong>{aiStatus?.enabled ? "已自动启用" : "等待后端密钥"}</strong>
            <small>{aiStatus ? `${aiStatus.provider} · ${aiStatus.model}` : "智谱模型由后端配置"}</small>
          </div>
        </article>

        <div className="interface-summary-grid" aria-label="接口概况">
          <article><span>已连接</span><strong>{connectedCount}</strong><small>个授权接口</small></article>
          <article><span>待连接</span><strong>{items.length - connectedCount}</strong><small>个需要用户凭据</small></article>
          <article><span>付费接口</span><strong>{paidCount}</strong><small>费用归当前使用者</small></article>
        </div>

        <div className="interface-management-grid">
          <section className="interface-list-panel" aria-labelledby="managed-interface-title">
            <div className="panel-title-row">
              <div>
                <h2 id="managed-interface-title">我的接口</h2>
              </div>
              <span>{items.length} 个</span>
            </div>
            <div className="managed-interface-list">
              {items.map((item) => (
                <article className="managed-interface-card" key={item.id}>
                  <div className="managed-interface-icon" aria-hidden="true">
                    {item.id === "tianyancha-bids" ? "天" : "API"}
                  </div>
                  <div className="managed-interface-copy">
                    <div>
                      <h3>{item.name}</h3>
                      <span className={`connection-state state-${item.status}`}>
                        <i aria-hidden="true" />{item.status_label}
                      </span>
                    </div>
                    <p>{item.detail}</p>
                    <dl>
                      <div><dt>计费方式</dt><dd>{item.collection_mode}</dd></div>
                      <div><dt>费用承担</dt><dd>当前使用者</dd></div>
                      <div><dt>凭据类型</dt><dd>{item.id === "tianyancha-bids" ? "Token" : "API Key"}</dd></div>
                    </dl>
                  </div>
                  <div className="interface-card-actions">
                    <a href={item.url} target="_blank" rel="noreferrer">开放平台</a>
                    <button type="button" onClick={() => { setCredential(""); setSelectedInterface(item); }}>
                      {item.status === "ready" ? "更新凭据" : "连接"}
                    </button>
                    {item.status === "ready" && (
                      <button className="disconnect-button" type="button" disabled={saving} onClick={() => void disconnect(item)}>断开</button>
                    )}
                  </div>
                </article>
              ))}
            </div>
          </section>

          <aside className="interface-policy-panel" aria-labelledby="spend-policy-title">
            <span className="title-with-info"><h2 id="spend-policy-title">预算上限</h2><InfoTip text="限额保存在本地后端。每次付费接口调用前都会原子检查，预计费用会使当日累计超限时，请求不会发出。" /></span>
            <label className="spend-limit-field">
              <span>每日预算上限</span>
              <span className="currency-input"><b>¥</b><input type="number" min="0" step="0.01" value={dailyLimit} onChange={(event) => setDailyLimit(event.target.value)} /></span>
            </label>
            <button className="budget-save-button" type="button" onClick={saveBudget} disabled={budgetSaving}>{budgetSaving ? "正在保存…" : "保存上限"}</button>
            <div className="policy-roadmap"><strong>后端强制拦截已开启</strong><small>今日已用 ¥{budget?.spent_today ?? "0.00"} · 剩余 ¥{budget?.remaining ?? dailyLimit}</small></div>
            <div className="policy-note">
              <strong>凭据安全</strong>
              <p>不要把 Token 放进截图或聊天。连接后只保存在本次本地后端进程内存中，重启服务即清除。</p>
            </div>
          </aside>
        </div>
      </section>

      {selectedInterface && (
        <div className="credential-dialog-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.currentTarget === event.target && !saving) setSelectedInterface(null);
        }}>
          <section className="credential-dialog" role="dialog" aria-modal="true" aria-labelledby="credential-dialog-title">
            <button className="credential-dialog-close" type="button" aria-label="关闭" disabled={saving} onClick={() => setSelectedInterface(null)}>×</button>
            <h2 id="credential-dialog-title">连接 {selectedInterface.name}</h2>
            <p>请填写你在开放平台获得的{selectedInterface.id === "tianyancha-bids" ? " Token" : " API Key"}。保存时不做测试请求，因此不会产生本次验证费用。</p>
            <form onSubmit={saveCredential}>
              <label htmlFor="source-credential">{selectedInterface.id === "tianyancha-bids" ? "Token" : "API Key"}</label>
              <input
                id="source-credential"
                type="password"
                autoComplete="off"
                minLength={8}
                maxLength={512}
                value={credential}
                onChange={(event) => setCredential(event.target.value)}
                placeholder="仅发送到 127.0.0.1 本地后端"
                autoFocus
              />
              <small>不会写入浏览器存储或项目文件；后端重启后需要重新填写。</small>
              <div>
                <button type="button" disabled={saving} onClick={() => setSelectedInterface(null)}>取消</button>
                <button type="submit" disabled={saving || credential.trim().length < 8}>{saving ? "正在连接…" : "安全连接"}</button>
              </div>
            </form>
          </section>
        </div>
      )}
    </AppShell>
  );
}
