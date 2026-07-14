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
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton/);
});


test("server-renders the collected projects page and reserved reports page", async () => {
  const projects = await (await render("/projects")).text();
  const reports = await (await render("/reports")).text();
  assert.match(projects, /收集到的项目/);
  assert.match(projects, /下载成 Word/);
  assert.match(reports, /报告、增量与长期记忆/);
});
