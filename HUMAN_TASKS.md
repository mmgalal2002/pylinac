# Human QA Checklist

## Previous QA Work

The completed items below belong to earlier changes, not the detailed PDF project.

- [x] Compare approved QA images before and after these changes with the same dependency versions.
- [x] Run the cloud-backed regression suites with working local test-data access.
- [x] Review the skipped changes in [DEPRECATED_CODE.md](DEPRECATED_CODE.md).
- [x] Accept the verified changes for the intended workflow.

Human review and acceptance have not been completed by the agent.

## Picket Fence Approval: 2026-10-13

The human confirmed that Picket Fence custom PDF generation is done, tested and
approved, and instructed the agent to proceed with the full report plan. This is
a record of the human's decision, not acceptance performed by the agent. Other
analyses and unreviewed variations remain pending.

## Confirmed Imaging Scope: 2026-10-13

- [x] Human limited this rollout to X-ray imaging, MRI, CT and mammography.
- [x] Human supplied `E:\dcms-20261013T142612Z-1-001\dcms` for local generation.
- [x] Human declined content checks and dependency installation.

That initial scope excluded nuclear medicine, machine logs, calibration and
non-image device workflows. On 2026-10-23 the human expanded PDF coverage to all
nuclear medicine analyses and every supported phantom-based QA analysis and
variation. Calibration, machine logs and device-only workflows remain excluded.
The nuclear plot-data JSON task is separate from PDF generation.

## Nuclear PDF Generation And Review: 2026-10-23

- [x] Human authorized nuclear medicine and all supported phantom analyses and
      variations in the detailed-report scope.
- [x] Human authorized PDF-only generation with one-by-one Markdown tracking;
      no analysis-code or JSON changes, tests, builds, linters or screenshots.
- [ ] Review MaxCountRate PDFs and confirm acquisition timing and count-rate units.
- [ ] Review PlanarUniformity PDFs, each frame and all FOV measurements. Both
      acquisitions emit `All-NaN slice encountered` warnings; check for unavailable
      measurements and confirm the analysis settings and unchanged image legends.
- [ ] Review CenterOfRotation PDFs, acquisition geometry, fits and residuals.
- [ ] Review TomographicResolution PDFs, image scaling and three profile fits.
- [ ] Supply/confirm SimpleSensitivity activity, nuclide and acquisition settings;
      review the resulting PDF when available. Supplied sensitivity images identify
      iodine-131 but record zero dose; supply the nonzero source activity in MBq,
      its reference time, and the matching phantom/background acquisition pair.
- [ ] Review FourBarResolution PDFs and confirm bar geometry and image scaling.
- [ ] Confirm QuadrantResolution phantom settings and review its PDFs. The review
      pair uses the documented QuadrantBar reference widths
      `(4.23, 3.18, 2.54, 2.12)` mm, `roi_diameter_mm=70` and
      `distance_from_center_mm=130`; confirm actual widths, ordering and ROI size.
- [ ] Review TomographicUniformity PDFs and all image/FOV measurements. The local
      input is spelled `Nuclear/Jaszack.dcm` and contains 45 source images; default
      averaging includes images 1-44, with excluded end marker 45. Confirm the
      appropriate uniformity slab and review the `All-NaN slice encountered`
      warning and unchanged image/legend placement.
- [ ] Confirm TomographicContrast phantom settings and review its PDFs. The pair
      uses library-default sphere diameters `(38, 31.8, 25.4, 19.1, 15.9, 12.7)` mm
      and angles `(-10, -70, -130, -190, 110, 50)` degrees; confirm these against
      the actual phantom before clinical use.

PDF generation is not clinical acceptance. Keep every new report's human review
unchecked until the human confirms it. Existing imaging acceptance is unchanged.
Twenty-two nuclear review PDFs were generated for eight analyses, alongside the
62 existing imaging PDFs. SimpleSensitivity remains blocked on source activity.
See the output folder's `generation_status.md` for per-analysis inputs, settings,
warning cases and filenames; the historical JSON generation record is unchanged.

## Nuclear publish_pdf API Review: 2026-10-23

- [x] Human authorized public PDF methods for all nine nuclear analyzers, with
      the same image, chart and branding standards as the other detailed reports.
- [ ] Generate reports through each new `publish_pdf()` method using approved
      local inputs, timing, geometry and activity; review every included image
      and chart. SimpleSensitivity requires confirmed positive activity in MBq.
- [ ] Exercise file and binary-stream output, notes, metadata, local logos,
      branding-logo precedence, custom fonts/colours and `open_file` behavior.
- [ ] Confirm the new-only API defaults to `detailed=True`, rejects
      `detailed=False` and requires a completed analysis.
- [ ] Compare all displayed measurements and attached JSON with the existing
      analysis results; review uniformity warnings and exclusive-end frame wording.
- [ ] Run approved regression/documentation checks and accept each API separately.

Only syntax and editor diagnostics were checked for the added methods. The 22
existing nuclear PDFs predate these APIs and do not validate their execution.
No runtime, visual, clinical or complete-system acceptance is claimed.

## Nuclear Plot-Ready JSON Review: 2026-10-23

- [ ] Review the nuclear chart coverage and scope notes in
      [IMAGE_PLOT_INVENTORY.md](IMAGE_PLOT_INVENTORY.md); confirm the six line/scatter
      chart outputs and the three no-chart cases are represented correctly.
- [ ] Confirm each chart-producing nuclear result's `plot_data.line_plots`
      reproduces its line/scatter series and fitted curves; confirm image pixels
      and phantom/ROI overlays are absent from result JSON.
- [ ] Confirm the current line-series metadata is sufficient for the intended
      front end, including fit parameters, X limits and secondary axes; decide
      whether an explicit chart-kind field is needed.
- [ ] Confirm Simple Sensitivity's `plot_data` is empty because it has no plot.
- [ ] Review chart-only JSON size using representative NM datasets before using
      it in web responses.
- [x] Authorize the focused serialization check using the supplied COR DICOMs
      (user direction, 2026-10-23); results are recorded in [AGENT_TASKS.md](AGENT_TASKS.md).
- [ ] Review the COR chart JSON check results and decide whether its payload is
      sufficient for the intended front end.
- [ ] Review the attached Tomographic Uniformity Matplotlib image using its
      actual source DICOM (`Jaszczak.dcm`); the supplied COR files are not this
      image's source. Verify pixel intensity/windowing and decide whether to
      move or simplify the legend before accepting any display change.

## Custom Logo Review: 2026-10-13

- [ ] Review detailed PDFs with an approved local logo using the existing `logo=`
      argument and the new `branding.logo` option. Confirm `logo=` wins when both
      are supplied.
- [ ] Confirm the selected logo appears on every page without distortion,
      unwanted backgrounds or overlap with the header and report content.

## ARTBackend Deployment And Review

- [ ] Manually deploy this custom pylinac into the backend's runtime environment
      after installing requirements, then restart the backend. The current editor
      interpreter still has stock pylinac rather than the detailed renderer.
- [ ] Review the Pro-ART identity, existing logo, teal tables, blue charts,
      analysis titles, headers and footers using approved real imaging inputs.
- [ ] Exercise the fourteen updated imaging services and compare their PDF
      attachments, measurements, JSON results and API payloads with approved data.
- [ ] Review the retained synthetic Picket Fence example separately; do not treat
      the automated synthetic smoke check as clinical or visual acceptance.
- [ ] Review the pre-existing Picket Fence failure when `crop_mm` is omitted.
      The integration smoke check used `crop_mm=0`; the analysis defaults were not
      changed as part of this PDF replacement.
- [ ] Run the unavailable `prek` quality gate and accept the backend integration
      only after the required clinical, visual and deployment checks.

## Imaging Report Review

The implementation/example status of every class is in
[AGENT_TASKS.md](AGENT_TASKS.md). Standard and branded review PDFs and per-class
generation records are in `E:\dcms-20261013T142612Z-1-001\detailed-reports`.

- [ ] Review every generated X-ray, CT, MRI and mammography report pair.
- [ ] Confirm the supplied image was analysed with the correct phantom class,
      setup, orientation, scale and clinical parameters.
- [ ] Review both large and small mammography reports, including all mass,
      speck-group, fibre and zoomed artifacts.
- [ ] Supply the correct Starshot SID and matching data for awaiting-input rows.
- [ ] Resolve input detection for ACR CT and IBA Primus with approved data/settings.
- [ ] Run content checks, documentation build and regression checks when desired.
- [ ] Accept each new report and variation separately. Picket Fence pilot approval
      is not acceptance of the new reports or regenerated examples.

## Detailed PDF Reports: Decisions

Plan: [PDF_REPORT_PLAN.md](PDF_REPORT_PLAN.md).
Agent work: [AGENT_TASKS.md](AGENT_TASKS.md).

- [ ] Review the scope and the proposed `detailed=True` option.
- [ ] Supply approved examples for every test family and important variation,
      including multi-file cases, failed checks, warnings and large result sets.
- [ ] Confirm required site metadata, logos, page format and privacy rules.
- [ ] Confirm which source artifacts may be attached. Approve any sensitive input
      data and acceptable PDF size before it is embedded.
- [ ] Approve any new PDF dependency before it is installed, if one is needed.

## Detailed PDF Reports: Review And Acceptance

- [x] Review and approve the Picket Fence pilot (human confirmation, 2026-10-13).
- [ ] Review the multi-image Winston-Lutz pilot before the wider rollout.
- [ ] Review every coverage-matrix row, including all supported variations.
- [ ] Compare the report tables and attached JSON with the actual analysis results.
      Confirm values, units, tolerances, warnings and pass/fail labels are correct.
- [ ] Confirm every artifact is readable and matches the correct input file.
- [ ] Open PDFs offline in the normal PDF viewer and check black-and-white printing.
      Check page flow, small labels, long tables and JSON attachment access.
- [ ] Compare default and `detailed=False` PDFs with approved legacy reports.
      Confirm existing calls, notes, logos, streams and analysis values still work.
- [ ] Run focused and cloud-backed regression checks with approved local data and
      confirm the supported Python and Windows workflows.
- [ ] Accept the complete detailed report workflow only after all required cases
      are reviewed. Record any remaining limitations.

Only confirmed human decisions are marked complete. Approval of the remaining
reports and complete-system acceptance remain unchecked.

## Medical Wording And Full Branding: Pilot Review

- [x] Review [docs/source/files/picket_fence_detailed_pilot.pdf](docs/source/files/picket_fence_detailed_pilot.pdf)
      for medical-reader wording, readable measurements and image quality.
- [ ] Confirm that central-axis coordinates describe image pixels, not patient
      anatomy, and that no printed JSON paths or developer-style table labels remain.
- [ ] Confirm that displayed picket numbers begin at 1 while the attached JSON
      keeps the original identifiers and exact measurements.
- [x] Review [docs/source/files/picket_fence_branded_pilot.pdf](docs/source/files/picket_fence_branded_pilot.pdf)
      for the title, fonts, colours, tables, charts, header and footer, not only the logo.
- [x] Approve the Picket Fence wording and brand design before applying the same
      rules to the remaining QA reports. Report measurements and image overlays must
      remain faithful to the original analysis.
- [ ] Review rounded measurements near the tolerance limits. Confirm that printed
      precision is useful, counts stay whole and pass/fail uses unrounded results.

## Recent Plotly Test Updates: 2026-10-23

- [ ] Run the focused pytest command in [RECENT_TEST_COMMITS.md](RECENT_TEST_COMMITS.md);
      confirm required local test-data access and review the results.
- [ ] Review the Plotly threshold/axis behavior and updated figure/trace expectations
      before accepting the test changes.
