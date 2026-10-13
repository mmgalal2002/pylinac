# Detailed PDF Report Plan

## Goal

Add a complete, clear PDF report for every supported QA test and its variations.
Show all structured results as readable report sections, with useful charts and
the analysis artifacts. Keep the current PDF option unchanged.

Implementation has started with the Picket Fence pilot. No new PDF dependency
has been installed. Human visual and clinical acceptance is still pending.

## Required Audience And Branding

These rules apply to the Picket Fence pilot and every future detailed report.

- [x] Record that reports are for medical physicists and clinicians, not developers.
- [ ] Use clinical measurement names and short explanations throughout the report.
- [ ] Replace visible JSON paths, field keys and programming terms with human labels.
      For example, central-axis `x` becomes "Horizontal image position (pixels)" in
      Picket Fence. Do not confuse image coordinates with patient anatomy.
- [ ] Use readable measurement numbering while preserving original data in the attachment.
- [ ] Keep complete data and exact field identities in the attached JSON, not in
      developer-facing table headings.
- [ ] Apply full Pylinac branding to typography, page furniture, colours, tables,
      charts, titles, headers and footers. A logo alone is not enough.
- [ ] Allow a custom report brand without changing analysis values or the old PDF.
- [ ] Require every new analysis adapter to follow these audience and branding rules.

## Current Revision Steps

1. [x] Record the clinician-facing wording and full-branding requirements.
2. [ ] Add shared human label handling for nested results and measurement tables.
3. [ ] Apply clinical labels, units and explanations to the Picket Fence report.
4. [ ] Add a reusable brand configuration and use it on every report element.
5. [ ] Regenerate the Picket Fence pilot with the updated wording and branding.
6. [ ] Leave visual review and clinical acceptance to the human before wider rollout.

## Simple API

```python
analysis.publish_pdf("current_report.pdf")
analysis.publish_pdf("current_report.pdf", detailed=False)
analysis.publish_pdf("detailed_report.pdf", detailed=True)
```

- [ ] Keep `detailed=False` as the default.
- [ ] Add `detailed` as a keyword-only parameter after the existing parameters.
- [ ] Keep all existing arguments, return values, file paths, streams and side effects.
- [ ] Route only `detailed=True` to the new report code.
- [ ] Keep the legacy PDF renderer and plotting functions available and unchanged.
- [ ] For analyses without a PDF method, add an explicit detailed report entry point
      without changing their analysis API. Record these cases in the coverage list.

## Report Content

- [ ] Show the test name, variation, input file IDs, analysis date, Pylinac version,
      supplied metadata, notes and the Pylinac or custom logo.
- [ ] Start with key results, warnings and pass/fail status where the analysis
      provides a valid status. Use "Not evaluated" when it does not.
- [ ] Show every JSON field, including nested objects, lists, per-image results,
      per-leaf results and optional fields. Do not silently drop unknown fields.
- [ ] Use clinically reviewed field names, units, table headers and explanations.
      Keep original field identities in the attached JSON for traceability, not as
      printed JSON paths.
- [ ] Keep full numeric precision in the attached JSON. Use consistent display
      precision in the report. Never invent units, tolerances or missing values.
- [ ] Include all long tables and arrays in a readable appendix with repeated
      headings. A summary chart must not replace the complete data.
- [ ] Attach the exact JSON snapshot used to build the report. Also show its data
      in the PDF, so attachment support is not needed to read the results.
- [ ] Include each analysed image or other analysis artifact at a readable size,
      with its file ID, caption, relevant overlays and orientation or scale.
- [ ] For multi-file analyses, show per-file artifacts and results, then the combined
      findings. Do not squeeze all files into one small composite image.
- [ ] Include profiles, measurements and other available analysis artifacts.
      Attach original input files only after human approval of privacy and file size.

## Page Design And Charts

- [ ] Use a clean clinical report design: white pages, dark text, Pylinac green,
      clear headings and compact tables. Use red and amber only for status or warnings.
- [ ] Keep text selectable. Use readable fonts, stable margins, page numbers,
      section bookmarks and an index for long reports.
- [ ] Give images and charts enough space. Preserve image proportions and important
      detail. Use vector charts where practical and sharp raster images otherwise.
- [ ] Give every supported test variation a useful chart or analysis visual based
      on real data. Label axes, units, legends and known tolerance lines.
- [ ] Match charts to the test: leaf errors, profiles, offsets, MTF, HU values,
      dose curves, time series or other available measurements. Do not invent data
      to fill a chart. Scalar-only tests still need a clear result visual.
- [ ] Prevent clipped text, overlapping sections, tiny labels, blank charts and
      broken tables. Handle long names, many files, long notes and large result sets.
- [ ] Make status clear in black-and-white print, not only through colour.
- [ ] Make the PDF complete offline, with local fonts, images and logo assets.
      Do not require a website, cloud service or external viewer to read the report.

## New Code Design

Current anchors: [pylinac/core/pdf.py](pylinac/core/pdf.py),
[pylinac/core/utilities.py](pylinac/core/utilities.py) and the report method in
[pylinac/picketfence.py](pylinac/picketfence.py).

- [ ] Put the new renderer in a separate reporting module. Leave `PylinacCanvas`
      unchanged. Existing report methods need only the opt-in routing branch.
- [ ] Capture structured results once and reuse that snapshot for tables, charts
      and the JSON attachment. Do not rerun analysis or change its measurements.
- [ ] Use small module adapters to supply sections, units, artifacts and chart data.
      Share page layout, table handling and recursive JSON rendering across modules.
- [ ] Render any new result field through a generic section until its adapter has
      a better layout. Track field coverage against the captured JSON.
- [ ] Reuse suitable existing artifact exports. Close only resources opened by
      the new renderer; do not change global plotting settings or caller-owned streams.
- [ ] Start with ReportLab Platypus for automatic page layout and tables, because
      ReportLab is already required. Check its chart and attachment support in a pilot.
- [ ] Compare an HTML/CSS PDF library, such as WeasyPrint, only if the pilot cannot
      meet the design. Check Windows support, packaging, offline use and licence first.
- [ ] Ask before installing any package. Use `uv`; keep new dependencies optional
      and lazy-loaded so the legacy PDF does not need them.
- [ ] Give clear errors for unavailable detailed-report dependencies or unsupported
      data. Do not silently fall back to the legacy report or publish incomplete data.

## Coverage Checklist

Here, "test" means a QA analysis, not a pytest execution report. This is the starting
coverage list, not a claim that every class already has JSON or PDF support.

| Test family         | Required coverage                                                     |
| ------------------- | --------------------------------------------------------------------- |
| Picket Fence        | MLC types, leaves, pickets, orientations and tolerances               |
| Winston-Lutz        | 2D, multi-image, multi-target/multi-field and available axis variants |
| Starshot            | Image variants, detected lines, centre and circle results             |
| VMAT                | DRGS, DRCS, DRMLC and their image and segment variants                |
| Planar imaging      | Every phantom class, inherited variation and ROI result               |
| CT and CBCT         | All CatPhan models and available module results                       |
| ACR                 | CT and all supported MRI analysis variants                            |
| Cheese phantoms     | TomoCheese, CIRS062M and their ROI results                            |
| Quart               | QuartDVT, HypersightQuartDVT and available module results             |
| Field analysis      | Image/device analysis, field profiles, protocols and metrics          |
| GE CT QA and Helios | Every supported analysis class and result section                     |
| DLG                 | Every supported analysis variation and result section                 |
| Nuclear medicine    | Every supported analysis class and result section                     |
| Machine logs        | Dynalog, trajectory logs and supported collection workflows           |
| Calibration         | TG-51, TRS-398 and supported beam/setup variants                      |
| Community modules   | Quasar, orthogonality and any other supported analysis                |

- [ ] Audit public analysis classes, subclasses and inherited PDF methods. Use
      existing basic and data-bank cases to identify file and parameter variations.
- [ ] Add any missing family or variation to this list. Record JSON, artifact and
      PDF support for each item, with a clear plan for any gap.
- [ ] Check plan-generation and core utilities too. Record whether they expose QA
      results that need reports; do not count helper functions as QA tests.
- [ ] Maintain a coverage matrix with each class/variation, result fields, artifacts,
      charts, example inputs and review status. No silent exclusions.

## Delivery And Acceptance

- [ ] First deliver one Picket Fence pilot with full leaf data, clear artifacts and
      charts. Include a large case to check page flow.
- [ ] After human design review, deliver a multi-image Winston-Lutz pilot to check
      per-file and combined sections. Then add adapters for every remaining family.
- [ ] Check that every JSON field is represented, attachments match the snapshot,
      artifacts are present and the PDF opens correctly offline.
- [ ] Check default and explicit `detailed=False` reports against legacy examples.
      Ignore only expected timestamps and PDF metadata when comparing them.
- [ ] Check both modes with existing arguments, custom logos, notes, output streams,
      multi-file cases, warning cases and unavailable optional dependencies.
- [ ] Let the human run tests and confirm visual and clinical acceptance. Do not
      mark human tasks complete on their behalf.
- [ ] Update public API documentation in ReStructuredText. Update the repository
      guide if the new reporting package changes its navigation.

Implementation ownership: [AGENT_TASKS.md](AGENT_TASKS.md).
Human decisions and acceptance: [HUMAN_TASKS.md](HUMAN_TASKS.md).
