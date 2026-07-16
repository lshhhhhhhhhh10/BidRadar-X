"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import styles from "./page.module.css";
import {
  SHANGHAI_PROPERTY_DEMO_ID,
  SHANGHAI_PROPERTY_DEMO_PROJECTS,
  SHANGHAI_PROPERTY_DEMO_QUERY,
  SHANGHAI_PROPERTY_DEMO_VERIFIED_AT,
} from "@/lib/demo-tenders";
import { createRequirementTemplates } from "@/lib/mock-requirements-parser";
import { resolveApiUrl, type ProjectProfile, type ProjectSummary } from "@/lib/tender-api";


type ViewMode = "cumulative" | "additions";

type DemoScheduledRun = {
  id: string;
  executedAt: string;
  label: string;
  collectedCount: number;
  duplicateCount: number;
  addedProjectIds: string[];
};

const DEMO_RUNS: DemoScheduledRun[] = [
  {
    id: "20260713-0900",
    executedAt: "2026-07-13 09:00",
    label: "首次定时执行",
    collectedCount: 5,
    duplicateCount: 0,
    addedProjectIds: [
      "demo-ceb-property-customer-maintenance",
      "demo-ceb-jiangyang-cleaning",
      "demo-ceb-wangnibang-cleaning",
      "demo-ceb-vehicle-cleaning",
      "demo-jianyu-wanan-cleaning",
    ],
  },
  {
    id: "20260714-0900",
    executedAt: "2026-07-14 09:00",
    label: "第 2 次定时执行",
    collectedCount: 8,
    duplicateCount: 5,
    addedProjectIds: [
      "demo-ceb-yard-cleaning-materials",
      "demo-ceb-caohan-green-maintenance",
      "demo-ceb-jinshan-green-maintenance",
    ],
  },
  {
    id: "20260715-0900",
    executedAt: "2026-07-15 09:00",
    label: "第 3 次定时执行",
    collectedCount: 10,
    duplicateCount: 8,
    addedProjectIds: [
      "demo-ceb-laogang-maintenance",
      "demo-shggzy-beiai-property",
    ],
  },
];


export default function ShanghaiPropertyReportPreviewPage() {
  const [selectedRunId, setSelectedRunId] = useState("20260715-0900");
  const [viewMode, setViewMode] = useState<ViewMode>("cumulative");
  const selectedRunIndex = DEMO_RUNS.findIndex((run) => run.id === selectedRunId);
  const selectedRun = DEMO_RUNS[selectedRunIndex] ?? DEMO_RUNS[0];

  const cumulativeProjectIds = useMemo(
    () => new Set(
      DEMO_RUNS
        .slice(0, selectedRunIndex + 1)
        .flatMap((run) => run.addedProjectIds),
    ),
    [selectedRunIndex],
  );
  const addedProjectIds = useMemo(
    () => new Set(selectedRun.addedProjectIds),
    [selectedRun],
  );
  const visibleProjects = SHANGHAI_PROPERTY_DEMO_PROJECTS.filter((project) => (
    viewMode === "additions"
      ? addedProjectIds.has(project.project_id)
      : cumulativeProjectIds.has(project.project_id)
  ));
  const downloadUrl = selectedRun.addedProjectIds.length > 0
    ? resolveApiUrl(`/api/demo/reports/shanghai-property/runs/${selectedRun.id}/download`)
    : null;

  return (
    <main className={styles.workspace}>
      <header className={styles.topbar}>
        <div>
          <p className={styles.kicker}>INCREMENTAL REPORT PREVIEW</p>
          <h1>Word 报告查看</h1>
          <p>选择一次运行，页面标出当次新增；下载文件保持正式、无高亮。</p>
        </div>
        <div className={styles.topActions}>
          <Link href={`/projects?demo=${SHANGHAI_PROPERTY_DEMO_ID}`}>返回项目结果</Link>
          {downloadUrl ? (
            <a className={styles.primaryAction} href={downloadUrl}>下载本次增量 Word</a>
          ) : (
            <span className={styles.disabledAction} aria-disabled="true">本次无新增，不生成 Word</span>
          )}
        </div>
      </header>

      <div className={styles.layout}>
        <aside className={styles.runPanel} aria-label="定时运行记录">
          <div className={styles.scheduleCard}>
            <span>执行频率</span>
            <strong>每天 09:00</strong>
            <small>主题：物业管理服务项目 · 区域：上海</small>
          </div>
          <h2>运行记录</h2>
          <ol className={styles.runList}>
            {DEMO_RUNS.map((run) => {
              const active = run.id === selectedRun.id;
              return (
                <li key={run.id}>
                  <button
                    className={active ? styles.activeRun : styles.runButton}
                    onClick={() => setSelectedRunId(run.id)}
                    type="button"
                    aria-pressed={active}
                  >
                    <span>{run.executedAt}</span>
                    <strong>{run.label}</strong>
                    <small>
                      新增 {run.addedProjectIds.length} 条 · 过滤重复 {run.duplicateCount} 条
                    </small>
                  </button>
                </li>
              );
            })}
          </ol>
          <div className={styles.legend}>
            <p><i className={styles.newDot} />本次新增</p>
            <p><i className={styles.historyDot} />历史已推送</p>
          </div>
        </aside>

        <section className={styles.previewColumn}>
          <div className={styles.previewToolbar}>
            <div>
              <strong>{selectedRun.executedAt}</strong>
              <span>{selectedRun.label}</span>
            </div>
            <div className={styles.modeSwitch} aria-label="报告查看模式">
              <button
                className={viewMode === "cumulative" ? styles.selectedMode : undefined}
                onClick={() => setViewMode("cumulative")}
                type="button"
                aria-pressed={viewMode === "cumulative"}
              >
                查看累计内容
              </button>
              <button
                className={viewMode === "additions" ? styles.selectedMode : undefined}
                onClick={() => setViewMode("additions")}
                type="button"
                aria-pressed={viewMode === "additions"}
              >
                仅看本次新增
              </button>
            </div>
          </div>

          <article className={styles.paper} aria-label="Word 报告内容预览">
            <header className={styles.reportHeader}>
              <p>BIDRADAR-X / TENDER INTELLIGENCE</p>
              <h2>招投标信息增量报告</h2>
              <h3>{SHANGHAI_PROPERTY_DEMO_QUERY}</h3>
              <div className={styles.reportMeta}>
                <div><span>报告批次</span><strong>{selectedRun.executedAt}</strong></div>
                <div><span>执行频率</span><strong>每天 09:00</strong></div>
                <div><span>本次抓取</span><strong>{selectedRun.collectedCount} 条</strong></div>
                <div><span>过滤重复</span><strong>{selectedRun.duplicateCount} 条</strong></div>
                <div><span>本次新增</span><strong>{selectedRun.addedProjectIds.length} 条</strong></div>
                <div><span>累计推送</span><strong>{cumulativeProjectIds.size} 条</strong></div>
              </div>
              <p className={styles.previewNotice}>
                页面绿色标记仅用于演示增量识别；下载的 Word 只包含本次新增项目，不显示标记。
              </p>
            </header>

            {visibleProjects.length === 0 ? (
              <div className={styles.noAdditions}>
                <strong>本次没有新增公告</strong>
                <p>10 条抓取结果均已在此前批次推送，系统不生成重复 Word。</p>
              </div>
            ) : (
              <ol className={styles.projectSections}>
                {visibleProjects.map((project, index) => (
                  <ProjectReportSection
                    key={project.project_id}
                    project={project}
                    index={index + 1}
                    isAdded={addedProjectIds.has(project.project_id)}
                  />
                ))}
              </ol>
            )}

            <footer className={styles.paperFooter}>
              合成演示数据版本：{SHANGHAI_PROPERTY_DEMO_VERIFIED_AT} · 不代表真实公告事实
            </footer>
          </article>
        </section>
      </div>
    </main>
  );
}


function ProjectReportSection({
  project,
  index,
  isAdded,
}: {
  project: ProjectSummary;
  index: number;
  isAdded: boolean;
}) {
  const modules = useMemo(
    () => createRequirementTemplates({ ...project, modules: [] } as ProjectProfile),
    [project],
  );

  return (
    <li className={isAdded ? styles.addedProject : styles.historyProject}>
      <div className={styles.projectHeading}>
        <span className={styles.projectNumber}>{String(index).padStart(2, "0")}</span>
        <div>
          <small>{isAdded ? "NEW IN THIS RUN" : "PREVIOUSLY DELIVERED"}</small>
          <h4>{project.title}</h4>
        </div>
        <strong className={isAdded ? styles.addedBadge : styles.historyBadge}>
          {isAdded ? "本次新增" : "历史已推送"}
        </strong>
      </div>
      <dl className={styles.basicInfo}>
        <div><dt>招标人</dt><dd>{project.purchaser}</dd></div>
        <div><dt>发布时间</dt><dd>{project.published_at.slice(0, 10)}</dd></div>
        <div><dt>投标截止</dt><dd>{project.deadline ? project.deadline.slice(0, 16).replace("T", " ") : "以原公告为准"}</dd></div>
        <div><dt>信息来源</dt><dd>{project.source_name}</dd></div>
      </dl>
      <p className={styles.projectSummary}>{project.summary}</p>
      <div className={styles.sourceRow}>
        <span>合成演示数据，无外部公告链接</span>
      </div>
      <details className={styles.requirementDetails}>
        <summary>查看合成八大模块示例</summary>
        <div className={styles.moduleGrid}>
          {modules.map((module, moduleIndex) => {
            const foundLines = module.rawText
              .split("\n")
              .filter((line) => line && !line.includes("[原文未提及]"));
            return (
              <section key={module.id} className={styles.moduleCard}>
                <header>
                  <span>{moduleIndex + 1}</span>
                  <div><h5>{module.name.replace(/^模块 \d+ · /, "")}</h5><small>{module.description}</small></div>
                </header>
                <dl>
                  {foundLines.map((line) => {
                    const separator = line.indexOf("：");
                    const label = separator >= 0 ? line.slice(0, separator) : line;
                    const value = separator >= 0 ? line.slice(separator + 1) : "";
                    return <div key={label}><dt>{label}</dt><dd>{value}</dd></div>;
                  })}
                </dl>
              </section>
            );
          })}
        </div>
      </details>
    </li>
  );
}
