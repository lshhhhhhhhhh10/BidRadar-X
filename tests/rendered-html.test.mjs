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
  assert.match(html, /对话框，请输入您的投标对象/);
  assert.match(html, /下一步/);
  assert.match(html, /热门推荐/);
  assert.match(html, /换一批/);
  assert.match(html, /剑鱼（未登录）/);
  assert.match(html, /添加信息来源网站/);
  assert.match(html, /href="https:\/\/www\.jianyu360\.com\/"/);
  assert.match(html, /target="_blank"/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton/);
});


test("server-renders the real project-result and report-history shells", async () => {
  const projects = await (await render("/projects")).text();
  const reports = await (await render("/reports")).text();
  assert.match(projects, /本次运行的项目/);
  assert.match(projects, /下载本次 Word|Word 暂不可下载/);
  assert.match(reports, /真实运行与报告历史/);
  assert.match(reports, /来自本地 SQLite/);
  assert.doesNotMatch(reports, /具体功能将在第三阶段确定/);
});


test("server-renders URL context into dynamic project navigation", async () => {
  const project = await (
    await render("/projects/project-real?run=run-real&task=task-real")
  ).text();
  const modulePage = await (
    await render("/projects/project-real/module-real?run=run-real&task=task-real")
  ).text();

  assert.match(project, /projects\?run=run-real(?:&|&amp;)task=task-real/);
  assert.match(
    modulePage,
    /projects\/project-real\?run=run-real(?:&|&amp;)task=task-real/,
  );
});
