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
    ? `/projects?demo=${encodeURIComponent(SHANGHAI_PROPERTY_DEMO_ID)}`
    : `/projects?run=${encodeURIComponent(runId)}&task=${encodeURIComponent(taskId)}`;

  return (
    <div className="requirements-page requirements-workbench-page">
      <header className="requirements-header">
        <Link className="outline-action" href={backHref}>返回项目列表</Link>
        <div>
          <p className="section-kicker">LLM-PARSED REQUIREMENTS</p>
          <h1>{project?.title ?? "招标项目具体信息"}</h1>
          {project && <p>{project.project_code || "项目编号未披露"} · {project.purchaser} · {project.source_name}</p>}
        </div>
        <span className="objective-badge">{isDemo ? "合成演示 · 不代表真实公告" : "8 个固定模块 · 条款动态识别"}</span>
      </header>

      <main className="requirements-main requirements-workbench-main">
        {loading && <div className="status-panel" role="status">正在读取项目内容…</div>}
        {error && <div className="status-panel error-panel" role="alert">{error}</div>}
        {project && <RequirementsWorkbench key={project.project_id} project={project} />}
      </main>
    </div>
  );
}


function RequirementsWorkbench({ project }: { project: ProjectProfile }) {
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
            <p className="section-kicker">MOCK LLM ANALYZER</p>
            <h2 id="parser-title">按模块查看原文条款</h2>
            <p>全文识别结果始终同时作用于下方八个模块；选择模块只切换文本框中的原文片段，每行对应一个字段。</p>
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
          <span>可直接编辑当前模块原文；保存后会重新计算整份文件的识别结果。</span>
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
