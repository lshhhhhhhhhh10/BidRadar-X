import assert from "node:assert/strict";
import test from "node:test";


async function render(path = "/") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request(`http://localhost${path}`, { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}


test("server-renders the local intelligence workbench", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /招投标情报工作台/);
  assert.match(html, /北京时间/);
  assert.match(html, /请输入您的投标对象/);
  assert.match(html, /开始检索/);
  assert.match(html, /智能检索/);
  assert.match(html, /aria-label="查看说明"/);
  assert.match(html, /为你推荐/);
  assert.match(html, /换一批/);
  assert.match(html, /aria-label="检索历史"/);
  assert.match(html, /aria-label="定时推送与收藏项目"/);
  assert.match(html, /定时推送/);
  assert.match(html, /收藏项目/);
  assert.match(html, /信息来源/);
  assert.match(html, /5<!-- --> 类/);
  assert.match(html, /class="source-pill"/);
  assert.match(html, /aria-expanded="false"/);
  assert.doesNotMatch(html, /id="source-catalog-panel"/);
  assert.doesNotMatch(html, /请确认识别结果|LOCAL RULE EXTRACTION/);
  assert.doesNotMatch(html, />LIBRARY</);
  assert.doesNotMatch(html, /workspace-logo|>BR<|PROJECT PREVIEW|BIDRADAR X/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton/);
});


test("server-renders user-funded interface management", async () => {
  const response = await render("/interfaces");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /接口管理/);
  assert.match(html, /费用归当前使用者/);
  assert.match(html, /每日预算上限/);
  assert.match(html, /后端强制拦截已开启/);
  assert.match(html, /天眼查 · 招投标搜索/);
  assert.doesNotMatch(html, /SAM\.gov Opportunities/);
});


test("server-renders the merged project-report shell", async () => {
  const reports = await (await render("/reports")).text();
  assert.match(reports, /项目报告/);
  assert.match(reports, /Word 文档/);
  assert.match(reports, /查询记录/);
  assert.match(reports, /收录项目/);
  assert.match(reports, /项目重点/);
  assert.doesNotMatch(reports, /AUTOMATED PROJECT REPORT|PROJECT BRIEF|SUMMARY DOCUMENT/);
  assert.doesNotMatch(reports, /具体功能将在第三阶段确定/);
});


test("server-renders URL context into dynamic project navigation", async () => {
  const project = await (
    await render("/projects/project-real?run=run-real&task=task-real")
  ).text();
  const modulePage = await (
    await render("/projects/project-real/module-real?run=run-real&task=task-real")
  ).text();

  assert.match(project, /reports\?run=run-real/);
  assert.match(
    modulePage,
    /projects\/project-real\?run=run-real(?:&|&amp;)task=task-real/,
  );
});
