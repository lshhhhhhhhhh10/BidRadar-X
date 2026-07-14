import { AppShell } from "../components/AppShell";


export default function ReportsPage() {
  return (
    <AppShell active="reports">
      <section className="placeholder-page">
        <p className="eyebrow">DELIVERY MEMORY</p>
        <h1>报告、增量与长期记忆</h1>
        <p>该页面已预留报告下载、推送记录、来源水位线和用户反馈入口，具体功能将在第三阶段确定。</p>
        <div className="placeholder-grid">
          <div><span>01</span><strong>报告中心</strong><p>全量与增量报告统一管理。</p></div>
          <div><span>02</span><strong>推送记忆</strong><p>避免重复交付已知项目。</p></div>
          <div><span>03</span><strong>来源状态</strong><p>展示水位线和登录健康状态。</p></div>
        </div>
      </section>
    </AppShell>
  );
}
