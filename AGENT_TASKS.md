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
scope. All nine nuclear analyzer classes are included. Review PDFs now exist for
eight of them; SimpleSensitivity example generation is blocked on source activity.
All nine public PDF adapters are written; execution and human acceptance remain
pending. Calibration, machine-log and
device-only reports remain excluded. The earlier nuclear plot-data JSON task was
separate; this later authorization explicitly expands the PDF scope.

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
- [x] Implement detailed PDF adapters for every in-scope nuclear analysis while
      preserving existing legacy PDF behavior.
- [ ] Generate examples for every matching local input and supported variation;
      record missing inputs and configuration blockers.
- [ ] Complete field/artifact review and human acceptance for every new report.

Only Markdown scope and tracking were changed for this authorization. No
application code, tests, builds, linters or screenshots were run.

## Nuclear publish_pdf APIs: 2026-10-23

The human subsequently authorized public PDF methods for all nine nuclear
analyzers. This supersedes the no-public-API restriction of the earlier example
generation pass, not the prohibition on changing analysis results or plotting.
Use the existing shared renderer, clinical wording, full branding, local logos,
notes, metadata, output streams and the complete-precision JSON attachment.
As with DLG, these new-only APIs default to `detailed=True` and reject
`detailed=False` because no legacy nuclear PDF layout exists.

- [x] MaxCountRate: count-rate chart and peak-count acquisition image.
- [x] PlanarUniformity: every frame's measurements and existing FOV image overlays.
- [x] CenterOfRotation: reference acquisition image, position fit and residual charts.
- [x] TomographicResolution: profile reference image and all three Gaussian fits.
- [x] SimpleSensitivity: measurements, phantom and optional background images;
      require a finite positive activity and nuclide half-life before publishing.
- [x] FourBarResolution: sampled phantom image, both profile fits and resolution data.
- [x] QuadrantResolution: phantom ROI image, MTF and FWHM charts.
- [x] TomographicUniformity: composite image, all FOV measurements and accurate
      exclusive-end frame-range wording.
- [x] TomographicContrast: sphere/reference images, all sphere results and contrast chart.
- [x] Document the common API and leave runtime/visual/clinical checks human-owned.

Static verification: Pylance reports no Python syntax errors and no diagnostics
in the added methods. Existing tuple-return annotation diagnostics in older
plotting/helpers remain unchanged. No API execution, PDF regeneration, tests,
builds, linters, screenshots or dependency installations were performed for this
implementation. Analysis calculations, result schemas and plotting functions are
unchanged; the new methods capture existing views through the shared renderer.

The 22 earlier example PDFs were generated directly, before these APIs existed;
they are not evidence that the new methods have been executed or accepted.

## PDF-Only Nuclear Example Generation: 2026-10-23

The human authorized PDF creation and incremental Markdown tracking after the
scope update. Use the existing shared renderer directly; do not change analysis
code, result JSON, plotting methods or public PDF APIs for this generation pass.
Keep adapter implementation status separate from generated example status.
Generate each analysis from matching supplied local data and record its exact
input and settings. Missing acquisition settings must not be invented.

- [x] MaxCountRate: four PDFs generated from `Nuclear/MaxCountRate.dcm` (24 frames)
      and `Nuclear/MCR.dcm` (30 frames). Both use `frame_duration=1.0` seconds,
      verified from nested DICOM Actual Frame Duration (1000 ms). Output stems:
      `MaxCountRate` and `MaxCountRate_MCR`, each with `_detailed.pdf` and
      `_branded.pdf`. The first file emits a pre-existing DICOM UID-format warning;
      human clinical and visual review remain pending.
- [x] PlanarUniformity: four PDFs generated from
      `Nuclear/Uniformity/UNIFORMIDAD_1_Ok.dcm` (one frame) and
      `Nuclear/Uniformity/Point_Source.dcm` (two frames). Explicit library defaults:
      `ufov_ratio=0.95`, `cfov_ratio=0.75`, `window_size=5`, `threshold=0.75`.
      Output stems: `PlanarUniformity` and `PlanarUniformity_PointSource`.
      Analysis emits `All-NaN slice encountered` warnings; human measurement and
      image/legend review are required. No analysis or plotting change was made.
- [x] CenterOfRotation: four PDFs generated from `Nuclear/COR/COR_102.dcm` and
      `Nuclear/COR/COR_180.dcm` (32 frames each), using `analyze()` and the DICOM
      acquisition geometry/pixel scale. Output stems: `CenterOfRotation` and
      `CenterOfRotation_COR180`; both include the fitted-position chart and two
      residual charts. Human review remains pending.
- [x] TomographicResolution: two PDFs generated from
      `Nuclear/TomoResolution.dcm` (64 images), using `analyze()` with DICOM
      pixel spacing and slice-spacing magnitude of `8.25999928` mm. Output stem:
      `TomographicResolution`; all three image-axis profiles and Gaussian fits
      are included. Human review remains pending.
- [x] SimpleSensitivity: blocker recorded; no PDF generated. The supplied
      `Nuclear/sensitivity/PetriDish.dcm`, `Syringe 1cc.dcm` and `Background.dcm`
      identify the nuclide as `Yodo 131` (iodine-131) but each records
      `RadionuclideTotalDose=0`. A confirmed nonzero source activity in MBq and
      its measurement/acquisition reference are required; no activity is invented.
- [x] FourBarResolution: two PDFs generated from
      `Nuclear/PixelSz&Resolution/FourBar.dcm` using explicit library defaults
      `separation_mm=100`, `roi_width_mm=10` and DICOM pixel spacing
      `1.032499908` mm. Output stem: `FourBarResolution`. Reports explicitly
      require human confirmation of physical phantom geometry before clinical use.
- [x] QuadrantResolution: two PDFs generated from
      `Nuclear/PixelSz&Resolution/QuadrantBar.dcm` using the documented/reference
      configuration: `bar_widths=(4.23, 3.18, 2.54, 2.12)` mm,
      `roi_diameter_mm=70`, `distance_from_center_mm=130`. Output stem:
      `QuadrantResolution`. Reports identify the reference configuration and
      require human confirmation of actual bar widths, order and ROI geometry.
- [x] TomographicUniformity: two PDFs generated from `Nuclear/Jaszack.dcm`
      (45 source images; supplied filename spelling retained). Explicit defaults:
      `first_frame=0`, `last_frame=-1`, `ufov_ratio=0.8`, `cfov_ratio=0.75`,
      `center_ratio=0.4`, `threshold=0.75`, `window_size=5`. The unchanged analyzer
      averages source images 1-44; stored end marker 45 is excluded and labeled
      accordingly in the PDF. Output stem: `TomographicUniformity`. Analysis emits
      `All-NaN slice encountered`; frame-range, measurements and image/legend
      acceptance remain human-owned.
- [x] TomographicContrast: two PDFs generated from `Nuclear/Jaszack.dcm`
      (45 source images). Explicit library defaults:
      `sphere_diameters_mm=(38, 31.8, 25.4, 19.1, 15.9, 12.7)`,
      `sphere_angles=(-10, -70, -130, -190, 110, 50)`, `ufov_ratio=0.8`,
      `search_window_px=5`, `search_slices=3`. Output stem: `TomographicContrast`.
      Reports include all six sphere results, both image views and the contrast
      chart; actual geometry and clinical acceptance require human confirmation.

PDFs go to `E:\dcms-20261013T142612Z-1-001\detailed-reports`. Existing imaging PDFs
and JSON generation records must remain unchanged. No tests, builds, linters,
screenshots or clinical acceptance are included in this generation task.

Outcome: 22 new standard/branded PDFs for eight nuclear analyses from eleven
input/analysis configurations. SimpleSensitivity has no PDF because source
activity is missing. Only PDFs and Markdown tracking were written; source code,
public APIs, image plotting, result schemas and historical JSON files are unchanged.
Detailed per-analysis inputs, settings, warnings and filenames are recorded in
the output folder's `generation_status.md`; do not use the older JSON record or
the unmodified imaging example script as nuclear generation status.

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

- 47 concrete imaging analyses and all nine nuclear medicine analyses have
      detailed-report adapters: 56 analyses in total. Nuclear API execution and
      human acceptance remain pending.
- 31 imaging analyses generated standard and branded reports: 62 PDFs in total.
- 8 nuclear analyses generated 22 standard/branded PDFs directly through the
  existing shared renderer; SimpleSensitivity awaits confirmed source activity.
- 84 review PDFs now exist across imaging and nuclear medicine. Generation does
  not mean clinical or visual acceptance; warning cases need explicit review.
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

Updated 2026-10-23. "Implemented" means the opt-in adapter is written, not that
its report has been rendered, tested or human-approved. Example generation is
recorded separately; human acceptance remains pending for every new adapter.
Inherited adapters count only when the
subclass does not override the report entry point.
Nuclear examples were generated directly through the shared renderer before the
new analyzer methods were added. "Implemented" records the written API, not
execution or acceptance of those methods using the earlier PDFs.

| QA analysis                      | Adapter           | Generated example                                     | Human acceptance |
| -------------------------------- | ----------------- | ----------------------------------------------------- | ---------------- |
| PicketFence                      | Implemented       | Standard and branded                                  | Approved pilot   |
| WinstonLutz2D                    | Implemented       | Standard and branded                                  | Pending          |
| WinstonLutz                      | Implemented       | Standard and branded; 17 images                       | Pending          |
| WinstonLutzMultiTargetMultiField | Implemented       | Standard and branded                                  | Pending          |
| Starshot                         | Implemented       | Awaiting TIFF source-to-image distance                | Pending          |
| DRGS                             | Implemented       | Standard and branded                                  | Pending          |
| DRCS                             | Implemented       | Standard and branded                                  | Pending          |
| DRMLC                            | Implemented       | Standard and branded                                  | Pending          |
| FieldAnalysis                    | Implemented       | Standard and branded from fa.dcm                      | Pending          |
| DeviceFieldAnalysis              | Excluded by scope | Not applicable                                        | Not applicable   |
| FieldProfileAnalysis             | Implemented       | Standard and branded                                  | Pending          |
| StandardImagingFC2               | Implemented       | Awaiting fc2.dcm or matching image                    | Pending          |
| IMTLRad                          | Implemented       | Awaiting matching image                               | Pending          |
| DoselabRLf                       | Implemented       | Awaiting matching image                               | Pending          |
| IsoAlign                         | Implemented       | Awaiting matching image                               | Pending          |
| SNCFSQA                          | Implemented       | Awaiting matching image                               | Pending          |
| LasVegas                         | Implemented       | Standard and branded from LasVegas2.dcm               | Pending          |
| ElektaLasVegas                   | Implemented       | Standard and branded                                  | Pending          |
| PTWEPIDQC                        | Implemented       | Standard and branded; analysis warnings retained      | Pending          |
| IBAPrimusA                       | Implemented       | Blocked: input phantom detection fails                | Pending          |
| StandardImagingQC3               | Implemented       | Standard and branded                                  | Pending          |
| StandardImagingQCkV              | Implemented       | Standard and branded                                  | Pending          |
| SNCkV                            | Implemented       | Standard and branded                                  | Pending          |
| SNCMV                            | Implemented       | Standard and branded                                  | Pending          |
| SNCMV12510                       | Implemented       | Awaiting matching image                               | Pending          |
| LeedsTOR                         | Implemented       | Standard and branded                                  | Pending          |
| LeedsTORBlue                     | Implemented       | Awaiting matching input                               | Pending          |
| DoselabMC2kV                     | Implemented       | Standard and branded                                  | Pending          |
| DoselabMC2MV                     | Implemented       | Standard and branded                                  | Pending          |
| ACRDigitalMammography            | Implemented       | Standard and branded; full detail views               | Pending          |
| SmallACRMammography              | Implemented       | Standard and branded from Planar Mammo.dcm            | Pending          |
| ACRCT                            | Implemented       | Blocked: CT archive has no detected HU module         | Pending          |
| ACRMRILarge                      | Implemented       | Standard and branded                                  | Pending          |
| ACRMRIMedium                     | Implemented       | Awaiting matching input                               | Pending          |
| CatPhan503                       | Implemented       | Standard and branded; analysis warnings retained      | Pending          |
| CatPhan504                       | Implemented       | Standard and branded                                  | Pending          |
| CatPhan600                       | Implemented       | Standard and branded                                  | Pending          |
| CatPhan604                       | Implemented       | Standard and branded                                  | Pending          |
| CatPhan700                       | Implemented       | Awaiting matching input                               | Pending          |
| TomoCheese                       | Implemented       | Standard and branded                                  | Pending          |
| CIRS062M                         | Implemented       | Awaiting matching input                               | Pending          |
| QuartDVT                         | Implemented       | Standard and branded                                  | Pending          |
| HypersightQuartDVT               | Implemented       | Awaiting matching input                               | Pending          |
| GECTQA                           | Implemented       | Standard and branded; profile warning retained        | Pending          |
| GEHeliosCTDaily                  | Implemented       | Standard and branded                                  | Pending          |
| DLG                              | Implemented       | Awaiting image and overlap settings                   | Pending          |
| MaxCountRate                     | Implemented       | Standard and branded; two acquisitions, four PDFs     | Pending          |
| PlanarUniformity                 | Implemented       | Standard and branded; two acquisitions; warnings      | Pending          |
| CenterOfRotation                 | Implemented       | Standard and branded; two acquisitions, four PDFs     | Pending          |
| TomographicResolution            | Implemented       | Standard and branded from TomoResolution.dcm          | Pending          |
| SimpleSensitivity                | Implemented       | Blocked: confirmed nonzero source activity needed     | Pending          |
| FourBarResolution                | Implemented       | Standard and branded; default geometry needs review   | Pending          |
| QuadrantResolution               | Implemented       | Standard and branded; reference geometry needs review | Pending          |
| TomographicUniformity            | Implemented       | Standard and branded from Jaszack.dcm; warnings       | Pending          |
| TomographicContrast              | Implemented       | Standard and branded from Jaszack.dcm                 | Pending          |
| Dynalog                          | Excluded by scope | Not applicable                                        | Not applicable   |
| TrajectoryLog                    | Excluded by scope | Not applicable                                        | Not applicable   |
| MachineLogs                      | Excluded by scope | Not applicable                                        | Not applicable   |
| TG51Photon                       | Excluded by scope | Not applicable                                        | Not applicable   |
| TG51ElectronLegacy               | Excluded by scope | Not applicable                                        | Not applicable   |
| TG51ElectronModern               | Excluded by scope | Not applicable                                        | Not applicable   |
| TRS398Photon                     | Excluded by scope | Not applicable                                        | Not applicable   |
| TRS398Electron                   | Excluded by scope | Not applicable                                        | Not applicable   |
| QuasarLightRadScaling            | Implemented       | Awaiting matching input                               | Pending          |
| JawOrthogonality                 | Implemented       | Standard and branded                                  | Pending          |

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
