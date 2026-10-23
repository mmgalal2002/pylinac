# Agent Tasks: Detailed PDF Reports

Plan: [PDF_REPORT_PLAN.md](PDF_REPORT_PLAN.md).
Human decisions: [HUMAN_TASKS.md](HUMAN_TASKS.md).

The shared renderer and Picket Fence pilot are implemented. On 2026-10-13 the
human confirmed that Picket Fence custom PDF generation was tested and approved,
including the pilot design. Wider module rollout is now authorized and in progress.
Approval applies to Picket Fence only, not to unreviewed reports or variations.

## Current Scope

On 2026-10-23, the human expanded the detailed-PDF rollout to include nuclear
medicine and **every supported phantom-based QA analysis and variation** across
the package, in addition to the existing X-ray imaging, MRI, CT and mammography
scope. All nine nuclear analyzer classes are now included and still need PDF
adapters, examples and review. Calibration, machine-log and device-only reports
remain excluded. The earlier nuclear plot-data JSON task was separate; this later
authorization explicitly expands the PDF scope.

Use only the supplied local folder `E:\dcms-20261013T142612Z-1-001\dcms`.
Do not download data or install dependencies. The human explicitly declined
content checks; tests, builds, linters and screenshots remain human-owned.

## ARTBackend Integration: 2026-10-13

The human requested replacement of the existing PDF generator in the sibling
`ARTBackend` repository, assuming manual deployment of this custom pylinac.
This integration does not change this library's legacy defaults or analysis code.

- [x] Route the fourteen existing supported imaging PDF services through one
      shared publisher with `detailed=True` and full Pro-ART branding.
- [x] Reuse the backend's logo and configure the report identity, teal tables,
      blue charts, header and footer centrally. Keep analysis-specific titles.
- [x] Preserve response keys, base64 payloads, JSON results and temporary cleanup.
      Leave nuclear, machine-log, PET, ultrasound and PDF-free workflows unchanged.
- [x] Reject a legacy-only pylinac build without silently generating an old PDF.
- [x] Document manual deployment after backend requirements and the required restart.
- [x] Run seven backend-only regression checks against the custom checkout.
- [x] Run an offline synthetic Picket Fence service smoke check with `crop_mm=0`.
      Verify PDF author metadata, embedded JSON, base64 aliases and cleanup.
- [x] Record that no packages were installed and no source-library test suite,
      content checks or clinical acceptance were performed for this integration.

The default editor interpreter still imports stock pylinac. The supplied image
folder is unavailable on this machine, so real-input and visual review remain
pending. `uv`, `uvx` and `prek` are unavailable; the backend whitespace diff check
passed. The pre-existing omitted-`crop_mm` failure remains unchanged and documented.
Human deployment and acceptance tasks are in [HUMAN_TASKS.md](HUMAN_TASKS.md).

## Nuclear Plot-Ready JSON: 2026-10-23

- [x] Audit every nuclear medicine `plot()` against its `results_data()` model.
- [x] Add typed plot payloads to every nuclear analyzer result model, including
      line series, fit curves, displayed image slices and overlays; leave the
      no-plot Simple Sensitivity payload empty.
- [x] Preserve existing scalar measurements and fix Planar Uniformity's nested
      `as_json=True` output so each frame is a JSON object, not an encoded string.
- [x] Document the plot payload shape and per-frame Planar Uniformity JSON.
- [ ] Complete human review and any approved serialization checks in
      [HUMAN_TASKS.md](HUMAN_TASKS.md).

No application code, tests, builds or linters were run for this task, per the
human's instruction. Its original scope did not include PDFs; the later PDF scope
expansion is recorded below.

## Nuclear Medicine PDF Scope Expansion: 2026-10-23

- [x] Record the human's authorization to include all nuclear medicine analyses
      and every supported phantom-based QA analysis and variation in the report
      rollout, superseding the earlier nuclear exclusion.
- [x] Add all nine nuclear analyzer classes to the coverage matrix and mark their
      detailed-report work as pending.
- [ ] Implement detailed PDF adapters for every in-scope nuclear analysis while
      preserving existing legacy PDF behavior.
- [ ] Generate examples for every matching local input and supported variation;
      record missing inputs and configuration blockers.
- [ ] Complete field/artifact review and human acceptance for every new report.

Only Markdown scope and tracking were changed for this authorization. No
application code, tests, builds, linters or screenshots were run.

## Nuclear Chart Coverage Audit: 2026-10-23

- [x] Recheck the current `nuclear.py` chart creation and result payloads after
      the nuclear plot-data changes.
- [x] Record six chart-producing analyses: MaxCountRate, CenterOfRotation,
      TomographicResolution, FourBarResolution, QuadrantResolution and
      TomographicContrast.
- [x] Record the three no-chart cases: PlanarUniformity and TomographicUniformity
      produce image views only; SimpleSensitivity has no plot method and an empty
      `plot_data` payload.
- [x] Confirm the nuclear charts use line/scatter-style series; no bar,
      histogram or box chart is created in `nuclear.py`.
- [x] Update [IMAGE_PLOT_INVENTORY.md](IMAGE_PLOT_INVENTORY.md) with chart coverage,
      payload limitations and scope exclusions.
- [x] Record that this was a source-only audit; no tests or runtime serialization
      checks were performed.

## Nuclear JSON Image-Payload Removal: 2026-10-23

- [x] Remove pixel arrays, raster metadata and phantom/ROI overlay geometry from
      nuclear result JSON; retain common chart series under `plot_data.line_plots`.
- [x] Keep existing Matplotlib `plot()` image views unchanged; the JSON scope is
      chart data only.
- [x] Record the attached Matplotlib image diagnosis and Python-side improvement
      options in [IMAGE_PLOT_INVENTORY.md](IMAGE_PLOT_INVENTORY.md).
- [x] Search the repository for references to the removed image-payload models;
      no references outside `nuclear.py` were found.
- [x] Run focused offline serialization checks against the supplied COR_102 and
      COR_180 DICOMs: both expected deviations matched, JSON parsed, all three
      chart definitions/four series matched plotted Matplotlib lines, and no
      raster or overlay payload was present.

No full pytest suite, build or linter was run; the focused inline Python check
above passed. The supplied COR files are not the source for the Tomographic
Uniformity screenshot. Its matching `Jaszczak.dcm` was not found locally, so
pixel/windowing diagnosis and visual plot changes remain pending source data and
human review.

## Logo Customization: 2026-10-13

- [x] Confirm the existing `logo=` argument reaches the shared detailed renderer,
      including the direct Picket Fence and Winston-Lutz report paths.
- [x] Accept a local logo in `ReportBranding` and the `branding` mapping as well.
- [x] Keep explicit `logo=` precedence, local-file validation and existing defaults.
- [x] Document both options and `publish.logo` for paired local review examples.
- [x] Check shared-renderer editor diagnostics; no errors were reported.

No custom-logo PDFs were generated for this revision because no custom logo was
supplied. Visual review remains pending in [HUMAN_TASKS.md](HUMAN_TASKS.md).
No tests, builds, linters or screenshots were run for this revision.

## Rollout Summary

- 47 concrete imaging analyses have detailed-report adapters; the nine nuclear
      medicine analyses are newly in scope and have no detailed-report adapters yet.
- 31 imaging analyses generated standard and branded reports: 62 PDFs in total.
- 14 imaging analyses await matching input data or required clinical settings.
- 2 supplied imaging cases fail during analysis before PDF generation: ACR CT and IBA Primus.
- Calibration, machine-log and device-only workflows remain excluded from scope.
- Only the original Picket Fence pilot is human-approved. New report examples
      and all unreviewed variations still require human acceptance.

## Display Rounding: Current Steps

- [x] Configure clinical precision for errors, distances, percentages, angles
      and image coordinates. Keep counts and identifiers as whole numbers.
- [x] Apply field precision to nested arrays and table cells.
- [x] Use consistent chart-axis, histogram and tolerance-label formatting.
- [x] Normalize rounded negative zero without changing measured data.
- [x] Check representative formatting and confirm the result snapshot is unchanged.
- [x] Regenerate the standard and custom-branded local pilot PDFs.
- [x] Document the policy in the plan and public report guide.
- [x] Run scoped repository content checks for this rounding revision. All content
      checks passed; the existing `master` branch-policy gate remains blocked.
- [x] Record the human's 2026-10-13 approval of the Picket Fence pilot.

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
- [x] Audit concrete imaging classes, inherited/overridden PDF entry points,
      result models and available artifacts. Keep variation verification separate.
- [x] Add a complete class/variation coverage matrix to the plan. Mark gaps clearly; do not exclude
      modules because they lack a current PDF or JSON method.
- [x] Record the new API for analyses without `publish_pdf()` and retain old defaults.
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
- [x] Receive human approval of Picket Fence before extending the pilot design.
- [ ] If another PDF library is needed, document the trade-offs and request approval
      before adding or installing dependencies.

## All Tests And Variations

- [x] Record human authorization to proceed with the complete report plan.
- [x] Deliver a multi-image Winston-Lutz pilot with per-image and combined results.
- [x] Add an adapter for every concrete analysis class in the imaging-only scope.
- [ ] Give each variant clear charts or analysis visuals and readable artifacts.
- [ ] Handle missing values, warnings, long arrays, large image sets and custom metadata.
- [ ] Preserve file/stream behaviour, notes, logos, existing options and `open_file`.
- [ ] Finish every row in the coverage matrix before calling coverage complete.

## Per-Analysis Implementation Progress

Updated 2026-10-13. "Implemented" means the opt-in adapter is written, not that
its report has been rendered, tested or human-approved. Example generation is
recorded separately; human acceptance remains pending for every new adapter.
Inherited adapters count only when the
subclass does not override the report entry point.

| QA analysis                      | Adapter           | Generated example                                | Human acceptance |
| -------------------------------- | ----------------- | ------------------------------------------------ | ---------------- |
| PicketFence                      | Implemented       | Standard and branded                             | Approved pilot   |
| WinstonLutz2D                    | Implemented       | Standard and branded                             | Pending          |
| WinstonLutz                      | Implemented       | Standard and branded; 17 images                  | Pending          |
| WinstonLutzMultiTargetMultiField | Implemented       | Standard and branded                             | Pending          |
| Starshot                         | Implemented       | Awaiting TIFF source-to-image distance           | Pending          |
| DRGS                             | Implemented       | Standard and branded                             | Pending          |
| DRCS                             | Implemented       | Standard and branded                             | Pending          |
| DRMLC                            | Implemented       | Standard and branded                             | Pending          |
| FieldAnalysis                    | Implemented       | Standard and branded from fa.dcm                 | Pending          |
| DeviceFieldAnalysis              | Excluded by scope | Not applicable                                   | Not applicable   |
| FieldProfileAnalysis             | Implemented       | Standard and branded                             | Pending          |
| StandardImagingFC2               | Implemented       | Awaiting fc2.dcm or matching image               | Pending          |
| IMTLRad                          | Implemented       | Awaiting matching image                          | Pending          |
| DoselabRLf                       | Implemented       | Awaiting matching image                          | Pending          |
| IsoAlign                         | Implemented       | Awaiting matching image                          | Pending          |
| SNCFSQA                          | Implemented       | Awaiting matching image                          | Pending          |
| LasVegas                         | Implemented       | Standard and branded from LasVegas2.dcm          | Pending          |
| ElektaLasVegas                   | Implemented       | Standard and branded                             | Pending          |
| PTWEPIDQC                        | Implemented       | Standard and branded; analysis warnings retained | Pending          |
| IBAPrimusA                       | Implemented       | Blocked: input phantom detection fails           | Pending          |
| StandardImagingQC3               | Implemented       | Standard and branded                             | Pending          |
| StandardImagingQCkV              | Implemented       | Standard and branded                             | Pending          |
| SNCkV                            | Implemented       | Standard and branded                             | Pending          |
| SNCMV                            | Implemented       | Standard and branded                             | Pending          |
| SNCMV12510                       | Implemented       | Awaiting matching image                          | Pending          |
| LeedsTOR                         | Implemented       | Standard and branded                             | Pending          |
| LeedsTORBlue                     | Implemented       | Awaiting matching input                          | Pending          |
| DoselabMC2kV                     | Implemented       | Standard and branded                             | Pending          |
| DoselabMC2MV                     | Implemented       | Standard and branded                             | Pending          |
| ACRDigitalMammography            | Implemented       | Standard and branded; full detail views          | Pending          |
| SmallACRMammography              | Implemented       | Standard and branded from Planar Mammo.dcm       | Pending          |
| ACRCT                            | Implemented       | Blocked: CT archive has no detected HU module    | Pending          |
| ACRMRILarge                      | Implemented       | Standard and branded                             | Pending          |
| ACRMRIMedium                     | Implemented       | Awaiting matching input                          | Pending          |
| CatPhan503                       | Implemented       | Standard and branded; analysis warnings retained | Pending          |
| CatPhan504                       | Implemented       | Standard and branded                             | Pending          |
| CatPhan600                       | Implemented       | Standard and branded                             | Pending          |
| CatPhan604                       | Implemented       | Standard and branded                             | Pending          |
| CatPhan700                       | Implemented       | Awaiting matching input                          | Pending          |
| TomoCheese                       | Implemented       | Standard and branded                             | Pending          |
| CIRS062M                         | Implemented       | Awaiting matching input                          | Pending          |
| QuartDVT                         | Implemented       | Standard and branded                             | Pending          |
| HypersightQuartDVT               | Implemented       | Awaiting matching input                          | Pending          |
| GECTQA                           | Implemented       | Standard and branded; profile warning retained   | Pending          |
| GEHeliosCTDaily                  | Implemented       | Standard and branded                             | Pending          |
| DLG                              | Implemented       | Awaiting image and overlap settings              | Pending          |
| MaxCountRate                     | Pending           | Not generated                                     | Pending          |
| PlanarUniformity                 | Pending           | Not generated                                     | Pending          |
| CenterOfRotation                 | Pending           | Not generated                                     | Pending          |
| TomographicResolution            | Pending           | Not generated                                     | Pending          |
| SimpleSensitivity                | Pending           | Not generated                                     | Pending          |
| FourBarResolution                | Pending           | Not generated                                     | Pending          |
| QuadrantResolution               | Pending           | Not generated                                     | Pending          |
| TomographicUniformity            | Pending           | Not generated                                     | Pending          |
| TomographicContrast              | Pending           | Not generated                                     | Pending          |
| Dynalog                          | Excluded by scope | Not applicable                                   | Not applicable   |
| TrajectoryLog                    | Excluded by scope | Not applicable                                   | Not applicable   |
| MachineLogs                      | Excluded by scope | Not applicable                                   | Not applicable   |
| TG51Photon                       | Excluded by scope | Not applicable                                   | Not applicable   |
| TG51ElectronLegacy               | Excluded by scope | Not applicable                                   | Not applicable   |
| TG51ElectronModern               | Excluded by scope | Not applicable                                   | Not applicable   |
| TRS398Photon                     | Excluded by scope | Not applicable                                   | Not applicable   |
| TRS398Electron                   | Excluded by scope | Not applicable                                   | Not applicable   |
| QuasarLightRadScaling            | Implemented       | Awaiting matching input                          | Pending          |
| JawOrthogonality                 | Implemented       | Standard and branded                             | Pending          |

Variation requirements and known gaps are recorded in
[PDF_REPORT_PLAN.md](PDF_REPORT_PLAN.md). No new adapter is marked human-tested.

## Local Example Generation

- [x] Use the human-supplied local datasets only; do not download demo data.
- [x] Generate standard and branded PDFs for every matching analysable input.
- [x] Generate both large and small ACR mammography reports with individual ROI views.
- [x] Generate a 17-image Winston-Lutz report and multi-target examples.
- [x] Record every class, exact input and generation outcome in Markdown and JSON.
- [ ] Obtain matching inputs/settings for the awaiting-input rows above.
- [ ] Obtain an analysable ACR CT dataset/configuration and IBA Primus image/setup.
- [ ] Complete per-variation generation and human acceptance; class routing alone
      does not certify every possible analysis parameter combination.

Outputs: `E:\dcms-20261013T142612Z-1-001\detailed-reports`.
That folder contains `generation_status.md` and `generation_status.json` with
per-analysis source inputs, PDF names and error stages. Regenerate through
[scripts/generate_detailed_report_examples.py](scripts/generate_detailed_report_examples.py).

No tests, builds, linters, screenshot checks or dependency installations were run
for this rollout. The human declined content checks. Editor diagnostics and
actual local report generation are recorded without claiming clinical validation.
The checked content-check items below belong to the earlier Picket Fence pilot.

## Review And Handover

- [ ] Review field coverage and confirm no analysis data is changed or invented.
- [ ] Prepare paired legacy/detailed examples and exact commands for human checks.
- [ ] Ask before adding or running tests, builds, linters or screenshot checks;
      follow any required repository checks within the approved scope.
- [x] Document the pilot's `detailed=True` and `branding` options in RST.
- [x] Update the repository guide for the shared renderer and future adapters.
- [x] Record per-class implementation/generation status, exclusions and open blockers.

## Current Verification

The checked content-check items in this section are historical Picket Fence pilot
records, not checks run for the imaging rollout. The human declined new checks.

- [x] Render the default clinical pilot from the existing local documentation image.
- [x] Render a branding example with custom title, fonts, colours, header and footer.
- [x] Check editor diagnostics for the new renderer and Picket Fence changes.
- [ ] Check the rendered text with a PDF parser; none is currently installed.
- [x] Run the installed, cached `prek` hooks and accept formatting fixes. Python
      syntax, Ruff, whitespace, line endings and RST content checks passed.
- [ ] Clear the branch-policy gate on an approved working branch. The current
      `master` branch is blocked by `no-commit-to-branch`; no branch was changed.
- [ ] Build the documentation when Nox and Sphinx are available. They are not
      installed in the current environment. Do not install without human approval.
- [ ] Complete regression checks and clinical acceptance with the human.

The existing `save_histogram` type-annotation diagnostic is unchanged. No regression
test suite, documentation build or screenshot review has been run by the agent.

## Recent Test Commit Audit: 2026-10-23

- [x] Review the latest six reachable commits and record the commit subjects and
      test-file deltas in [RECENT_TEST_COMMITS.md](RECENT_TEST_COMMITS.md).
- [x] Cross-check updated Plotly test expectations against the MTF, CatPhan,
      planar-imaging and Winston-Lutz implementations.
- [x] Normalize the `unittest` import spacing in `tests_basic/test_planar_imaging.py`.
- [x] Record that no test suite was executed; human execution and acceptance remain
      pending in [HUMAN_TASKS.md](HUMAN_TASKS.md).
