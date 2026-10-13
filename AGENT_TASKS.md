# Agent Tasks: Detailed PDF Reports

Plan: [PDF_REPORT_PLAN.md](PDF_REPORT_PLAN.md).
Human decisions: [HUMAN_TASKS.md](HUMAN_TASKS.md).

The shared renderer and Picket Fence pilot are implemented. The pilot is being
revised for medical readers and full branding. Wider module rollout is pending.

## Clinician Wording And Full Branding: Current Steps

- [x] Record the new requirements in the plan for all current and future reports.
- [x] Replace raw JSON paths and technical table labels in the shared renderer.
- [x] Add plain medical wording for every Picket Fence field and nested coordinate.
- [x] Use clear leaf and picket labels without changing the attached measurements.
- [x] Add full brand controls for fonts, colours, charts, tables, titles, headers
  and footers, alongside the existing logo option.
- [x] Regenerate the local pilot and record what was checked.
- [x] Add this requirement to the repository guide for future report adapters.
- [x] Prepare human wording and brand-review tasks. Do not complete human acceptance.

## Plan And Coverage

- [x] Create the Markdown plan and separate agent and human checklists.
- [ ] Audit report entry points, result models, artifacts and every analysis variation.
- [ ] Add a complete coverage matrix to the plan. Mark gaps clearly; do not exclude
  modules because they lack a current PDF or JSON method.
- [ ] Record the new API for modules without `publish_pdf()` and preserve old APIs.
- [ ] Record the page design and measurable acceptance rules from the plan.

## Shared Renderer And Pilot

- [x] Build an isolated renderer using ReportLab layout tools first. Keep the old
  canvas, analysis calculations, result schemas and plotting functions unchanged.
- [x] Build reusable sections, paged tables, nested-data rendering, artifact pages,
  chart placement, warnings, bookmarks and local asset handling.
- [x] Capture one JSON snapshot and include every field in the report. Attach the
  same JSON and keep its original numeric precision.
- [x] Add the keyword-only `detailed=False` option without moving existing arguments.
- [x] Deliver local Picket Fence examples with medical wording and custom branding.
- [ ] Deliver approved large and additional-variation Picket Fence examples.
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
- [x] Document the pilot's `detailed=True` and `branding` options in RST.
- [x] Update the repository guide for the shared renderer and future adapters.
- [ ] Record open issues and implementation status. Leave human acceptance unchecked.

## Current Verification

- [x] Render the default clinical pilot from the existing local documentation image.
- [x] Render a branding example with custom title, fonts, colours, header and footer.
- [x] Check editor diagnostics for the new renderer and Picket Fence changes.
- [ ] Check the rendered text with a PDF parser; none is currently installed.
- [ ] Complete repository formatting and documentation build gates when approved
  tools are available. Do not install packages without human approval.
- [ ] Complete regression checks and clinical acceptance with the human.

The existing `save_histogram` type-annotation diagnostic is unchanged. No regression
test suite, documentation build or screenshot review has been run by the agent.
