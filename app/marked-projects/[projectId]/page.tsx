"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import {
  INITIAL_MARKED_PROJECTS,
  markedProjectStatus,
} from "@/lib/marked-projects";


export default function MarkedProjectUpdatePage() {
  const params = useParams<{ projectId: string }>();
  const project = INITIAL_MARKED_PROJECTS.find((item) => item.id === params.projectId);

  if (!project) {
    return (
      <main className="marked-update-page">
        <Link className="outline-action" href="/">返回首页</Link>
        <div className="marked-update-missing">
          <p className="section-kicker">LAST UPDATE</p>
          <h1>没有找到该标记项目</h1>
        </div>
      </main>
    );
  }

  return (
    <main className="marked-update-page">
      <header className="marked-update-header">
        <Link className="outline-action" href="/">返回首页</Link>
        <div>
          <p className="section-kicker">LAST UPDATED PROJECT</p>
          <h1>最后一次更新</h1>
          <p>{project.title}</p>
        </div>
        <span className={`marked-update-badge${project.hasUpdates ? " is-new" : ""}`}>
          {markedProjectStatus(project)}
        </span>
      </header>

      <section className="marked-update-content">
        <aside className="marked-update-overview">
          <p className="section-kicker">PROJECT SNAPSHOT</p>
          <h2>本次增量</h2>
          <strong>{project.newItemCount}</strong>
          <span>条新增招标内容</span>
          <div>
            <p><span>项目区域</span><b>{project.region}</b></p>
            <p><span>执行频率</span><b>{project.frequency}</b></p>
            <p><span>历史去重</span><b>{project.filteredDuplicateCount} 条</b></p>
          </div>
        </aside>
        <article className="marked-update-summary">
          <p className="section-kicker">UPDATE SUMMARY</p>
          <h2>{project.hasUpdates ? "发现新的招标内容" : "本次没有新增内容"}</h2>
          <p>{project.summary}</p>
          <dl>
            <div><dt>项目区域</dt><dd>{project.region}</dd></div>
            <div><dt>更新时间</dt><dd>{project.lastUpdatedAt}</dd></div>
            <div><dt>更新频率</dt><dd>{project.frequency}</dd></div>
            <div><dt>本次新增</dt><dd>{project.newItemCount} 条</dd></div>
            <div><dt>过滤重复</dt><dd>{project.filteredDuplicateCount} 条</dd></div>
          </dl>
          {project.reportHref && (
            <Link className="solid-action" href={project.reportHref}>查看本次 Word 报告</Link>
          )}
        </article>
      </section>
    </main>
  );
}
