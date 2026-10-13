# Human QA Checklist

## Previous QA Work

The completed items below belong to earlier changes, not the detailed PDF project.

- [x] Compare approved QA images before and after these changes with the same dependency versions.
- [x] Run the cloud-backed regression suites with working local test-data access.
- [x] Review the skipped changes in [DEPRECATED_CODE.md](DEPRECATED_CODE.md).
- [x] Accept the verified changes for the intended workflow.

Human review and acceptance have not been completed by the agent.

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

- [ ] Review the Picket Fence pilot for layout, full leaf data, charts and artifacts.
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

All detailed PDF human tasks start unchecked. Only the human may complete them.

## Medical Wording And Full Branding: Pilot Review

- [ ] Review [docs/source/files/picket_fence_detailed_pilot.pdf](docs/source/files/picket_fence_detailed_pilot.pdf)
	for medical-reader wording, readable measurements and image quality.
- [ ] Confirm that central-axis coordinates describe image pixels, not patient
	anatomy, and that no printed JSON paths or developer-style table labels remain.
- [ ] Confirm that displayed picket numbers begin at 1 while the attached JSON
	keeps the original identifiers and exact measurements.
- [ ] Review [docs/source/files/picket_fence_branded_pilot.pdf](docs/source/files/picket_fence_branded_pilot.pdf)
	for the title, fonts, colours, tables, charts, header and footer, not only the logo.
- [ ] Approve the Picket Fence wording and brand design before applying the same
	rules to the remaining QA reports. Report measurements and image overlays must
	remain faithful to the original analysis.
