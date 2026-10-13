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

Nuclear medicine, machine logs, calibration and non-image device workflows are
excluded. The agent removed its earlier out-of-scope additions. Existing methods
for those workflows were not replaced.

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
