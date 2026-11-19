from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from functools import partial
from io import BytesIO
from json import JSONEncoder
from math import ceil, floor
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple
from xml.sax.saxutils import escape

import numpy as np
from matplotlib import pyplot as plt
from matplotlib.ticker import MaxNLocator
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Flowable,
    Frame,
    Image,
    LongTable,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

if TYPE_CHECKING:
    from .acr import ACRCT467, ACRCT467Comparison, ACRCT467Result, ACRCT467Statistics

_INK = colors.HexColor("#22292C")
_TEAL = colors.HexColor("#15556A")
_MUTED = colors.HexColor("#536360")
_RULE = colors.HexColor("#D5DEDB")
_TINT = colors.HexColor("#F2F5F4")
_PLOT_GREEN = "#267661"
_PAGE_SIZE = landscape(A4)
_MARGIN = 51
_TOP_MARGIN = 77
_BOTTOM_MARGIN = 50
_CELL = ParagraphStyle(
    "ACR cell", fontName="Helvetica", fontSize=9, leading=11, textColor=_INK
)
_NUMBER = ParagraphStyle("ACR number", parent=_CELL, alignment=TA_RIGHT)
_HEADER = ParagraphStyle(
    "ACR table header", parent=_CELL, fontName="Helvetica-Bold", textColor=colors.white
)
_NUMBER_HEADER = ParagraphStyle("ACR number header", parent=_HEADER, alignment=TA_RIGHT)
_BODY = ParagraphStyle(
    "ACR body", parent=_CELL, fontSize=10.5, leading=15, spaceAfter=7
)
_HEADING = ParagraphStyle(
    "ACR heading",
    parent=_BODY,
    fontName="Helvetica-Bold",
    fontSize=16,
    leading=21,
    textColor=_TEAL,
    spaceAfter=8,
    keepWithNext=True,
)
_TITLE = ParagraphStyle("ACR title", parent=_HEADING, fontSize=22, leading=29)
_CAPTION = ParagraphStyle("ACR caption", parent=_BODY, fontSize=9, textColor=_MUTED, spaceBefore=8)
_SECTION = ParagraphStyle(
    "ACR section",
    parent=_BODY,
    fontName="Helvetica-Bold",
    fontSize=12,
    leading=16,
    textColor=_TEAL,
    spaceBefore=12,
    spaceAfter=5,
    keepWithNext=True,
)
_TABLE_SECTION = ParagraphStyle("ACR table section", parent=_SECTION, keepWithNext=False)

_STATISTICS = (
    ("pixel_count", "Pixel count"),
    ("mean", "Mean"),
    ("median", "Median"),
    ("stdev", "Std. deviation"),
    ("variance", "Variance"),
    ("minimum", "Minimum"),
    ("maximum", "Maximum"),
    ("interquartile_range", "IQR"),
    ("median_absolute_deviation", "Median abs. deviation"),
    ("skewness", "Skewness"),
    ("excess_kurtosis", "Excess kurtosis"),
)

_DENSITY_COLUMNS = ("material", "relative_electron_density", "physical_density_g_cm3")
_SUPPLIED_DENSITIES = (
    ("Lung (LN-300)", 0.29, 0.30),
    ("Lung (LN-450)", 0.40, 0.45),
    ("Adipose (AP6)", 0.90, 0.92),
    ("Breast", 0.96, 0.99),
    ("CT Solid Water", 0.99, 1.02),
    ("Brain", 1.05, 1.05),
    ("Liver (LV1)", 1.07, 1.08),
    ("Inner Bone", 1.09, 1.12),
    ("Bone (B200)", 1.11, 1.15),
    ("Bone (CB2-30% Mineral)", 1.28, 1.34),
    ("Bone (CB2-50% Mineral)", 1.47, 1.56),
    ("Cortical Bone (SB3)", 1.69, 1.82),
    ("True Water", 1.00, 1.00),
    ("Titanium Insert (optional)", 3.79, 4.59),
)
_GUIDE_NOTES = (
    "The guide's GE CT/i examples and observed HU variation are not acceptance limits.",
    "These supplied nominal densities are not measured values. Some differ from the guide's Table 1. "
    "Use the phantom-specific certificate and confirmed rod positions for calibration.",
)


def _display(value: object) -> str:
    if value is None:
        return "Not available"
    if isinstance(value, (tuple, list)):
        return ", ".join(_display(item) for item in value) if value else "None"
    if isinstance(value, Mapping):
        return "\n".join(
            f"{str(name).replace('_', ' ').capitalize()}: {_display(item)}"
            for name, item in value.items()
        ) or "None"
    return str(value)


def _cell(value: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(_display(value)).replace("\n", "<br/>"), style)


def _table(
    headers: Sequence[str],
    rows: Sequence[Sequence[object]],
    width: float,
    *,
    weights: Sequence[float],
    label_columns: int = 1,
    padding: int = 3,
) -> LongTable:
    cells = [
        [
            _cell(label, _HEADER if column < label_columns else _NUMBER_HEADER)
            for column, label in enumerate(headers)
        ],
        *[
            [
                _cell(value, _CELL if column < label_columns else _NUMBER)
                for column, value in enumerate(row)
            ]
            for row in rows
        ],
    ]
    weight_total = sum(weights)
    preferred = [width * weight / weight_total for weight in weights]
    minimums = [
        preferred[column]
        if column < label_columns
        else 13 + max(
            (
                stringWidth(_display(row[column]), _NUMBER.fontName, _NUMBER.fontSize)
                for row in rows
            ),
            default=0,
        )
        for column in range(len(headers))
    ]
    spare = width - sum(minimums)
    if spare >= 0:
        gaps = [max(0, target - minimum) for target, minimum in zip(preferred, minimums)]
        gap_total = sum(gaps)
        if gap_total:
            preferred = [
                minimum + spare * gap / gap_total
                for minimum, gap in zip(minimums, gaps)
            ]

    return LongTable(
        cells,
        colWidths=preferred,
        repeatRows=1,
        splitInRow=1,
        hAlign="LEFT",
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _TEAL),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), (colors.white, _TINT)),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), padding),
                ("BOTTOMPADDING", (0, 0), (-1, -1), padding),
                ("LINEBELOW", (0, -1), (-1, -1), 0.6, _RULE),
            ]
        ),
    )


def _pairwise_table(pairs: Sequence[ACRCT467Comparison], width: float) -> LongTable:
    return _table(
        (
            "First ROI",
            "Second ROI",
            "Mean difference",
            "Median difference",
            "Pooled SD",
            "Mean CNR",
            "Median CNR",
        ),
        [
            (
                pair.first_roi,
                pair.second_roi,
                pair.mean_difference,
                pair.median_difference,
                pair.pooled_stdev,
                pair.mean_cnr,
                pair.median_cnr,
            )
            for pair in pairs
        ],
        width,
        weights=(0.62, 0.62, 1.15, 1.15, 1, 1, 1),
        label_columns=2,
    )


def _facts(rows: Sequence[tuple[str, object]], width: float, pairs: int = 2) -> LongTable:
    padded = [*rows, *([("", "")] * (-len(rows) % pairs))]
    return _table(
        ("Field", "Value") * pairs,
        [
            tuple(value for pair in padded[start : start + pairs] for value in pair)
            for start in range(0, len(padded), pairs)
        ],
        width,
        weights=(1.1, 1.65) * pairs,
        label_columns=pairs * 2,
        padding=2,
    )


def _table_heading(title: str) -> list[Flowable]:
    return [CondPageBreak(78), _cell(title, _TABLE_SECTION)]


class _ReportFigure(NamedTuple):
    key: str
    title: str
    caption: str
    stream: BytesIO


def _render_figure(key: str, title: str, caption: str, figure: plt.Figure) -> _ReportFigure:
    try:
        stream = BytesIO()
        figure.savefig(stream, format="png", dpi=160)
        stream.seek(0)
        return _ReportFigure(key, title, caption, stream)
    finally:
        plt.close(figure)


def _intensity_figure(result: ACRCT467Result) -> _ReportFigure:
    names = [name.removeprefix("ROI ") for name in result.rois]
    means = [roi.mean for roi in result.rois.values()]
    medians = [roi.median for roi in result.rois.values()]
    deviations = [roi.stdev for roi in result.rois.values()]
    figure, (values, variation) = plt.subplots(
        2, 1, figsize=(7.8, 6), sharex=True, layout="constrained"
    )
    values.errorbar(
        names, means, yerr=deviations, fmt="o", color=_PLOT_GREEN, capsize=3,
        label="Mean and pixel standard deviation",
    )
    values.scatter(names, medians, color="black", marker="x", label="Median")
    values.set(ylabel=f"Pixel value ({result.value_units})")
    values.legend(fontsize=9)
    variation.bar(names, deviations, color=_PLOT_GREEN)
    variation.set(xlabel="ROI number", ylabel=f"Pixel standard deviation ({result.value_units})")
    for axis in (values, variation):
        axis.grid(axis="y", alpha=0.25)
    return _render_figure(
        "roi-intensities", "ROI intensities and pixel variation",
        "Analysis-slice disks. Pixel standard deviation describes the sampled values; it is not a scanner uniformity test.",
        figure,
    )


def _roi_figures(analyzer: ACRCT467, result: ACRCT467Result) -> list[_ReportFigure]:
    regions = list(result.rois.items())
    row_mm, column_mm = result.pixel_spacing_mm
    lower, upper = analyzer._overlay_window(result)
    image = analyzer.dicom_stack[result.origin_slice].array
    figures = []
    for closeups in (True, False):
        for start in range(0, len(regions), 6):
            group = regions[start : start + 6]
            figure, axes = plt.subplots(3, 2, figsize=(7.8, 9.0), layout="constrained")
            for axis, (name, roi) in zip(axes.flat, group):
                if closeups:
                    x_center, y_center = roi.center_px
                    half_width = 1.7 * roi.radius_mm / column_mm
                    half_height = 1.7 * roi.radius_mm / row_mm
                    left = max(0, floor(x_center - half_width))
                    right = min(image.shape[1], ceil(x_center + half_width) + 1)
                    top = max(0, floor(y_center - half_height))
                    bottom = min(image.shape[0], ceil(y_center + half_height) + 1)
                    axis.imshow(
                        image[top:bottom, left:right],
                        extent=(left - 0.5, right - 0.5, bottom - 0.5, top - 0.5),
                        cmap="gray", aspect=row_mm / column_mm, vmin=lower, vmax=upper,
                        interpolation="nearest",
                    )
                    analyzer._draw_sampling_disk(axis, roi, result.pixel_spacing_mm)
                    axis.set_title(f"{name} | Median {roi.median:.1f}; SD {roi.stdev:.1f}", fontsize=9)
                    axis.set_xlabel("Image column (px)", fontsize=8)
                    axis.set_ylabel("Image row (px)", fontsize=8)
                else:
                    axis.stairs(roi.histogram.counts, roi.histogram.bin_edges, fill=True, color=_PLOT_GREEN)
                    axis.axvline(roi.median, color="black", linestyle="--", linewidth=1, label="Median")
                    axis.legend(fontsize=7)
                    axis.set_title(name, fontsize=9)
                    axis.set_xlabel(f"Pixel value ({result.value_units})", fontsize=8)
                    axis.set_ylabel("Sampled pixels", fontsize=8)
                axis.xaxis.set_major_locator(MaxNLocator(5))
                axis.yaxis.set_major_locator(MaxNLocator(4, integer=True))
                axis.tick_params(labelsize=8)
            for axis in axes.flat[len(group) :]:
                axis.set_visible(False)

            span = f"{start + 1} to {start + len(group)}"
            if closeups:
                key = f"closeups-{start + 1}"
                title = f"ROI sampling close-ups: {span}"
                caption = (
                    f"Analysis-slice sampling disks. Median and SD are in {result.value_units} units. "
                    "Blue: image-supported boundary. Yellow: layout-only placement."
                )
            else:
                key = f"distributions-{start + 1}"
                title = f"ROI pixel-value distributions: {span}"
                caption = "Histograms use the measured disk bins and pixel counts. The dashed line marks the median."
            figures.append(_render_figure(key, title, caption, figure))
    return figures


def _slice_figures(analyzer: ACRCT467, result: ACRCT467Result) -> list[_ReportFigure]:
    row_mm, column_mm = result.pixel_spacing_mm
    lower, upper = analyzer._overlay_window(result)
    figures = []
    for start in range(0, len(result.slices), 9):
        group = result.slices[start : start + 9]
        figure, axes = plt.subplots(3, 3, figsize=(7.8, 8.5), layout="constrained")
        for axis, plane in zip(axes.flat, group):
            axis.imshow(
                analyzer.dicom_stack[plane.index].array, cmap="gray",
                aspect=row_mm / column_mm, vmin=lower, vmax=upper,
            )
            marker = " (analysis)" if plane.index == result.origin_slice else ""
            axis.set_title(f"Slice {plane.index}{marker}\nz = {plane.z_mm:g} mm", fontsize=9)
            axis.set_axis_off()
        for axis in axes.flat[len(group) :]:
            axis.set_visible(False)
        figures.append(
            _render_figure(
                f"slice-images-{group[0].index}",
                f"Axial scan images: {group[0].index} to {group[-1].index}",
                "Slice indices are zero-based. Images share the analysis overlay's grayscale window and physical aspect ratio.",
                figure,
            )
        )
    return figures


def _geometry_figure(result: ACRCT467Result) -> _ReportFigure:
    figure, (outline, placement) = plt.subplots(2, 1, figsize=(7.8, 6), layout="constrained")
    outline.plot(
        [plane.z_mm for plane in result.slices],
        [plane.outline_equivalent_diameter_mm for plane in result.slices],
        ".-", color=_PLOT_GREEN,
    )
    outline.axvline(result.origin_z_mm, color="gray", linestyle="--", linewidth=1)
    outline.set(
        title="Equivalent outline diameter by slice",
        xlabel="DICOM slice position z (mm)",
        ylabel="Diameter (mm)",
    )
    outline.ticklabel_format(axis="y", useOffset=False)
    placement.bar(
        [name.removeprefix("ROI ") for name in result.rois],
        [roi.placement_median_span for roi in result.rois.values()],
        color=_PLOT_GREEN,
    )
    placement.set(
        title="Median variation under disk placement shifts",
        xlabel="ROI number",
        ylabel=f"Median span ({result.value_units})",
    )
    for axis in (outline, placement):
        axis.grid(axis="y", alpha=0.25)
    return _render_figure(
        "outline-and-placement", "Outline and placement measurements",
        "Gaps indicate slices without a complete outline. Median span is the range across the nine placement shifts. "
        "Neither plot is an acceptance test.",
        figure,
    )


def _comparison_figure(result: ACRCT467Result) -> _ReportFigure:
    positions = {name: index for index, name in enumerate(result.rois)}
    labels = [name.removeprefix("ROI ") for name in positions]
    ticks = range(len(labels))
    figure, axes = plt.subplots(2, 2, figsize=(7.8, 7.8), layout="constrained")
    fields = (
        ("mean_difference", f"Mean difference ({result.value_units})", True),
        ("median_difference", f"Median difference ({result.value_units})", True),
        ("mean_cnr", "Mean CNR", False),
        ("median_cnr", "Median CNR", False),
    )
    for axis, (field, title, signed) in zip(axes.flat, fields, strict=True):
        matrix = np.full((len(labels), len(labels)), np.nan)
        for pair in result.pair_comparisons:
            value = getattr(pair, field)
            if value is not None:
                first, second = positions[pair.first_roi], positions[pair.second_roi]
                matrix[first, second] = value
                matrix[second, first] = -value if signed else value
        maximum = float(np.max(np.abs(matrix[np.isfinite(matrix)]), initial=0)) or 1.0
        palette = plt.get_cmap("RdBu_r" if signed else "viridis").with_extremes(bad="#E8EDEC")
        heatmap = axis.imshow(matrix, cmap=palette, vmin=-maximum if signed else 0, vmax=maximum)
        axis.set(
            title=title, xticks=ticks, yticks=ticks, xticklabels=labels, yticklabels=labels,
            xlabel="Second ROI", ylabel="First ROI",
        )
        axis.tick_params(labelsize=7, length=2)
        figure.colorbar(heatmap, ax=axis, shrink=0.8).ax.tick_params(labelsize=8)
    return _render_figure(
        "pairwise-figures", "ROI contrast and contrast-to-noise ratio",
        "Differences are second ROI minus first ROI. CNR is dimensionless. Gray cells are self-pairs or undefined values.",
        figure,
    )


def _report_figures(analyzer: ACRCT467, result: ACRCT467Result) -> list[_ReportFigure]:
    return [
        _render_figure(
            "overlay", "Analysed phantom image",
            "Numbered disks on the analysis slice. Blue: image-supported boundary. Yellow: layout-only placement.",
            analyzer.plot_analyzed_image(show=False),
        ),
        _intensity_figure(result),
        *_roi_figures(analyzer, result),
        _render_figure(
            "profiles", "Through-plane slice profiles",
            "Disk medians at fixed image coordinates. The dashed line marks the analysis slice.",
            analyzer.plot_slice_profiles(show=False),
        ),
        *_slice_figures(analyzer, result),
        _geometry_figure(result),
        _comparison_figure(result),
    ]


class _Chapter(Paragraph):
    def __init__(
        self,
        title: str,
        key: str,
        *,
        style: ParagraphStyle = _HEADING,
        toc_level: int | None = 0,
    ) -> None:
        super().__init__(escape(title), style)
        self.key = key
        self.toc_level = toc_level


class _ReportDocument(BaseDocTemplate):
    def afterFlowable(self, flowable: object) -> None:
        if isinstance(flowable, _Chapter):
            title = flowable.getPlainText()
            self.canv.bookmarkPage(flowable.key)
            self.canv.addOutlineEntry(title, flowable.key, level=flowable.toc_level or 0)
            if flowable.toc_level is not None:
                self.notify("TOCEntry", (flowable.toc_level, title, self.page, flowable.key))


def _contents() -> TableOfContents:
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle(
            "ACR contents", parent=_BODY, fontName="Helvetica-Bold", leading=14,
            spaceBefore=5, spaceAfter=3,
        ),
        ParagraphStyle(
            "ACR subcontents", parent=_BODY, fontSize=9, leading=12, leftIndent=12,
            spaceBefore=0, spaceAfter=2,
        ),
    ]
    toc.dotsMinLevel = 1
    return toc


def _report_theme(
    canvas: Canvas, doc: _ReportDocument, *, logo: Path | str | None
) -> None:
    width, height = doc.pageTemplate.pagesize
    canvas.saveState()
    canvas.setFillColor(_TEAL)
    if logo is None:
        canvas.setFont("Helvetica-Bold", 21)
        canvas.drawString(_MARGIN, height - 46.5, "Pro-ART")
        canvas.setFont("Helvetica", 5.7)
        canvas.drawString(_MARGIN, height - 56, "Applications for Radiological Technologies")
    else:
        canvas.drawImage(
            str(logo), _MARGIN, height - 57, width=103, height=28,
            mask="auto", preserveAspectRatio=True, anchor="w",
        )
    canvas.setFont("Helvetica-Bold", 10.5)
    canvas.drawString(_MARGIN + 119, height - 39, "CT Quality Assurance")
    canvas.drawString(_MARGIN + 119, height - 52, "Gammex 467 electron density phantom")
    canvas.setStrokeColor(_TEAL)
    canvas.line(_MARGIN, height - 62, width - _MARGIN, height - 62)
    canvas.setStrokeColor(_RULE)
    canvas.line(_MARGIN, 42, width - _MARGIN, 42)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(_MUTED)
    canvas.drawString(_MARGIN, 19, "Gammex 467 | CT quality assurance")
    canvas.drawRightString(width - _MARGIN, 19, f"Page {doc.page}")
    canvas.restoreState()


def _grade(passed: bool | None) -> str:
    return "Not evaluated" if passed is None else "PASS" if passed else "FAIL"


def _qa_rows(result: ACRCT467Result) -> list[tuple[str, str, str]]:
    origin = result.slices[result.origin_slice]
    thickness = origin.slice_thickness_mm
    diameter = origin.outline_equivalent_diameter_mm
    guide = result.guide_measurements
    accuracy_status = _grade(guide.ct_number_passed if guide else None)
    if guide is None:
        accuracy_note = "No confirmed material assignments or scanner-specific HU limits supplied."
    elif guide.ct_number_passed is not None:
        count = len(guide.ct_number_checks)
        within = sum(check.passed is True for check in guide.ct_number_checks.values())
        accuracy_note = f"{within} of {count} supplied rod references within tolerance (mean HU)."
    elif guide.ct_number_checks:
        accuracy_note = "Rod references supplied, but the scan does not declare HU on every slice."
    else:
        accuracy_note = (
            f"{len(guide.rod_statistics)} regions sampled with {guide.rod_sample_diameter_mm:g} mm disks. "
            "Confirmed rod positions and scanner-specific HU limits were not supplied."
        )
    return [
        ("CT number accuracy", accuracy_status, accuracy_note),
        (
            "CT number uniformity", "Not evaluated",
            "No designated uniformity module was measured. Insert differences are not a uniformity test.",
        ),
        (
            "High-contrast spatial resolution", "Not evaluated",
            "No line-pair or MTF target was measured.",
        ),
        (
            "Low-contrast resolution", "Not evaluated",
            "Pairwise contrast and CNR are descriptive; no low-contrast detectability target was scored.",
        ),
        (
            "Slice thickness", "DICOM only" if thickness is not None else "Not available",
            f"DICOM reports {thickness:g} mm on the analysis slice. No image-based thickness test."
            if thickness is not None else "No DICOM thickness or image-based measurement available.",
        ),
        (
            "Geometric accuracy", "Measurement only" if diameter is not None else "Not evaluated",
            f"Equivalent outline diameter: {diameter:.2f} mm. No independent reference was applied."
            if diameter is not None else "No outline measurement or independent reference available.",
        ),
        (
            "Pass/Fail", "Not determined",
            "The Model 467 guide gives no applicable acceptance limits. "
            "Any site comparisons grade only the supplied CT-number checks, not overall ACR QA.",
        ),
    ]


class _JsonTable(NamedTuple):
    columns: tuple[str, ...]
    rows: list[tuple[object, ...]]


def _json_table(
    identifiers: tuple[str, ...],
    fields: tuple[str, ...],
    records: Iterable[tuple[tuple[object, ...], Mapping[str, object] | None]],
) -> _JsonTable:
    return _JsonTable(
        identifiers + fields,
        [
            (*identity, *(record[field] if record is not None else None for field in fields))
            for identity, record in records
        ],
    )


def _format_json_report(report: Mapping[str, object]) -> str:
    encode = JSONEncoder(ensure_ascii=False, allow_nan=False).encode

    def format_value(value: object, indent: str) -> str:
        child = indent + "  "
        if isinstance(value, _JsonTable):
            rows = ",\n".join(f"{child}  {encode(row)}" for row in value.rows)
            rows_text = f"[\n{rows}\n{child}]" if rows else "[]"
            return (
                f'{{\n{child}"columns": {encode(value.columns)},'
                f'\n{child}"rows": {rows_text}\n{indent}}}'
            )
        if isinstance(value, Mapping) and value:
            members = ",\n".join(
                f"{child}{encode(key)}: {format_value(item, child)}"
                for key, item in value.items()
            )
            return f"{{\n{members}\n{indent}}}"
        return encode(value)

    return format_value(report, "") + "\n"


def _json_report(result: ACRCT467Result) -> str:
    scan = result.model_dump(mode="json")
    rois = scan.pop("rois")
    slices = scan.pop("slices")
    comparisons = scan.pop("pair_comparisons")
    checklist: dict[str, dict[str, object]] = {
        item: {"status": status, "observation": observation}
        for item, status, observation in _qa_rows(result)
    }
    origin = result.slices[result.origin_slice]
    guide = scan.get("guide_measurements")
    checklist["CT number accuracy"]["passed"] = guide["ct_number_passed"] if guide else None
    checklist["Pass/Fail"]["passed"] = None
    checklist["Slice thickness"]["dicom_nominal_thickness_mm"] = origin.slice_thickness_mm
    checklist["Geometric accuracy"]["outline_equivalent_diameter_mm"] = (
        origin.outline_equivalent_diameter_mm
    )

    statistics = (*(field for field, _ in _STATISTICS), "percentiles")
    roi_key = ("roi",)
    slice_key = ("slice_index",)
    if guide is not None:
        guide["rod_statistics"] = _json_table(
            roi_key,
            statistics,
            (((name,), sample) for name, sample in guide["rod_statistics"].items()),
        )
    return _format_json_report(
        {
            "qa_summary": checklist,
            "reference": {
                "manual_acceptance_limits": None,
                "notes": _GUIDE_NOTES,
                "supplied_nominal_rod_densities": _JsonTable(_DENSITY_COLUMNS, list(_SUPPLIED_DENSITIES)),
            },
            "scan": scan,
            "rois": {
                "geometry": _json_table(
                    roi_key,
                    ("center_px", "angle_deg", "distance_mm", "radius_mm", "placement_median_span"),
                    (((name,), roi) for name, roi in rois.items()),
                ),
                "disk_statistics": _json_table(
                    roi_key, statistics, (((name,), roi) for name, roi in rois.items()),
                ),
                "sphere_statistics": _json_table(
                    roi_key, statistics, (((name,), roi["sphere"]) for name, roi in rois.items()),
                ),
                "boundaries": _json_table(
                    roi_key,
                    ("center_px", "equivalent_diameter_mm", "center_offset_mm", "local_contrast"),
                    (((name,), roi["boundary"]) for name, roi in rois.items()),
                ),
                "disk_histograms": _json_table(
                    roi_key, ("bin_edges", "counts"),
                    (((name,), roi["histogram"]) for name, roi in rois.items()),
                ),
                "placement_sensitivity": _json_table(
                    roi_key, ("offset_mm", "pixel_count", "mean", "median", "stdev"),
                    (((name,), sample) for name, roi in rois.items() for sample in roi["placement_sensitivity"]),
                ),
            },
            "slices": {
                "geometry": _json_table(
                    slice_key,
                    (
                        "z_mm", "outline_center_px", "outline_equivalent_diameter_mm",
                        "slice_thickness_mm", "rescale_type", "rescale_slope", "rescale_intercept",
                    ),
                    (((plane["index"],), plane) for plane in slices),
                ),
                "acquisition": _json_table(
                    slice_key,
                    (
                        "image_type", "convolution_kernel", "tube_voltage_kvp", "tube_current_ma",
                        "exposure_mas", "ctdi_vol_mgy", "reconstruction_diameter_mm",
                    ),
                    (((plane["index"],), plane["acquisition"]) for plane in slices),
                ),
                "roi_statistics": _json_table(
                    slice_key + roi_key, statistics,
                    (((plane["index"], name), roi) for plane in slices for name, roi in plane["rois"].items()),
                ),
            },
            "pair_comparisons": _json_table(
                (),
                (
                    "first_roi", "second_roi", "mean_difference", "median_difference",
                    "pooled_stdev", "mean_cnr", "median_cnr",
                ),
                (((), comparison) for comparison in comparisons),
            ),
        }
    )


def _cover(result: ACRCT467Result, width: float, *, detailed: bool) -> list[Flowable]:
    title = f"{result.phantom_model} CT QA {'Report' if detailed else 'Summary'}"
    return [
        _Chapter(title, "overview", style=_TITLE, toc_level=None),
        _cell("Overall Pass/Fail: Not determined", _SECTION),
        _table(
            ("Test information", "Details"),
            [
                ("Date of analysis", result.date_of_analysis.strftime("%d %B %Y, %H:%M:%S")),
                ("Analysis software version", result.pylinac_version),
                ("Phantom model", result.phantom_model),
                ("Number of scan images", result.num_images),
            ],
            width,
            weights=(0.8, 1.2),
            label_columns=2,
            padding=4,
        ),
        _cell("QA measurements", _SECTION),
        _table(
            ("QA item", "Status", "Observation"),
            _qa_rows(result),
            width,
            weights=(1.35, 1, 2.85),
            label_columns=3,
            padding=4,
        ),
        _cell("Series and sampling", _SECTION),
        _table(
            ("Field", "Value"),
            [
                ("Analysis slice (zero-based)", f"{result.origin_slice}, z = {result.origin_z_mm:g} mm"),
                ("Regions sampled", len(result.rois)),
                ("Image-supported boundaries", sum(roi.boundary is not None for roi in result.rois.values())),
                ("Pixel value units", result.value_units),
            ],
            width,
            weights=(0.8, 1.2),
            label_columns=2,
            padding=4,
        ),
    ]


def _guide_reference(result: ACRCT467Result, width: float) -> list[Flowable]:
    guide = result.guide_measurements
    if guide is None:
        return []
    story: list[Flowable] = [
        PageBreak(),
        _Chapter("Gammex 467 reference and checks", "guide-reference"),
        _cell("Source: Model 467 User's Guide (006328-00-04), Tables 1-2 and Collecting Data.", _BODY),
        _cell(guide.guide_url, _CAPTION),
        _cell(
            f"Guide sampling: {guide.rod_sample_diameter_mm:g} mm disks at the automatically "
            f"registered layout positions unless overridden. Units: {result.value_units}. "
            f"Nominal caliper-hole spacing: {guide.nominal_caliper_spacing_mm:g} mm (not measured).",
            _BODY,
        ),
        *[_cell(note, _BODY) for note in _GUIDE_NOTES],
        _cell("Supplied nominal rod densities", _SECTION),
        _table(
            ("Rod material", "Relative electron density", "Physical density (g/cm3)"),
            _SUPPLIED_DENSITIES,
            width,
            weights=(1.8, 1, 1),
            padding=4,
        ),
    ]
    if guide.ct_number_checks:
        story.extend(
            (
                PageBreak(),
                _Chapter("Site CT-number comparisons", "ct-number-checks"),
                _cell(
                    "Only supplied references are evaluated. A mean HU deviation within the supplied tolerance passes.",
                    _BODY,
                ),
                _table(
                    ("ROI / material / source", "Mean HU", "Reference HU", "Tolerance HU", "Difference HU", "Status"),
                    [
                        (
                            f"{name}: {check.reference.material}\n{check.reference.source}",
                            guide.rod_statistics[name].mean if result.value_units == "HU" else None,
                            check.reference.expected_hu,
                            check.reference.tolerance_hu,
                            check.difference_hu,
                            _grade(check.passed),
                        )
                        for name, check in guide.ct_number_checks.items()
                    ],
                    width,
                    weights=(2, 1.15, 0.8, 0.8, 1.15, 1),
                    padding=3,
                ),
            )
        )
    return story


def _series_details(result: ACRCT467Result, width: float) -> list[Flowable]:
    facts = _facts(
        (
            ("Analysis date", result.date_of_analysis.isoformat()),
            ("Pylinac version", result.pylinac_version),
            ("Origin slice (zero-based)", result.origin_slice),
            ("Origin z position (mm)", result.origin_z_mm),
            ("Image matrix (rows, columns)", result.image_shape_px),
            ("Phantom center (x, y pixels)", result.center_px),
            ("Pixel spacing (row, column mm)", result.pixel_spacing_mm),
            ("Slice spacing (mm)", result.slice_spacing_mm),
            ("Reference angle (deg)", result.reference_angle_deg),
            (
                "Angle reference method",
                result.reference_angle_method.replace("_", " ").capitalize(),
            ),
            ("Sphere sample slice indices", result.sphere_slice_indices),
            ("Sphere coverage limitation", result.sphere_unavailable_reason or "None"),
        ),
        width,
    )
    story: list[Flowable] = [
        _Chapter("Detailed measurements", "details"),
        _Chapter("Series geometry and analysis settings", "series", style=_SECTION, toc_level=1),
        facts,
        _cell("Measurement limitations", _SECTION),
        *[_cell(f"- {note}", _BODY) for note in result.limitations],
    ]
    if result.warnings:
        story.append(_cell("Analysis warnings", _SECTION))
        story.extend(_cell(warning, _BODY) for warning in result.warnings)
    else:
        story.append(_cell("Analysis warnings: none.", _BODY))
    return story


def _region_overview(result: ACRCT467Result, width: float) -> list[Flowable]:
    return [
        CondPageBreak(90),
        _Chapter("Selected regions at a glance", "region-summary", toc_level=1),
        _cell(
            f"Measurements at slice {result.origin_slice}, z = {result.origin_z_mm:g} mm. "
            f"Intensity units: {result.value_units}. SD = population standard deviation; "
            "IQR = interquartile range.",
            _BODY,
        ),
        _table(
            ("Region", "Boundary evidence", "Pixels", "Mean", "Median", "SD"),
            [
                (
                    name, "Image-supported" if roi.boundary is not None else "Layout only",
                    roi.pixel_count, roi.mean, roi.median, roi.stdev,
                )
                for name, roi in result.rois.items()
            ],
            width,
            weights=(0.8, 1.55, 0.8, 1.25, 1, 1.25),
            label_columns=2,
        ),
    ]


def _sample_tables(
    identifiers: tuple[str, str],
    samples: Sequence[tuple[str | int, str, ACRCT467Statistics]],
    width: float,
) -> list[Flowable]:
    standard_fields = _STATISTICS[:-2]
    percentiles = sorted({level for _, _, sample in samples for level in sample.percentiles})
    return [
        *_table_heading("Sample statistics"),
        _table(
            (*identifiers, *(label for _, label in standard_fields)),
            [
                (first, second, *(getattr(sample, field) for field, _ in standard_fields))
                for first, second, sample in samples
            ],
            width,
            weights=(0.6, 0.75, 0.7, 1.4, 0.8, 1.4, 1.4, 0.8, 0.8, 0.8, 0.95),
            label_columns=2,
            padding=2,
        ),
        *_table_heading("Sample percentiles and distribution shape"),
        _table(
            (*identifiers, *(f"P{level}" for level in percentiles), "Skewness", "Excess kurtosis"),
            [
                (
                    first,
                    second,
                    *(sample.percentiles.get(level) for level in percentiles),
                    sample.skewness,
                    sample.excess_kurtosis,
                )
                for first, second, sample in samples
            ],
            width,
            weights=(0.65, 0.75, *(1 for _ in percentiles), 1.2, 1.2),
            label_columns=2,
            padding=2,
        ),
    ]


def _region_details(result: ACRCT467Result, width: float) -> list[Flowable]:
    samples = [
        (name, sample_type, sample)
        for name, roi in result.rois.items()
        for sample_type, sample in (("Disk", roi), ("Sphere", roi.sphere))
        if sample is not None
    ]
    if result.guide_measurements is not None:
        samples.extend(
            (name, "10 mm guide disk", sample)
            for name, sample in result.guide_measurements.rod_statistics.items()
        )
    headings = ("Bin", "Lower edge", "Upper edge", "Pixel count")
    bins = []
    for name, roi in result.rois.items():
        histogram = roi.histogram
        entries = [
            (index, lower, upper, count)
            for index, (lower, upper, count) in enumerate(
                zip(histogram.bin_edges[:-1], histogram.bin_edges[1:], histogram.counts, strict=True),
                start=1,
            )
        ]
        for start in range(0, len(entries), 2):
            right = entries[start + 1] if start + 1 < len(entries) else ("",) * 4
            bins.append((name, *entries[start], *right))

    return [
        CondPageBreak(90),
        _Chapter("ROI geometry and statistics", "region-details", toc_level=1),
        _table(
            (
                "ROI", "Disk center (x, y px)", "Radius (mm)", "Angle (deg)",
                "Distance from center (mm)", "Placement median span", "Sphere sample",
            ),
            [
                (
                    name, roi.center_px, roi.radius_mm, roi.angle_deg, roi.distance_mm,
                    roi.placement_median_span, "Available" if roi.sphere is not None else None,
                )
                for name, roi in result.rois.items()
            ],
            width,
            weights=(0.6, 2, 0.8, 1, 1.05, 1.25, 1.05),
            padding=2,
        ),
        *_table_heading("Boundary evidence"),
        _table(
            (
                "ROI", "Evidence", "Boundary center (x, y px)", "Equivalent diameter (mm)",
                "Center offset (mm)", "Local contrast",
            ),
            [
                (
                    name, "Image-supported", boundary.center_px, boundary.equivalent_diameter_mm,
                    boundary.center_offset_mm, boundary.local_contrast,
                ) if boundary is not None else (name, "Layout only", None, None, None, None)
                for name, roi in result.rois.items()
                for boundary in (roi.boundary,)
            ],
            width,
            weights=(0.6, 1.2, 2, 1.2, 1.2, 1.2),
            label_columns=2,
            padding=2,
        ),
        *_sample_tables(("ROI", "Sample"), samples, width),
        CondPageBreak(90),
        _Chapter("ROI placement sensitivity", "placement", toc_level=1),
        _table(
            ("ROI", "X shift (mm)", "Y shift (mm)", "Pixels", "Mean", "Median", "SD"),
            [
                (name, *sample.offset_mm, sample.pixel_count, sample.mean, sample.median, sample.stdev)
                for name, roi in result.rois.items()
                for sample in roi.placement_sensitivity
            ],
            width,
            weights=(0.7, 1, 1, 0.7, 1.3, 1, 1.3),
            padding=2,
        ),
        CondPageBreak(90),
        _Chapter("Disk histogram bin data", "histograms", toc_level=1),
        _cell("Bins are listed left to right in each row. Edges use the reported intensity units.", _BODY),
        _table(
            ("ROI", *headings, *headings),
            bins,
            width,
            weights=(0.7, *((0.48, 1.35, 1.35, 0.65) * 2)),
            padding=2,
        ),
    ]


def _slice_details(result: ACRCT467Result, width: float) -> list[Flowable]:
    return [
        CondPageBreak(90),
        _Chapter("Slice geometry and acquisition", "slice-details", toc_level=1),
        _cell("Slice indices are zero-based. Thickness values are nominal DICOM values.", _BODY),
        _table(
            (
                "Slice", "Z position (mm)", "Outline center (x, y px)", "Equivalent diameter (mm)",
                "DICOM thickness (mm)", "Rescale slope", "Rescale intercept", "Rescale type",
            ),
            [
                (
                    plane.index, plane.z_mm, plane.outline_center_px,
                    plane.outline_equivalent_diameter_mm, plane.slice_thickness_mm,
                    plane.rescale_slope, plane.rescale_intercept, plane.rescale_type,
                )
                for plane in result.slices
            ],
            width,
            weights=(0.55, 0.9, 2, 1.15, 1.05, 0.85, 0.85, 1.05),
            padding=2,
        ),
        *_table_heading("DICOM acquisition and reconstruction"),
        _table(
            (
                "Slice", "Image type", "Convolution kernel", "Tube voltage (kVp)",
                "Tube current (mA)", "Exposure (mAs)", "CTDIvol (mGy)", "Reconstruction diameter (mm)",
            ),
            [
                (plane.index, *plane.acquisition.model_dump().values())
                for plane in result.slices
            ],
            width,
            weights=(0.55, 1.8, 1.3, 0.9, 0.9, 0.95, 0.9, 1.2),
            label_columns=3,
            padding=2,
        ),
        CondPageBreak(90),
        _Chapter("Fixed-coordinate slice samples", "slice-samples", toc_level=1),
        _cell("Slice and ROI identify the same disk position on each image.", _BODY),
        *_sample_tables(
            ("Slice", "ROI"),
            [(plane.index, name, roi) for plane in result.slices for name, roi in plane.rois.items()],
            width,
        ),
    ]


def _write_report(
    filename: str | BytesIO,
    result: ACRCT467Result,
    figures: Sequence[_ReportFigure],
    *,
    detailed: bool,
    logo: Path | str | None,
) -> None:
    doc = _ReportDocument(
        filename,
        pagesize=A4,
        title=f"{result.phantom_model} CT QA {'Detailed Report' if detailed else 'Summary'}",
    )
    theme = partial(_report_theme, logo=logo)
    for template, page_size in (("portrait", A4), ("tables", _PAGE_SIZE)):
        width, height = page_size
        frame = Frame(_MARGIN, _BOTTOM_MARGIN, width - 2 * _MARGIN, height - _TOP_MARGIN - _BOTTOM_MARGIN)
        doc.addPageTemplates(PageTemplate(id=template, frames=frame, onPage=theme, pagesize=page_size))

    width = A4[0] - 2 * _MARGIN - 12
    story = _cover(result, width, detailed=detailed)
    story.extend((PageBreak(), _Chapter("Contents", "contents", toc_level=None), _contents()))
    for figure in figures:
        story.extend(
            (
                PageBreak(),
                _Chapter(figure.title, figure.key),
                Image(
                    figure.stream,
                    width=width,
                    height=A4[1] - _TOP_MARGIN - _BOTTOM_MARGIN - 95,
                    kind="proportional",
                ),
                _cell(figure.caption, _CAPTION),
            )
        )
    story.extend(_guide_reference(result, width))
    if detailed:
        width = _PAGE_SIZE[0] - 2 * _MARGIN - 12
        story.extend((NextPageTemplate("tables"), PageBreak(), *_series_details(result, width)))
        story.extend(_region_overview(result, width))
        story.extend(_region_details(result, width))
        story.extend(_slice_details(result, width))
        story.extend(
            (
                CondPageBreak(90),
                _Chapter("Pairwise contrast and CNR", "pairs", toc_level=1),
                _cell(
                    f"Signed intensity differences are second ROI minus first ROI ({result.value_units}). "
                    "Contrast-to-noise ratio (CNR) divides the absolute difference by pooled population SD.",
                    _BODY,
                ),
                _pairwise_table(result.pair_comparisons, width),
            )
        )
    doc.multiBuild(story)