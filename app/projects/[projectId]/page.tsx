"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import {
  createRequirementTemplates,
  parseMockRequirements,
  type MockRequirementTemplate,
} from "@/lib/mock-requirements-parser";
import { getProject, getRunForTask, type ProjectProfile } from "@/lib/tender-api";
import {
  SHANGHAI_PROPERTY_DEMO_ID,
  SHANGHAI_PROPERTY_DEMO_PROJECTS,
} from "@/lib/demo-tenders";
import { InfoTip } from "@/app/components/InfoTip";


export default function ProjectRequirementsPage() {
  const params = useParams<{ projectId: string }>();
  const searchParams = useSearchParams();
  const projectId = params.projectId ?? "";
  const runId = searchParams.get("run") ?? "";
  const taskId = searchParams.get("task") ?? "";
  const demoId = searchParams.get("demo") ?? "";
  const isDemo = demoId === SHANGHAI_PROPERTY_DEMO_ID;
  const [project, setProject] = useState<ProjectProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      await Promise.resolve();
      if (!cancelled) {
        setLoading(true);
        setError("");
        setProject(null);
      }

      if (isDemo) {
        const summary = SHANGHAI_PROPERTY_DEMO_PROJECTS.find((item) => item.project_id === projectId);
        if (!cancelled) {
          if (summary) setProject({ ...summary, modules: [] });
          else setError("没有找到这条演示项目，请返回项目列表重新选择。");
          setLoading(false);
        }
        return;
      }

      if (!runId || !taskId || !projectId) {
        if (!cancelled) {
          setError("项目地址缺少 run_id、task_id 或 project_id，请返回列表重新选择。");
          setLoading(false);
        }
        return;
      }

      try {
        const [, result] = await Promise.all([
          getRunForTask(runId, taskId),
          getProject(runId, projectId),
        ]);
        if (!cancelled) setProject(result);
      } catch (reason) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "读取项目失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => { cancelled = true; };
  }, [isDemo, projectId, runId, taskId]);

  const backHref = isDemo
    ? "/reports/demo-shanghai-property"
    : `/reports?run=${encodeURIComponent(runId)}`;

  return (
    <div className="requirements-page requirements-workbench-page">
      <header className="requirements-header">
        <Link className="outline-action" href={backHref}>返回项目报告</Link>
        <div>
          <h1>{project?.title ?? "招标项目具体信息"}</h1>
          {project && <p>{project.project_code || "项目编号未披露"} · {project.purchaser} · {project.source_name}</p>}
        </div>
        <span className="objective-badge">{isDemo ? "合成演示" : "结构化详情"}</span>
      </header>

      <main className="requirements-main requirements-workbench-main">
        {loading && <div className="status-panel" role="status">正在读取项目内容…</div>}
        {error && <div className="status-panel error-panel" role="alert">{error}</div>}
        {project && <RequirementsWorkbench key={project.project_id} project={project} demo={isDemo} />}
      </main>
    </div>
  );
}


function RequirementsWorkbench({ project, demo }: { project: ProjectProfile; demo: boolean }) {
  return demo ? <DemoRequirements project={project} /> : <VerifiedRequirements project={project} />;
}


function DemoRequirements({ project }: { project: ProjectProfile }) {
  const templates = useMemo(() => createRequirementTemplates(project), [project]);
  const [selectedTemplateId, setSelectedTemplateId] = useState(templates[0]?.id ?? "");
  const [draftText, setDraftText] = useState(templates[0]?.rawText ?? "");
  const [moduleSourceTexts, setModuleSourceTexts] = useState<Record<string, string>>(() =>
    Object.fromEntries(templates.map((template) => [template.id, template.rawText])),
  );
  const analyzedText = useMemo(
    () => templates.map((template) => moduleSourceTexts[template.id] ?? template.rawText).join("\n"),
    [moduleSourceTexts, templates],
  );
  const parsedModules = useMemo(() => parseMockRequirements(analyzedText), [analyzedText]);
  const foundTotal = parsedModules.reduce((total, module) => total + module.foundCount, 0);
  const itemTotal = parsedModules.reduce((total, module) => total + module.items.length, 0);

  function selectTemplate(template: MockRequirementTemplate) {
    setSelectedTemplateId(template.id);
    setDraftText(moduleSourceTexts[template.id] ?? template.rawText);
  }

  function reparseSelectedModule() {
    setModuleSourceTexts((current) => ({
      ...current,
      [selectedTemplateId]: draftText,
    }));
  }

  return (
    <>
      <section className="project-objective-summary requirements-project-summary">
        <span>项目摘要</span>
        <p>{project.summary}</p>
        <dl>
          <div><dt>发布时间</dt><dd>{project.published_at.slice(0, 10) || "未披露"}</dd></div>
          <div><dt>投标截止</dt><dd>{project.deadline?.replace("T", " ").slice(0, 16) || "未披露"}</dd></div>
          <div><dt>当前识别</dt><dd>{foundTotal} / {itemTotal} 项</dd></div>
        </dl>
      </section>

      <section className="llm-parser-panel" aria-labelledby="parser-title">
        <div className="llm-parser-heading">
          <div>
            <span className="title-with-info"><h2 id="parser-title">按模块查看原文条款</h2><InfoTip text="系统按八个常用投标模块整理原文证据；选择模块只切换当前查看的原文片段。" /></span>
          </div>
          <span className="parser-score">已识别 {foundTotal} / {itemTotal}</span>
        </div>

        <div className="template-switcher" role="group" aria-label="选择项目原文模板">
          {templates.map((template) => (
            <button
              className={template.id === selectedTemplateId ? "is-active" : ""}
              type="button"
              key={template.id}
              onClick={() => selectTemplate(template)}
            >
              <strong>{template.name}</strong>
              <span>{template.description}</span>
            </button>
          ))}
        </div>

        <label className="raw-text-editor">
          <span>当前模块原文逐项对照</span>
          <textarea value={draftText} onChange={(event) => setDraftText(event.target.value)} />
        </label>
        <div className="parser-actions">
          <button type="button" onClick={reparseSelectedModule}>更新此模块并重新解析全文</button>
        </div>
      </section>

      <section className="requirement-module-stack" aria-label="八大招标需求模块">
        {parsedModules.map((module, moduleIndex) => (
          <article className="parsed-module" key={module.id}>
            <header className="parsed-module-header">
              <span className="parsed-module-index">{String(moduleIndex + 1).padStart(2, "0")}</span>
              <div>
                <p>{module.englishTitle}</p>
                <h2>{module.title}</h2>
              </div>
              <strong>{module.foundCount} / {module.items.length} 已提取</strong>
            </header>
            <div className="parsed-requirement-list">
              {module.items.map((item) => (
                <div className={`parsed-requirement-item ${item.found ? "is-found" : "is-missing"}`} key={item.label}>
                  <div className="parsed-item-label">
                    <span>{item.found ? "已识别" : "未提及"}</span>
                    <h3>{item.label}</h3>
                  </div>
                  {item.found ? (
                    <div className="parsed-item-value">
                      <p>{item.value}</p>
                      <small>原文证据：{item.evidence}</small>
                    </div>
                  ) : (
                    <p className="missing-clause">[未提及 / No Clause Found]</p>
                  )}
                </div>
              ))}
            </div>
          </article>
        ))}
      </section>
    </>
  );
}


function VerifiedRequirements({ project }: { project: ProjectProfile }) {
  return (
    <>
      <section className="project-objective-summary requirements-project-summary">
        <span>项目摘要</span>
        <p>{project.summary || "公告没有提供可核验的摘要。"}</p>
        <dl>
          <div><dt>发布时间</dt><dd>{project.published_at.slice(0, 10) || "未披露"}</dd></div>
          <div><dt>投标截止</dt><dd>{project.deadline?.replace("T", " ").slice(0, 16) || "未披露"}</dd></div>
          <div><dt>证据数量</dt><dd>{project.evidence_count} 条</dd></div>
        </dl>
      </section>
      <section className="verified-requirements" aria-labelledby="verified-requirements-title">
        <header className="title-with-info">
          <h2 id="verified-requirements-title">已核验条款</h2>
          <InfoTip text="这里只展示来源公告或已归档招标文件中具有字段级证据的条款；没有证据时不会使用演示内容补齐。" />
        </header>
        {project.modules.length ? (
          <div className="verified-module-list">
            {project.modules.map((module, index) => (
              <article className="verified-module-card" key={module.id}>
                <header><span>{String(index + 1).padStart(2, "0")}</span><div><h3>{module.title}</h3>{module.summary && <p>{module.summary}</p>}</div></header>
                {module.facts.length > 0 && <dl>{module.facts.map((fact) => <div key={fact.label}><dt>{fact.label}</dt><dd>{fact.value}</dd><small>{fact.source}</small></div>)}</dl>}
                {module.tables.map((table) => (
                  <div className="verified-table" key={table.title}><h4>{table.title}</h4><div><table><thead><tr>{table.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{table.rows.map((row, rowIndex) => <tr key={`${table.title}-${rowIndex}`}>{row.map((cell, cellIndex) => <td key={`${rowIndex}-${cellIndex}`}>{cell || "未披露"}</td>)}</tr>)}</tbody></table></div></div>
                ))}
              </article>
            ))}
          </div>
        ) : <div className="verified-requirements-empty">当前公告没有可核验的结构化条款。请以原公告和已下载招标文件为准。</div>}
      </section>
    </>
  );
}
