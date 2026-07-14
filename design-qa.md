# Design QA

## Evidence

- Source visual truth: `D:\wxdownloadad\xwechat_files\wxid_mz4u8px5jewv22_927b\temp\RWTemp\2026-07\bcdf306feb389ced735c4860b610cf56.jpg`
- Collected-projects implementation: `D:\超巨变\artifacts\collected-projects-desktop.jpg`
- Requirements overview: `D:\超巨变\artifacts\project-requirements-overview.jpg`
- Requirement detail: `D:\超巨变\artifacts\project-requirement-detail.jpg`
- Comparison viewport: 1600 × 900 for the collected-projects page
- Responsive viewport: 390 × 844
- Compared state: three persisted mock projects loaded after completing the homepage extraction modal

## Full-view comparison

The source sketch and the rendered collected-projects page were opened in the same comparison input. The implementation preserves the sketch's defining structure: a back control at top-left, the “收集到的项目” heading beside it, vertically ordered numbered rows, publish time / source URL / project name in each row, a far-right “具体信息” action, and a bottom-left disabled Word-download control.

The source is a low-fidelity paper wireframe and does not define exact fonts, colors, borders, responsive behavior, or the two deeper requirement layers. The implementation therefore carries forward the existing site's ivory, black, square-border visual language without changing the source information hierarchy.

No additional focused crop was required for the source comparison because the wireframe contains only page-level boxes and labels. Dense requirement tables were inspected separately in the implementation: the technical matrix exposes all five required columns and nine populated rows.

## Required fidelity surfaces

- Fonts and typography: Chinese system type remains readable at desktop and mobile sizes; index numbers use a monospaced face to mirror the numbered boxes in the sketch. No clipped DOM text or forced single-line title overflow was measured.
- Spacing and layout rhythm: desktop rows use a stable number / metadata / action grid; the action is measured inside the 1600 px viewport at x=1358–1459. Mobile rows collapse into a single-column reading order.
- Colors and tokens: the existing `--paper`, `--surface`, `--ink`, and border tokens are reused consistently; disabled Word state is visibly muted.
- Image quality and asset fidelity: the source contains no product imagery, logos, or icons to reproduce. No placeholder imagery, custom SVG, or CSS illustration was introduced.
- Copy and content: labels follow the supplied Chinese specification. Requirement pages explicitly state that they only present objective purchaser clauses.

## Primary interactions tested

1. Entered “请每天关注最近1个月安徽省的服务器招标信息”.
2. Opened the extraction modal and verified 服务器采购 / 安徽省 / 最近1个月 / 每日.
3. Clicked modal “下一步”; the Python workflow completed and the collected-projects page loaded three rows from SQLite.
4. Opened the first project's “具体信息”; all eight requirement modules rendered.
5. Opened “技术与服务要求”; the table rendered the required five headers and nine realistic mock rows.
6. Checked the detail page for prohibited analysis fields; no winning probability, profit estimate, risk level, competitor analysis, or bidding recommendation appeared.
7. Followed 返回要求总览 → 返回项目列表 → 返回; the homepage modal reopened with its four edited values retained.
8. Confirmed “下载成 Word” is disabled during this simulation phase.

## Responsive and runtime evidence

- At 390 × 844, `documentElement.scrollWidth === clientWidth` (375 px) and all three project actions remain inside the measured content bounds.
- At 1440 × 1000, the technical detail page has no root horizontal overflow; its five-column table stays inside a dedicated scroll container.
- Browser console warnings/errors during the tested flow: none.
- Frontend production build: passed.
- Frontend rendered-page tests: 2 passed.
- Python workflow/API tests: 2 passed.

## Findings and comparison history

- Earlier implementation issue: the first backend data path attempted to place SQLite below a non-ASCII Windows directory, which the bundled Python runtime could not open. Fix: the simulation database and reports now use an ASCII-safe local runtime directory with an environment override. Post-fix evidence: workflow/API tests pass and browser flow loads three persisted projects with eight modules each.
- Earlier implementation issue: the combined launcher used a Windows child-process mode that raised `spawn EINVAL`. Fix: the frontend is launched through the Windows command processor while FastAPI runs from the project virtual environment. Post-fix evidence: one command starts both services and the final local page responds.
- No actionable P0, P1, or P2 visual, behavior, accessibility, or responsive issues remain.

final result: passed
