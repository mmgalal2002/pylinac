# Detailed PDF Report Plan

## Goal

Add a complete, clear PDF report for every supported **X-ray imaging, MRI, CT
and mammography** QA test and its variations, plus every nuclear medicine
analysis and every supported phantom-based QA analysis in the package. The human
expanded the scope on 2026-10-23 to include nuclear medicine and all phantom
classes and variations; this supersedes the earlier nuclear exclusion. Calibration,
machine logs and device-only workflows remain explicitly excluded, not silently
omitted.
No supported phantom-based QA analysis is excluded because of its modality.
Show all structured results as readable report sections, with useful charts and
the analysis artifacts. Keep the current PDF option unchanged.

The Picket Fence pilot is implemented, human-tested and human-approved as confirmed
on 2026-10-13. The human authorized the full rollout. No new PDF dependency has
been installed. Other reports and additional variations still require review.

Current delivery: 47 imaging adapters; nine nuclear medicine analyses are in scope
and still need public PDF adapters. Standard and branded PDF examples exist for
31 imaging analyses (62 PDFs) and eight nuclear analyses (22 PDFs): 84 review PDFs
in total. Nuclear examples were generated directly through the existing shared
renderer without source-code or result-JSON changes. SimpleSensitivity is blocked
on confirmed nonzero source activity. Fourteen imaging analyses await inputs/settings
and two supplied datasets fail detection before report generation. See the
individual rows in [AGENT_TASKS.md](AGENT_TASKS.md) for exact progress; do not call
coverage accepted while these gaps and human reviews remain open.

## PDF-Only Generation: 2026-10-23

- [x] Generate standard/branded review PDFs for MaxCountRate, PlanarUniformity,
      CenterOfRotation, TomographicResolution, FourBarResolution,
      QuadrantResolution, TomographicUniformity and TomographicContrast, using
      supplied local inputs only and updating Markdown after each analysis.
- [x] Record source images, exact analysis settings, reference/default geometry,
      existing warnings and the unchanged exclusive-end uniformity frame range.
- [ ] Obtain the nonzero source activity and acquisition reference required for
      SimpleSensitivity, then generate its PDFs. Supplied DICOM dose values are zero.
- [ ] Generate the remaining imaging examples once matching inputs and clinical
      configuration are supplied; the existing blockers remain open.
- [ ] Obtain human geometry, wording, layout, measurement and clinical acceptance.

Outputs: `E:\dcms-20261013T142612Z-1-001\detailed-reports`. Incremental nuclear
status is recorded in that folder's `generation_status.md` and in
[AGENT_TASKS.md](AGENT_TASKS.md). Historical JSON generation records are unchanged.
No analysis code, plotting method or public API was edited, and no tests, builds,
linters, screenshots or clinical acceptance checks were performed for this pass.

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
2. [x] Add shared human label handling for nested results and measurement tables.
3. [x] Apply clinical labels, units and explanations to the Picket Fence report.
4. [x] Add a reusable brand configuration and use it on report text, tables,
       charts, page backgrounds, headers and footers. Preserve the original image artifact.
5. [x] Regenerate the Picket Fence pilot with the updated wording and branding.
6. [x] Receive human approval of the Picket Fence pilot before wider rollout
       (confirmed 2026-10-13). Keep other reports' acceptance separate.

Current examples:

- [docs/source/files/picket_fence_detailed_pilot.pdf](docs/source/files/picket_fence_detailed_pilot.pdf)
- [docs/source/files/picket_fence_branded_pilot.pdf](docs/source/files/picket_fence_branded_pilot.pdf)

Both examples were rendered from the local documentation image without installing
packages or using cloud data. Editor diagnostics found no new renderer errors.
Automated PDF text extraction was not run because a PDF parser is not installed.
The human approved the Picket Fence pilot on 2026-10-13. This approval does not
replace review of other reports or of additional Picket Fence variations.

## Display Precision

Round printed numbers for medical readers, not the stored analysis data.

| Measurement                                        | Printed precision                                           |
| -------------------------------------------------- | ----------------------------------------------------------- |
| Leaf-position errors and tolerances                | 3 decimal places in mm                                      |
| Leaf positions, picket offsets, spacing and widths | 2 decimal places in mm                                      |
| Percentages                                        | 1 decimal place                                             |
| Angles                                             | 1 decimal place in degrees                                  |
| Image coordinates                                  | 1 decimal place in pixels                                   |
| Counts and measurement identifiers                 | Whole numbers                                               |
| Other floating-point measurements                  | 2 decimal places unless the adapter sets a better precision |

- [x] Add per-field precision that also applies to nested measurements.
- [x] Apply the same precision to tables, chart axes and tolerance labels.
- [x] Remove negative zero from rounded output.
- [x] Keep the original JSON and pass/fail calculations at full precision.
- [x] Regenerate the standard and branded Picket Fence examples.
- [ ] Have the human confirm the display precision, especially near tolerances.

Histogram intervals may use a few extra decimals when needed to keep neighbouring
bounds distinct. Every future report adapter must choose sensible precision for
its own clinical units rather than print long floating-point values.

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

| Test family | Required report coverage |
| --- | --- |
| Picket Fence | MLC types, separate/pair leaves, orientations and tolerances |
| Winston-Lutz | 2D, multi-image, multi-target/multi-field and available axes |
| Starshot | Image/combined-image inputs, reference point, detected lines and circle |
| VMAT | DRGS, DRCS, DRMLC; both input images and every segment |
| Planar imaging | Every concrete phantom class, inherited variation and ROI result |
| CT and CBCT | All CatPhan models and available module results |
| ACR | CT, MRI Large and MRI Medium; all module and localizer results |
| Cheese phantoms | TomoCheese, CIRS062M and their ROI results |
| Quart | QuartDVT, HypersightQuartDVT and their module results |
| Field analysis | Image-based field/profile analysis, protocols and custom metrics |
| GE CT QA and Helios | Every configured result section and available module artifact |
| DLG | Image-derived leaf overlap measurements and recorded fit |
| Community imaging modules | Quasar scaling and jaw orthogonality |
| Nuclear medicine | Every analyzer, result field, chart/image artifact and supported variation |
| Calibration, machine logs, device-only workflows | Excluded by the human on 2026-10-23 |

## Class And Variation Matrix

All result-model fields are rendered recursively and retained in the exact JSON
attachment. Future unlabelled fields use readable generic labels rather than
being omitted. Clinical review remains necessary for the new adapters.
The authoritative per-class implementation, generation and acceptance status is
the table in [AGENT_TASKS.md](AGENT_TASKS.md). Each class below has its own row
there, including inherited report methods; exclusions also have explicit rows.

| Analysis class | Snapshot/field coverage | Required variations | Analysis artifacts/visuals |
| --- | --- | --- | --- |
| PicketFence | PFResult, including every leaf position/error, width and CAX | Every built-in/custom MLC, pair/separate leaves, both orientations, action tolerance, log/BB reference | Analysed image, leaf-error chart, histogram, picket offsets and widths |
| WinstonLutz2D | WinstonLutz2DResult, all vectors and image coordinates | Single image, field/BB detection options and machine scale | Full image, BB detail, measured distance visual |
| WinstonLutz | WinstonLutzResult and both per-image collections | Gantry/collimator/couch/combinations, TIFF/CBCT, virtual shift, duplicate angle sets | Every full image and BB detail, per-image distance chart |
| WinstonLutzMultiTargetMultiField | Complete combined and per-image results, BB arrangements and shift | Multiple BBs/fields, missing matches, couch yaw and machine scale | Every full image and BB detail, per-BB/per-image distances |
| Starshot | StarshotResults including line angles, circle and optional reference | Single/combined images, TIFF/DICOM, reference point, tolerance | Full image and fitted-circle detail |
| DRGS | VMATResult and every named/indexed segment | ROI selection, tolerances and image order | Open/delivery images and median profiles separately |
| DRCS | DRCSResult, segments, collimator angles and rotation offset | ROI angles, collimator deviations and tolerance | Open/delivery images and median profiles separately |
| DRMLC | VMATResult and every named/indexed segment | ROI selection, tolerances and image order | Open/delivery images and median profiles separately |
| FieldAnalysis | FieldResult; no excluded measurement fields | Image centering, edge methods, normalisation and protocols | Separate image and horizontal/vertical profiles |
| FieldProfileAnalysis | FieldProfileResult, all metrics and every profile sample | Built-in/custom metrics, edge methods, normalisation and centering | Image with sampling regions and both measured profiles |
| StandardImagingFC2 | LightRadResult | Field/BB setup, offsets and configured criteria | Field image and detected measurements |
| IMTLRad | LightRadResult | Phantom-specific BB/field geometry | Field image and detected measurements |
| DoselabRLf | LightRadResult | Phantom-specific BB/field geometry | Field image and detected measurements |
| IsoAlign | LightRadResult | Phantom-specific BB/field geometry | Field image and detected measurements |
| SNCFSQA | LightRadResult | Phantom-specific BB/field geometry | Field image and detected measurements |
| LasVegas | PlanarResult including every low-contrast ROI | Contrast thresholds, setup and positioning | Image, contrast and visibility plots |
| ElektaLasVegas | PlanarResult including every low-contrast ROI | Elekta geometry and criteria | Image, contrast and visibility plots |
| PTWEPIDQC | PlanarResult, MTF and uniformity | Phantom-specific ROIs, unavailable MTF points and warnings | Image and available MTF/contrast plots |
| IBAPrimusA | PlanarResult and every ROI | Phantom positioning, SSD and thresholds | Image and available MTF/contrast plots |
| StandardImagingQC3 | PlanarResult and every ROI | Phantom geometry and thresholds | Image and available MTF/contrast plots |
| StandardImagingQCkV | PlanarResult and every ROI | kV geometry and thresholds | Image and available MTF/contrast plots |
| SNCkV | PlanarResult and every ROI | kV geometry and thresholds | Image and available MTF/contrast plots |
| SNCMV | PlanarResult and every ROI | MV geometry and thresholds | Image and available MTF/contrast plots |
| SNCMV12510 | PlanarResult and every ROI | Model-specific geometry and thresholds | Image and available MTF/contrast plots |
| LeedsTOR | PlanarResult and every ROI | Rotation, contrast criteria and unavailable MTF points | Image and available MTF/contrast plots |
| LeedsTORBlue | PlanarResult and every ROI | Blue phantom geometry and thresholds | Image and available MTF/contrast plots |
| DoselabMC2kV | PlanarResult and every ROI | kV geometry and thresholds | Image and available MTF/contrast plots |
| DoselabMC2MV | PlanarResult and every ROI | MV geometry and thresholds | Image and available MTF/contrast plots |
| ACRDigitalMammography | ACRDigitalMammographyResult including masses, fibres, specks and detection data | Orientation, thresholds, ROI modes and mammography geometry | Full image, all measurement curves and individual ROI zooms |
| SmallACRMammography | ACRDigitalMammographyResult; same complete fields | Small/square geometry and supported ROI detection modes | Full image, all measurement curves and individual ROI zooms |
| CatPhan503 | CatphanResult and every available nested module | HU/geometry/thickness, resolution and uniformity | Every available module image, curve and side view |
| CatPhan504 | CatphanResult and every available nested module | HU/geometry/thickness, resolution, uniformity and low contrast | Every available module image, curve and side view |
| CatPhan600 | CatphanResult and every available nested module | Model-specific modules and criteria | Every available module image, curve and side view |
| CatPhan604 | CatphanResult and every available nested module | Model-specific modules, HU reference and criteria | Every available module image, curve and side view |
| CatPhan700 | CatphanResult and every available nested module | Model-specific modules and criteria | Every available module image, curve and side view |
| ACRCT | ACRCTResult and all nested modules | CT number, geometry, low contrast, uniformity and resolution | Separate module images and available curves |
| ACRMRILarge | ACRMRIResult and all nested modules | Slice 1/11, uniformity/ghosting, localizer, geometric distortion and low-contrast slices | Separate module images, localizer and measured profiles |
| ACRMRIMedium | ACRMRIResult and all nested modules | Medium phantom geometry and supported MRI modules | Separate module images, localizer and measured profiles |
| TomoCheese | TomoCheeseResult including complete ROI values | ROI setup and optional supplied densities | Analysed image and density curve when configured |
| CIRS062M | CheeseResult including complete ROI values | ROI setup and optional supplied densities | Analysed image and density curve when configured |
| QuartDVT | QuartDVTResult and all nested modules | HU, uniformity, geometry and criteria | Separate module images and scan overview |
| HypersightQuartDVT | QuartDVTResult and all nested modules | Hypersight phantom-specific modules and criteria | Separate module images and scan overview |
| GECTQA | GECTQAResult, configured tests, localization and compatibility results | Scanner/phantom profiles, reference values and optional modules | Separate module images and available MTF visual |
| GEHeliosCTDaily | GEHeliosResult including every ROI and low-contrast slice | Contrast scale, resolution, low contrast, noise and uniformity | Separate module images, all available curves and scan overview |
| DLG | Measured gap, planned/measured per-leaf arrays and full regression result | Actual planned overlaps, MLC geometry and sampling settings | Leaf-gap scatter/fit and input image |
| QuasarLightRadScaling | Complete inherited LightRadResult | Quasar scaling and field/BB geometry | Field image and detected measurements |
| JawOrthogonality | Four recorded corner angles and every detected edge | Image edges and square-field setup | Analysed image with detected jaw edges |
| MaxCountRate | All scalar results and count-rate `plot_data` | Every supported acquisition/frame configuration | Count-rate chart with highlighted maximum |
| PlanarUniformity | All per-frame results and serialized frame objects | Every supported frame and FOV configuration | Per-frame image views and FOV measurements |
| CenterOfRotation | All scalar results and fit/residual `plot_data` | Every supported image set and acquisition configuration | Sine-fit chart and X/Y residual charts |
| TomographicResolution | All scalar results and X/Y/Z profile `plot_data` | Every supported image set and profile configuration | Three measured-profile charts with Gaussian fits |
| SimpleSensitivity | Every scalar result; empty `plot_data` | Every supported acquisition configuration | All available analysis results; no chart is produced |
| FourBarResolution | All scalar results and X/Y profile `plot_data` | Every supported image set and profile configuration | Two measured-profile charts with double-Gaussian fits |
| QuadrantResolution | All scalar results and MTF/FWHM `plot_data` | Every supported image set and pair-distance configuration | MTF and FWHM charts with secondary-axis metadata |
| TomographicUniformity | All scalar results and FOV measurements | Every supported frame and FOV configuration | Tomographic image view and FOV overlays |
| TomographicContrast | All scalar results and mean/max contrast `plot_data` | Every supported image set and contrast configuration | Contrast chart with mean and maximum series |

Generation uses local inputs only. Missing variants remain awaiting input instead
of being generated from the wrong phantom. IBA Primus and ACR CT currently fail
input detection before PDF generation. Starshot needs the measured SID for the
supplied TIFF. No scientific analysis algorithm was changed to bypass these gaps.

Core image/profile/ROI/geometry/metric utilities and plan generators are supporting
tools, not independent image QA result workflows. Their outputs are represented
through the owning analyses above; this rollout does not create pytest reports
or PDF reports for helper functions, data models or plan-construction classes.

### Remaining Variation Review

- [ ] Review every variation column above with approved matching data.
- [ ] Generate missing inputs through the local manifest; record each variation
      and its exact analysis settings in the example-generation output.
- [ ] Confirm streams, notes, custom logos/brands and unchanged legacy layouts.
- [ ] Review all displayed labels, units, warnings, tables, chart scales and artifacts.
- [ ] Run content, documentation and regression checks when authorized by the human.

- [ ] Audit public analysis classes, subclasses and inherited PDF methods. Use
      existing basic and data-bank cases to identify file and parameter variations.
- [ ] Add any missing family or variation to this list. Record JSON, artifact and
      PDF support for each item, with a clear plan for any gap.
- [ ] Check plan-generation and core utilities too. Record whether they expose QA
      results that need reports; do not count helper functions as QA tests.
- [x] Maintain a coverage matrix with each class/variation, result fields, artifacts,
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
