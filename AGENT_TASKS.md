# Agent Tasks: Detailed PDF Reports

Plan: [PDF_REPORT_PLAN.md](PDF_REPORT_PLAN.md).
Human decisions: [HUMAN_TASKS.md](HUMAN_TASKS.md).

Only the planning step is complete. Python implementation has not started.

## Plan And Coverage

- [x] Create the Markdown plan and separate agent and human checklists.
- [ ] Audit report entry points, result models, artifacts and every analysis variation.
- [ ] Add a complete coverage matrix to the plan. Mark gaps clearly; do not exclude
  modules because they lack a current PDF or JSON method.
- [ ] Record the new API for modules without `publish_pdf()` and preserve old APIs.
- [ ] Record the page design and measurable acceptance rules from the plan.

## Shared Renderer And Pilot

- [ ] Build an isolated renderer using ReportLab layout tools first. Keep the old
  canvas, analysis calculations, result schemas and plotting functions unchanged.
- [ ] Build reusable sections, paged tables, nested-data rendering, artifact pages,
  chart placement, warnings, bookmarks and local asset handling.
- [ ] Capture one JSON snapshot and include every field in the report. Attach the
  same JSON and keep its original numeric precision.
- [ ] Add the keyword-only `detailed=False` option without moving existing arguments.
- [ ] Deliver Picket Fence examples with full leaf/picket details and a large case.
- [ ] Wait for human review before extending the pilot design to all modules.
- [ ] If another PDF library is needed, document the trade-offs and request approval
  before adding or installing dependencies.

## All Tests And Variations

- [ ] Deliver a multi-image Winston-Lutz pilot with per-image and combined results.
- [ ] Add a small adapter for every remaining analysis family and variation.
- [ ] Give each variant clear charts or analysis visuals and readable artifacts.
- [ ] Handle missing values, warnings, long arrays, large image sets and custom metadata.
- [ ] Preserve file/stream behaviour, notes, logos, existing options and `open_file`.
- [ ] Finish every row in the coverage matrix before calling coverage complete.

## Review And Handover

- [ ] Review field coverage and confirm no analysis data is changed or invented.
- [ ] Prepare paired legacy/detailed examples and exact commands for human checks.
- [ ] Ask before adding or running tests, builds, linters or screenshot checks;
  follow any required repository checks within the approved scope.
- [ ] Document `detailed=True`, dependencies, supported cases and limitations in RST.
- [ ] Update the repository guide if a new reporting package is introduced.
- [ ] Record open issues and implementation status. Leave human acceptance unchecked.