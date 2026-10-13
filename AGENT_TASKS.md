# Agent Tasks: Detailed PDF Reports

Plan: [PDF_REPORT_PLAN.md](PDF_REPORT_PLAN.md).
Human decisions: [HUMAN_TASKS.md](HUMAN_TASKS.md).

The shared renderer and Picket Fence pilot are implemented. On 2026-10-13 the
human confirmed that Picket Fence custom PDF generation was tested and approved,
including the pilot design. Wider module rollout is now authorized and in progress.
Approval applies to Picket Fence only, not to unreviewed reports or variations.

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
- [x] Receive human approval of Picket Fence before extending the pilot design.
- [ ] If another PDF library is needed, document the trade-offs and request approval
      before adding or installing dependencies.

## All Tests And Variations

- [x] Record human authorization to proceed with the complete report plan.
- [ ] Deliver a multi-image Winston-Lutz pilot with per-image and combined results.
- [ ] Add a small adapter for every remaining analysis family and variation.
- [ ] Give each variant clear charts or analysis visuals and readable artifacts.
- [ ] Handle missing values, warnings, long arrays, large image sets and custom metadata.
- [ ] Preserve file/stream behaviour, notes, logos, existing options and `open_file`.
- [ ] Finish every row in the coverage matrix before calling coverage complete.

## Per-Analysis Implementation Progress

Updated 2026-10-13. "Implemented" means the opt-in adapter is written, not that
its report has been rendered, tested or human-approved. Examples and acceptance
remain pending for every new adapter. Inherited adapters count only when the
subclass does not override the report entry point.

| QA analysis                      | Adapter     | Generated example          | Human acceptance |
| -------------------------------- | ----------- | -------------------------- | ---------------- |
| PicketFence                      | Implemented | Standard and branded pilot | Approved pilot   |
| WinstonLutz2D                    | Implemented | Pending                    | Pending          |
| WinstonLutz                      | Implemented | Pending                    | Pending          |
| WinstonLutzMultiTargetMultiField | Implemented | Pending                    | Pending          |
| Starshot                         | Implemented | Pending                    | Pending          |
| DRGS                             | Implemented | Pending                    | Pending          |
| DRCS                             | Implemented | Pending                    | Pending          |
| DRMLC                            | Implemented | Pending                    | Pending          |
| FieldAnalysis                    | Implemented | Pending                    | Pending          |
| DeviceFieldAnalysis              | Implemented | Pending                    | Pending          |
| FieldProfileAnalysis             | Implemented | Pending                    | Pending          |
| StandardImagingFC2               | Implemented | Pending                    | Pending          |
| IMTLRad                          | Implemented | Pending                    | Pending          |
| DoselabRLf                       | Implemented | Pending                    | Pending          |
| IsoAlign                         | Implemented | Pending                    | Pending          |
| SNCFSQA                          | Implemented | Pending                    | Pending          |
| LasVegas                         | Implemented | Pending                    | Pending          |
| ElektaLasVegas                   | Implemented | Pending                    | Pending          |
| PTWEPIDQC                        | Implemented | Pending                    | Pending          |
| IBAPrimusA                       | Implemented | Pending                    | Pending          |
| StandardImagingQC3               | Implemented | Pending                    | Pending          |
| StandardImagingQCkV              | Implemented | Pending                    | Pending          |
| SNCkV                            | Implemented | Pending                    | Pending          |
| SNCMV                            | Implemented | Pending                    | Pending          |
| SNCMV12510                       | Implemented | Pending                    | Pending          |
| LeedsTOR                         | Implemented | Pending                    | Pending          |
| LeedsTORBlue                     | Implemented | Pending                    | Pending          |
| DoselabMC2kV                     | Implemented | Pending                    | Pending          |
| DoselabMC2MV                     | Implemented | Pending                    | Pending          |
| ACRDigitalMammography            | Implemented | Pending                    | Pending          |
| SmallACRMammography              | Implemented | Pending                    | Pending          |
| ACRCT                            | Implemented | Pending                    | Pending          |
| ACRMRILarge                      | Implemented | Pending                    | Pending          |
| ACRMRIMedium                     | Implemented | Pending                    | Pending          |
| CatPhan503                       | Pending     | Pending                    | Pending          |
| CatPhan504                       | Pending     | Pending                    | Pending          |
| CatPhan600                       | Pending     | Pending                    | Pending          |
| CatPhan604                       | Pending     | Pending                    | Pending          |
| CatPhan700                       | Pending     | Pending                    | Pending          |
| TomoCheese                       | Pending     | Pending                    | Pending          |
| CIRS062M                         | Pending     | Pending                    | Pending          |
| QuartDVT                         | Pending     | Pending                    | Pending          |
| HypersightQuartDVT               | Pending     | Pending                    | Pending          |
| GECTQA                           | Pending     | Pending                    | Pending          |
| GEHeliosCTDaily                  | Pending     | Pending                    | Pending          |
| DLG                              | Pending     | Pending                    | Pending          |
| MaxCountRate                     | Pending     | Pending                    | Pending          |
| PlanarUniformity                 | Pending     | Pending                    | Pending          |
| CenterOfRotation                 | Pending     | Pending                    | Pending          |
| TomographicResolution            | Pending     | Pending                    | Pending          |
| SimpleSensitivity                | Pending     | Pending                    | Pending          |
| FourBarResolution                | Pending     | Pending                    | Pending          |
| QuadrantResolution               | Pending     | Pending                    | Pending          |
| TomographicUniformity            | Pending     | Pending                    | Pending          |
| TomographicContrast              | Pending     | Pending                    | Pending          |
| Dynalog                          | Pending     | Pending                    | Pending          |
| TrajectoryLog                    | Pending     | Pending                    | Pending          |
| MachineLogs                      | Pending     | Pending                    | Pending          |
| TG51Photon                       | Pending     | Pending                    | Pending          |
| TG51ElectronLegacy               | Pending     | Pending                    | Pending          |
| TG51ElectronModern               | Pending     | Pending                    | Pending          |
| TRS398Photon                     | Pending     | Pending                    | Pending          |
| TRS398Electron                   | Pending     | Pending                    | Pending          |
| QuasarLightRadScaling            | Implemented | Pending                    | Pending          |
| JawOrthogonality                 | Pending     | Pending                    | Pending          |

Variation requirements and known gaps are recorded in
[PDF_REPORT_PLAN.md](PDF_REPORT_PLAN.md). No new adapter is marked human-tested.

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
- [x] Run the installed, cached `prek` hooks and accept formatting fixes. Python
      syntax, Ruff, whitespace, line endings and RST content checks passed.
- [ ] Clear the branch-policy gate on an approved working branch. The current
      `master` branch is blocked by `no-commit-to-branch`; no branch was changed.
- [ ] Build the documentation when Nox and Sphinx are available. They are not
      installed in the current environment. Do not install without human approval.
- [ ] Complete regression checks and clinical acceptance with the human.

The existing `save_histogram` type-annotation diagnostic is unchanged. No regression
test suite, documentation build or screenshot review has been run by the agent.
