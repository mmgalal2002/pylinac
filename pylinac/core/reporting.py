"""Paginated, data-first PDF reports, separate from the legacy PDF canvas."""

from __future__ import annotations

import io
import json
import math
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import BinaryIO
from xml.sax.saxutils import escape

import numpy as np
from PIL import Image as PILImage
from pydantic import BaseModel, ConfigDict, Field as ModelField
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, Line, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfdoc
from reportlab.pdfbase.pdfmetrics import getFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Flowable,
    Image,
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

CONTENT_WIDTH = A4[0] - 3.6 * cm - 12


class ReportBranding(BaseModel):
    """Full visual identity for a detailed medical physics report.

    Parameters
    ----------
    name : str
        Report owner shown in the page header and PDF author metadata.
    report_title : str, optional
        Custom title. The analysis name is used when no title is supplied.
    header_text, footer_text : str
        Page header and footer wording. A default footer uses the report owner.
    body_font, heading_font : str
        ReportLab font names. Custom fonts must be registered before publishing.
    font_size : float
        Base size, between 9 and 14 points. Other text sizes follow this value.
    primary_color, text_color, muted_color, background_color : str
        Brand accent, main text, supporting text and page colours.
    table_background_color, table_header_text_color, border_color : str
        Alternating row, table-header text and divider colours.
    chart_color, failure_color, warning_color : str
        Measurement, failed-result and warning colours. Measurements use the
        primary colour when no separate chart colour is supplied.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = "Pylinac"
    report_title: str | None = None
    header_text: str = "Medical physics quality assurance"
    footer_text: str | None = None
    body_font: str = "Helvetica"
    heading_font: str = "Helvetica-Bold"
    font_size: float = ModelField(default=10, ge=9, le=14)
    primary_color: str = "#20864B"
    text_color: str = "#20272B"
    muted_color: str = "#52615A"
    background_color: str = "#FFFFFF"
    table_background_color: str = "#F3F6F5"
    table_header_text_color: str = "#FFFFFF"
    border_color: str = "#D7DFDC"
    chart_color: str | None = None
    failure_color: str = "#B52E38"
    warning_color: str = "#9B6507"


@dataclass(frozen=True)
class ReportField:
    """Clinical wording for a result without changing its stored data.

    Parameters
    ----------
    label : str
        Human-readable measurement name, including verified units.
    explanation : str
        Short clinical explanation, rather than a description of Python types.
    numbered : bool
        Display a stored zero-based integer identifier as a one-based number.
    missing_label : str
        Wording used when the measurement is null.
    """

    label: str
    explanation: str = ""
    numbered: bool = False
    missing_label: str = "Not reported"


@dataclass(frozen=True)
class ReportTableLabels:
    """Human labels for complete measurement tables.

    Parameters
    ----------
    row_heading, series_heading, value_heading : str
        Names used for measurement identifiers, ordered measurements and values.
    row_labels, column_labels : mapping
        Explicit clinical names for stored identifiers and submeasurements.
    """

    row_heading: str = "Measurement"
    series_heading: str = "Measurement"
    value_heading: str = "Value"
    row_labels: Mapping[str, str] = field(default_factory=dict)
    column_labels: Mapping[str, str] = field(default_factory=dict)


class _SectionMarker(Flowable):
    def __init__(self, title: str, key: str, level: int) -> None:
        super().__init__()
        self.title = title
        self.key = key
        self.level = level
        self.keepWithNext = True

    def draw(self) -> None:
        pass


class _ReportTemplate(SimpleDocTemplate):
    def afterFlowable(self, flowable: Flowable) -> None:
        if isinstance(flowable, _SectionMarker):
            self.canv.bookmarkPage(flowable.key)
            self.canv.addOutlineEntry(flowable.title, flowable.key, flowable.level)
            self.notify(
                "TOCEntry",
                (flowable.level, escape(flowable.title), self.page, flowable.key),
            )


def _attach_json(canvas: Canvas, content: bytes) -> None:
    document = canvas._doc
    stream = pdfdoc.PDFStream(
        dictionary=pdfdoc.PDFDictionary(
            {
                "Type": pdfdoc.PDFName("EmbeddedFile"),
                "Params": pdfdoc.PDFDictionary({"Size": len(content)}),
            }
        ),
        content=content,
        filters=[pdfdoc.PDFZCompress],
    )
    stream_reference = document.Reference(stream)
    specification = pdfdoc.PDFDictionary(
        {
            "Type": pdfdoc.PDFName("Filespec"),
            "F": pdfdoc.PDFString("results.json"),
            "UF": pdfdoc.PDFString("results.json"),
            "Desc": pdfdoc.PDFString("The complete results snapshot used in this report"),
            "EF": pdfdoc.PDFDictionary({"F": stream_reference, "UF": stream_reference}),
        }
    )
    name_tree = pdfdoc.PDFDictionary(
        {
            "Names": pdfdoc.PDFArray(
                [pdfdoc.PDFString("results.json"), document.Reference(specification)]
            )
        }
    )
    document.Catalog.Names = pdfdoc.PDFDictionary({"EmbeddedFiles": name_tree})


def _label(name: str) -> str:
    words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name).replace("_", " ").split()
    terms = {
        "cax": "central axis",
        "mlc": "multileaf collimator",
        "roi": "region of interest",
        "mtf": "modulation transfer function",
        "snr": "signal-to-noise ratio",
        "cnr": "contrast-to-noise ratio",
        "mm": "(mm)",
        "pct": "(%)",
        "hu": "CT number (HU)",
        "x": "X component",
        "y": "Y component",
        "z": "Z component",
    }
    text = " ".join(terms.get(word.lower(), word) for word in words)
    return text[:1].upper() + text[1:]


def _value(value: object) -> str:
    if value is None:
        return "Not reported"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        return format(value, ".8g")
    if isinstance(value, dict):
        return "; ".join(f"{_label(str(key))}: {_value(child)}" for key, child in value.items()) or "No recorded items"
    if isinstance(value, list):
        return "; ".join(_value(child) for child in value) or "No recorded items"
    return str(value)


def _leaves(
    value: object, path: tuple[str | int, ...]
) -> Iterator[tuple[tuple[str | int, ...], object]]:
    if isinstance(value, dict) and value:
        for key, child in value.items():
            yield from _leaves(child, path + (str(key),))
    elif isinstance(value, list) and value:
        for index, child in enumerate(value):
            yield from _leaves(child, path + (index,))
    else:
        yield path, value


class DetailedReport:
    """Build a standalone PDF from one result snapshot and analysis artifacts.

    Parameters
    ----------
    title : str
        Analysis name used in the report.
    results : BaseModel
        Already analysed results. The model is serialized once without aliases
        or exclusions; report generation does not rerun analysis.
    context : mapping, optional
        Input identity and analysis settings supplied by the analysis adapter.
    metadata : mapping, optional
        User-supplied report metadata.
    notes : str or sequence of str, optional
        User-supplied notes.
    logo : Path or str, optional
        Local custom logo. The default logo is used only when packaged locally.
    fields : mapping, optional
        Clinical wording keyed by structured field components. A ``"*"``
        component matches a measurement identifier or list entry.
    table_labels : mapping, optional
        Clinical row and column names for each top-level measurement collection.
    branding : ReportBranding or mapping, optional
        Full report identity. Defaults to the Pylinac clinical report theme.
    """

    def __init__(
        self,
        title: str,
        results: BaseModel,
        context: Mapping[str, object] | None = None,
        metadata: Mapping[str, object] | None = None,
        notes: str | Sequence[str] | None = None,
        logo: Path | str | None = None,
        fields: Mapping[tuple[str, ...], ReportField] | None = None,
        table_labels: Mapping[str, ReportTableLabels] | None = None,
        branding: ReportBranding | Mapping[str, object] | None = None,
    ) -> None:
        self.branding = branding if isinstance(branding, ReportBranding) else ReportBranding.model_validate(branding or {})
        self.title = self.branding.report_title or title
        self._primary = colors.toColor(self.branding.primary_color)
        self._ink = colors.toColor(self.branding.text_color)
        self._muted = colors.toColor(self.branding.muted_color)
        self._paper = colors.toColor(self.branding.background_color)
        self._row_background = colors.toColor(self.branding.table_background_color)
        self._header_ink = colors.toColor(self.branding.table_header_text_color)
        self._line = colors.toColor(self.branding.border_color)
        self._chart = colors.toColor(self.branding.chart_color or self.branding.primary_color)
        self._failure = colors.toColor(self.branding.failure_color)
        self._warning = colors.toColor(self.branding.warning_color)
        for font in (self.branding.body_font, self.branding.heading_font):
            try:
                getFont(font)
            except KeyError as error:
                raise ValueError(f"Register the report font '{font}' before publishing.") from error
        self.results_json = results.model_dump_json()
        values = json.loads(self.results_json)
        if not isinstance(values, dict):
            raise TypeError("Detailed reports require a JSON object of results.")
        self.values: dict[str, object] = values
        self._fields = type(results).model_fields
        self._presentation = {
            ("pylinac_version",): ReportField("Analysis software version"),
            ("date_of_analysis",): ReportField("Date of analysis"),
            ("warnings",): ReportField("Analysis warnings"),
            ("passed",): ReportField("Overall test result"),
            **(fields or {}),
        }
        self._table_labels = table_labels or {}
        self._context = context or {}
        self._metadata = metadata or {}
        self._notes = notes
        self._story: list[Flowable] = []
        self._section_id = 0
        self._styles = getSampleStyleSheet()
        font_size = self.branding.font_size
        for name in ("Normal", "BodyText", "Heading1", "Heading2", "Title"):
            self._styles[name].textColor = self._ink
            self._styles[name].fontName = self.branding.body_font
            self._styles[name].fontSize = font_size
            self._styles[name].leading = font_size * 1.4
        for name in ("Heading1", "Heading2", "Title"):
            self._styles[name].fontName = self.branding.heading_font
            self._styles[name].textColor = self._primary
        self._styles["Title"].fontSize = font_size * 2.3
        self._styles["Title"].leading = font_size * 2.8
        self._styles["Title"].alignment = 0
        self._styles["Heading1"].fontSize = font_size * 1.6
        self._styles["Heading1"].leading = font_size * 2
        self._styles["Heading1"].spaceAfter = 10
        self._styles["Heading2"].fontSize = font_size * 1.2
        self._styles["Heading2"].leading = font_size * 1.6
        self._styles["Heading2"].spaceBefore = 12
        self._styles.add(
            ParagraphStyle(
                "ReportCell",
                fontName=self.branding.body_font,
                fontSize=font_size - 1,
                leading=(font_size - 1) * 1.35,
                textColor=self._ink,
                splitLongWords=True,
            )
        )
        self._styles.add(
            ParagraphStyle(
                "ReportHeader",
                parent=self._styles["ReportCell"],
                fontName=self.branding.heading_font,
                textColor=self._header_ink,
            )
        )
        self._styles.add(
            ParagraphStyle(
                "ReportCaption",
                parent=self._styles["BodyText"],
                fontSize=font_size - 1,
                leading=(font_size - 1) * 1.35,
                textColor=self._muted,
                spaceBefore=8,
            )
        )
        self._styles.add(
            ParagraphStyle(
                "ReportPageHeader",
                fontName=self.branding.heading_font,
                fontSize=font_size,
                leading=font_size * 1.4,
                textColor=self._primary,
            )
        )
        self._styles.add(
            ParagraphStyle(
                "ReportPageFooter",
                fontName=self.branding.body_font,
                fontSize=font_size - 2,
                leading=(font_size - 2) * 1.3,
                textColor=self._muted,
            )
        )
        self._logo = Path(logo) if logo is not None else None
        if self._logo is not None and not self._logo.is_file():
            raise FileNotFoundError(f"Report logo does not exist: {self._logo}")
        if self._logo is None and self.branding.name == "Pylinac":
            packaged = Path(__file__).parent.parent / "files" / "Pylinac-GREEN.png"
            if packaged.is_file():
                self._logo = packaged
        self._page_header = self._paragraph(
            "\n".join(text for text in (self.branding.name, self.branding.header_text) if text),
            "ReportPageHeader",
        )
        self._header_x = 6.0 * cm if self._logo is not None else 1.8 * cm
        header_width = A4[0] - self._header_x - 1.8 * cm
        _, self._header_height = self._page_header.wrap(header_width, A4[1])
        self._top_margin = max(2.7 * cm, self._header_height + 1.5 * cm)
        footer_text = self.branding.footer_text
        if footer_text is None:
            footer_text = f"{self.branding.name} | Medical physics quality assurance"
        self._page_footer = self._paragraph(footer_text, "ReportPageFooter")
        _, self._footer_height = self._page_footer.wrap(CONTENT_WIDTH - 65, A4[1])
        self._bottom_margin = max(2.0 * cm, self._footer_height + 1.5 * cm)
        if self._top_margin + self._bottom_margin > A4[1] - 8 * cm:
            raise ValueError("The report header and footer leave too little space for measurements.")

    def _paragraph(self, text: object, style: str = "BodyText") -> Paragraph:
        return Paragraph(
            escape(str(text)).replace("\n", "<br/>"), self._styles[style]
        )

    def _section(self, title: str, level: int = 0) -> list[Flowable]:
        key = f"section-{self._section_id}"
        self._section_id += 1
        return [
            _SectionMarker(title, key, level),
            self._paragraph(title, "Heading1" if level == 0 else "Heading2"),
        ]

    def _field_title(self, key: str) -> str:
        presentation = self._presentation.get((key,))
        if presentation is not None:
            return presentation.label
        field = self._fields.get(key)
        return _label((field.title if field is not None else None) or key)

    def _field_presentation(self, path: tuple[str | int, ...]) -> ReportField | None:
        exact = tuple(str(part) for part in path)
        presentation = self._presentation.get(exact)
        if presentation is not None or len(path) < 2:
            return presentation
        wildcard = (str(path[0]),) + ("*",) * (len(path) - 2) + (str(path[-1]),)
        return self._presentation.get(wildcard)

    def _measurement_label(self, path: tuple[str | int, ...]) -> str:
        presentation = self._field_presentation(path)
        if presentation is not None:
            return presentation.label
        labels = self._table_labels.get(str(path[0]), ReportTableLabels())
        parts = path[1:] or path
        return ": ".join(
            f"{labels.series_heading} {part + 1}"
            if isinstance(part, int)
            else labels.row_labels.get(part, _label(part))
            for part in parts
        )

    def _measurement_value(self, value: object, path: tuple[str | int, ...]) -> str:
        presentation = self._field_presentation(path)
        if value is None:
            return presentation.missing_label if presentation is not None else "Not reported"
        if (
            presentation is not None
            and presentation.numbered
            and isinstance(value, int)
            and not isinstance(value, bool)
        ):
            return str(value + 1)
        if path == ("passed",) and isinstance(value, bool):
            return "Within tolerance" if value else "Outside tolerance"
        if path == ("date_of_analysis",) and isinstance(value, str):
            try:
                return datetime.fromisoformat(value).strftime("%d %B %Y, %H:%M:%S %Z").strip()
            except ValueError:
                pass
        return _value(value)

    def _table(
        self,
        headings: Sequence[str],
        rows: Iterable[Sequence[object]],
        widths: Sequence[float],
    ) -> LongTable:
        table_rows = [[self._paragraph(name, "ReportHeader") for name in headings]]
        table_rows.extend(
            [
                self._paragraph(_value(value), "ReportCell")
                for value in row
            ]
            for row in rows
        )
        try:
            table = LongTable(
                table_rows,
                colWidths=list(widths),
                repeatRows=1,
                splitInRow=1,
                hAlign="LEFT",
            )
        except TypeError as error:
            raise RuntimeError(
                "Detailed PDF reports need ReportLab table row splitting support. "
                "Please update ReportLab, or use the existing detailed=False option."
            ) from error
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), self._primary),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [self._paper, self._row_background]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.5, self._primary),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.25, self._line),
                ]
            )
        )
        return table

    def add_table(
        self,
        title: str,
        headings: Sequence[str],
        rows: Iterable[Sequence[object]],
        widths: Sequence[float] | None = None,
    ) -> None:
        """Add a labelled, automatically paginated analysis table."""
        self._story.extend(self._section(title))
        self._story.append(
            self._table(
                headings,
                rows,
                widths or [CONTENT_WIDTH / len(headings)] * len(headings),
            )
        )

    def add_artifact(self, title: str, image: bytes, caption: str) -> None:
        """Add an image artifact on its own page without changing its proportions."""
        with PILImage.open(io.BytesIO(image)) as source:
            image_width, image_height = source.size
        scale = min(CONTENT_WIDTH / image_width, 18 * cm / image_height)
        self._story.append(PageBreak())
        self._story.extend(self._section(title))
        self._story.extend(
            [
                Image(
                    io.BytesIO(image),
                    width=image_width * scale,
                    height=image_height * scale,
                    hAlign="CENTER",
                ),
                self._paragraph(caption, "ReportCaption"),
            ]
        )

    def add_bar_chart(
        self,
        title: str,
        categories: Sequence[str],
        values: Sequence[float],
        value_label: str,
        category_label: str,
        *,
        limits: Sequence[tuple[str, float]] = (),
        highlighted: Sequence[str] = (),
        caption: str = "",
        whole_values: bool = False,
    ) -> None:
        """Add paged vector charts with labelled axes and supplied tolerance lines.

        Parameters
        ----------
        title : str
            Section title.
        categories : sequence of str
            Original measurement identifiers in display order.
        values : sequence of float
            Finite measurements corresponding to the identifiers.
        value_label, category_label : str
            Axis labels, including units where known.
        limits : sequence of (str, float)
            Named analysis limits drawn without recalculating pass/fail status.
        highlighted : sequence of str
            Identifiers already classified as failed by the analysis.
        caption : str
            Measurement context displayed below the chart.
        whole_values : bool
            Use integer ticks for counts.
        """
        if len(categories) != len(values) or not values:
            raise ValueError(f"Chart '{title}' needs matching, nonempty measurements.")
        if any(not math.isfinite(value) for value in values) or any(
            not math.isfinite(value) for _, value in limits
        ):
            raise ValueError(f"Chart '{title}' contains a non-finite measurement.")
        limit_values = [value for _, value in limits]
        lower = min(0.0, *values, *limit_values)
        upper = max(0.0, *values, *limit_values)
        span = upper - lower or 1.0
        minimum = lower - span * 0.08 if lower < 0 else 0.0
        maximum = upper + span * 0.12
        page_count = math.ceil(len(values) / 20)
        failed = set(highlighted)
        for page_index, start in enumerate(range(0, len(values), 20)):
            page_categories = list(categories[start : start + 20])
            page_values = list(values[start : start + 20])
            drawing = Drawing(CONTENT_WIDTH, 345)
            chart = VerticalBarChart()
            chart.x = 54
            chart.y = 85
            chart.width = CONTENT_WIDTH - 68
            chart.height = 200
            chart.data = [page_values]
            chart.groupSpacing = 4
            chart.barSpacing = 0
            chart.valueAxis.valueMin = minimum
            chart.valueAxis.valueMax = maximum
            chart.valueAxis.visibleGrid = True
            chart.valueAxis.gridStrokeColor = self._line
            chart.valueAxis.strokeColor = self._ink
            chart.valueAxis.labels.fillColor = self._ink
            chart.valueAxis.labels.fontName = self.branding.body_font
            chart.valueAxis.labels.fontSize = self.branding.font_size - 1
            chart.valueAxis.labelTextFormat = "%d" if whole_values else "%.3g"
            if whole_values:
                chart.valueAxis.valueStep = max(1, math.ceil((maximum - minimum) / 5))
            chart.categoryAxis.categoryNames = [
                f"{name} *" if name in failed else name for name in page_categories
            ]
            chart.categoryAxis.strokeColor = self._ink
            chart.categoryAxis.labels.fillColor = self._ink
            chart.categoryAxis.labels.fontName = self.branding.body_font
            chart.categoryAxis.labels.fontSize = self.branding.font_size - 1
            chart.categoryAxis.labels.angle = 45
            chart.categoryAxis.labels.boxAnchor = "ne"
            chart.categoryAxis.labels.dy = -5
            chart.bars[0].fillColor = self._chart
            chart.bars[0].strokeColor = self._ink
            chart.bars[0].strokeWidth = 0.3
            for index, category in enumerate(page_categories):
                if category in failed:
                    chart.bars[(0, index)].fillColor = self._failure
            drawing.add(chart)
            drawing.add(
                String(
                    0,
                    329,
                    value_label,
                    fontName=self.branding.heading_font,
                    fontSize=self.branding.font_size,
                    fillColor=self._ink,
                )
            )
            drawing.add(
                String(
                    chart.x + chart.width / 2,
                    8,
                    category_label,
                    textAnchor="middle",
                    fontName=self.branding.body_font,
                    fontSize=self.branding.font_size - 1,
                    fillColor=self._ink,
                )
            )
            if failed:
                drawing.add(
                    String(
                        CONTENT_WIDTH,
                        329,
                        "* Failed leaf",
                        textAnchor="end",
                        fontName=self.branding.body_font,
                        fontSize=self.branding.font_size - 1,
                        fillColor=self._failure,
                    )
                )
            for index, (name, limit) in enumerate(limits):
                line_color = self._failure if index == 0 else self._warning
                dash = [4, 2] if index == 0 else [1, 2]
                position = chart.y + (limit - minimum) / (maximum - minimum) * chart.height
                drawing.add(
                    Line(
                        chart.x,
                        position,
                        chart.x + chart.width,
                        position,
                        strokeColor=line_color,
                        strokeWidth=1,
                        strokeDashArray=dash,
                    )
                )
                legend_y = 313 - index * 12
                drawing.add(
                    Line(
                        0,
                        legend_y + 3,
                        16,
                        legend_y + 3,
                        strokeColor=line_color,
                        strokeDashArray=dash,
                    )
                )
                drawing.add(
                    String(
                        22,
                        legend_y,
                        f"{name}: {_value(limit)}",
                        fontName=self.branding.body_font,
                        fontSize=self.branding.font_size - 1,
                        fillColor=self._ink,
                    )
                )
            section_title = (
                f"{title} ({page_index + 1} of {page_count})" if page_count > 1 else title
            )
            self._story.append(PageBreak())
            self._story.extend(self._section(section_title))
            self._story.append(drawing)
            if caption:
                self._story.append(self._paragraph(caption, "ReportCaption"))

    def add_histogram(
        self,
        title: str,
        values: Sequence[float],
        bins: int,
        measurement_label: str,
        caption: str = "",
    ) -> None:
        """Add a vector histogram using NumPy's standard bin calculation."""
        if not values or any(not math.isfinite(value) for value in values):
            raise ValueError(f"Histogram '{title}' needs finite measurements.")
        counts, edges = np.histogram(values, bins=bins)
        categories = [
            f"{left:.3g} to {right:.3g}"
            for left, right in zip(edges[:-1], edges[1:])
        ]
        self.add_bar_chart(
            title,
            categories,
            [float(count) for count in counts],
            "Number of measurements",
            measurement_label,
            caption=caption,
            whole_values=True,
        )

    def _overview(self) -> list[Flowable]:
        passed = self.values.get("passed")
        status = "Within tolerance" if passed is True else "Outside tolerance" if passed is False else "Not assessed"
        story: list[Flowable] = [
            self._paragraph(self.title, "Title"),
            Spacer(1, 8),
            self._paragraph(f"Test outcome: {status}", "Heading2"),
        ]
        identity = {
            "Date of analysis": self._measurement_value(self.values.get("date_of_analysis"), ("date_of_analysis",)),
            "Analysis software version": self.values.get("pylinac_version"),
            **self._context,
        }
        story.append(
            self._table(
                ("Test information", "Details"),
                identity.items(),
                (CONTENT_WIDTH * 0.4, CONTENT_WIDTH * 0.6),
            )
        )
        summary = [
            (self._field_title(key), self._measurement_value(value, (key,)))
            for key, value in self.values.items()
            if not isinstance(value, (dict, list))
            and key not in {"date_of_analysis", "pylinac_version"}
        ]
        if summary:
            story.extend(
                [
                    self._paragraph("Key measurements", "Heading2"),
                    self._table(
                        ("Measurement", "Value"),
                        summary,
                        (CONTENT_WIDTH * 0.64, CONTENT_WIDTH * 0.36),
                    ),
                ]
            )
        warnings = self.values.get("warnings")
        if isinstance(warnings, list) and warnings:
            story.extend(
                [
                    self._paragraph(f"Analysis warnings ({len(warnings)})", "Heading2"),
                    self._table(
                        ("Warning", "Details"),
                        ((index + 1, warning) for index, warning in enumerate(warnings)),
                        (CONTENT_WIDTH * 0.12, CONTENT_WIDTH * 0.88),
                    ),
                ]
            )
        if self._metadata:
            story.extend(
                [
                    self._paragraph("Site and review information", "Heading2"),
                    self._table(
                        ("Field", "Value"),
                        ((_label(str(key)), value) for key, value in self._metadata.items()),
                        (CONTENT_WIDTH * 0.4, CONTENT_WIDTH * 0.6),
                    ),
                ]
            )
        if self._notes:
            story.append(self._paragraph("Notes", "Heading2"))
            notes = [self._notes] if isinstance(self._notes, str) else self._notes
            story.extend(self._paragraph(note) for note in notes)
        return story

    def _result_tables(self, value: object, path: tuple[str | int, ...]) -> list[Flowable]:
        labels = self._table_labels.get(str(path[0]), ReportTableLabels())
        if isinstance(value, dict) and value:
            sequences: dict[str, list[object]] = {}
            for key, child in value.items():
                if not isinstance(child, list) or any(
                    isinstance(item, (dict, list)) for item in child
                ):
                    break
                sequences[str(key)] = child
            else:
                length = max(len(child) for child in sequences.values())
                if length:
                    tables: list[Flowable] = [
                        self._paragraph(
                            "Measurements are listed in their recorded order. "
                            "'Not recorded' means no measurement was supplied at that position.",
                            "ReportCaption",
                        ),
                        Spacer(1, 6),
                    ]
                    for start in range(0, length, 6):
                        indices = list(range(start, min(start + 6, length)))
                        tables.append(
                            self._table(
                                [labels.row_heading] + [f"{labels.series_heading} {index + 1}" for index in indices],
                                (
                                    [labels.row_labels.get(key, _label(key))]
                                    + [
                                        self._measurement_value(child[index], path + (key, index))
                                        if index < len(child) else "Not recorded"
                                        for index in indices
                                    ]
                                    for key, child in sequences.items()
                                ),
                                [CONTENT_WIDTH * 0.22]
                                + [CONTENT_WIDTH * 0.78 / len(indices)] * len(indices),
                            )
                        )
                        tables.append(Spacer(1, 8))
                    return tables
            objects: dict[str, dict[str, object]] = {}
            for key, child in value.items():
                if not isinstance(child, dict) or not child or any(
                    isinstance(item, (dict, list)) for item in child.values()
                ):
                    break
                objects[str(key)] = child
            else:
                columns = list(dict.fromkeys(key for child in objects.values() for key in child))
                if columns:
                    tables = []
                    for start in range(0, len(columns), 6):
                        selection = columns[start : start + 6]
                        tables.append(
                            self._table(
                                [labels.row_heading] + [labels.column_labels.get(column, _label(column)) for column in selection],
                                (
                                    [labels.row_labels.get(key, _label(key))]
                                    + [
                                        self._measurement_value(child[column], path + (key, column))
                                        if column in child else "Not recorded"
                                        for column in selection
                                    ]
                                    for key, child in objects.items()
                                ),
                                [CONTENT_WIDTH * 0.22]
                                + [CONTENT_WIDTH * 0.78 / len(selection)] * len(selection),
                            )
                        )
                        tables.append(Spacer(1, 8))
                    return tables
        return [
            self._table(
                (labels.row_heading, labels.value_heading),
                (
                    (self._measurement_label(location), self._measurement_value(measurement, location))
                    for location, measurement in _leaves(value, path)
                ),
                (CONTENT_WIDTH * 0.68, CONTENT_WIDTH * 0.32),
            )
        ]

    def _complete_results(self) -> list[Flowable]:
        story: list[Flowable] = [PageBreak()]
        story.extend(self._section("Detailed measurements"))
        story.append(
            self._paragraph(
                "All recorded measurements are listed below. Numbers are rounded for "
                "readability; the attached measurement data retain full precision.",
                "ReportCaption",
            )
        )
        for key, value in self.values.items():
            presentation = self._presentation.get((key,))
            path = (key,)
            story.extend(self._section(self._field_title(key), level=1))
            if presentation is not None and presentation.explanation:
                story.append(self._paragraph(presentation.explanation, "ReportCaption"))
            story.append(Spacer(1, 6))
            story.extend(self._result_tables(value, path))
        return story

    def _draw_page(self, canvas: Canvas, document: SimpleDocTemplate) -> None:
        if document.page == 1:
            _attach_json(canvas, self.results_json.encode("utf-8"))
            canvas.setCreator("Pylinac detailed reports")
            canvas.showOutline()
        canvas.saveState()
        canvas.setFillColor(self._paper)
        canvas.rect(0, 0, A4[0], A4[1], stroke=0, fill=1)
        if self._logo is not None:
            canvas.drawImage(
                str(self._logo),
                1.8 * cm,
                A4[1] - 2.0 * cm,
                width=3.6 * cm,
                height=1.0 * cm,
                preserveAspectRatio=True,
                mask="auto",
                anchor="sw",
            )
        self._page_header.drawOn(canvas, self._header_x, A4[1] - cm - self._header_height)
        canvas.setStrokeColor(self._primary)
        header_line = A4[1] - self._top_margin + 0.5 * cm
        canvas.line(1.8 * cm, header_line, A4[0] - 1.8 * cm, header_line)
        canvas.setStrokeColor(self._line)
        footer_line = self._bottom_margin - 0.5 * cm
        canvas.line(1.8 * cm, footer_line, A4[0] - 1.8 * cm, footer_line)
        self._page_footer.drawOn(canvas, 1.8 * cm, 0.6 * cm)
        canvas.setFont(self.branding.body_font, self.branding.font_size - 2)
        canvas.setFillColor(self._muted)
        canvas.drawRightString(A4[0] - 1.8 * cm, 0.6 * cm + 2, f"Page {document.page}")
        canvas.restoreState()

    def write(self, filename: str | Path | BinaryIO) -> None:
        """Write the report to a file or caller-owned binary stream."""
        document = _ReportTemplate(
            str(filename) if isinstance(filename, Path) else filename,
            pagesize=A4,
            leftMargin=1.8 * cm,
            rightMargin=1.8 * cm,
            topMargin=self._top_margin,
            bottomMargin=self._bottom_margin,
            title=self.title,
            author=self.branding.name,
        )
        contents = TableOfContents()
        contents.levelStyles = [
            ParagraphStyle(
                "ReportContents",
                fontName=self.branding.heading_font,
                fontSize=self.branding.font_size,
                leading=self.branding.font_size * 1.5,
                spaceBefore=5,
                textColor=self._ink,
            ),
            ParagraphStyle(
                "ReportContentsDetail",
                fontName=self.branding.body_font,
                fontSize=self.branding.font_size - 1,
                leading=(self.branding.font_size - 1) * 1.45,
                leftIndent=12,
                textColor=self._ink,
            ),
        ]
        document.multiBuild(
            self._overview()
            + [PageBreak(), self._paragraph("Contents", "Heading1"), contents]
            + self._story
            + self._complete_results(),
            onFirstPage=self._draw_page,
            onLaterPages=self._draw_page,
        )