"""Paginated, data-first PDF reports, separate from the legacy PDF canvas."""

from __future__ import annotations

import io
import json
import math
from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import BinaryIO
from xml.sax.saxutils import escape

import numpy as np
from PIL import Image as PILImage
from pydantic import BaseModel
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, Line, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfdoc
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

INK = colors.HexColor("#20272B")
GREEN = colors.HexColor("#20864B")
LIGHT = colors.HexColor("#F3F6F5")
LINE = colors.HexColor("#D7DFDC")
RED = colors.HexColor("#B52E38")
AMBER = colors.HexColor("#9B6507")
CONTENT_WIDTH = A4[0] - 3.6 * cm - 12


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
    return name.replace("_", " ").capitalize()


def _value(value: object) -> str:
    if value is None:
        return "Not available"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        return format(value, ".8g")
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=True)
    return str(value)


def _leaves(value: object, path: str) -> Iterator[tuple[str, object]]:
    if isinstance(value, dict) and value:
        for key, child in value.items():
            yield from _leaves(child, f"{path}[{json.dumps(str(key))}]")
    elif isinstance(value, list) and value:
        for index, child in enumerate(value):
            yield from _leaves(child, f"{path}[{index}]")
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
    """

    def __init__(
        self,
        title: str,
        results: BaseModel,
        context: Mapping[str, object] | None = None,
        metadata: Mapping[str, object] | None = None,
        notes: str | Sequence[str] | None = None,
        logo: Path | str | None = None,
    ) -> None:
        self.title = title
        self.results_json = results.model_dump_json()
        values = json.loads(self.results_json)
        if not isinstance(values, dict):
            raise TypeError("Detailed reports require a JSON object of results.")
        self.values: dict[str, object] = values
        self._fields = type(results).model_fields
        self._context = context or {}
        self._metadata = metadata or {}
        self._notes = notes
        self._story: list[Flowable] = []
        self._section_id = 0
        self._styles = getSampleStyleSheet()
        for name in ("Normal", "BodyText", "Heading1", "Heading2", "Title"):
            self._styles[name].textColor = INK
        self._styles["Title"].fontSize = 23
        self._styles["Title"].leading = 28
        self._styles["Title"].alignment = 0
        self._styles["Heading1"].fontSize = 16
        self._styles["Heading1"].leading = 20
        self._styles["Heading1"].spaceAfter = 10
        self._styles["Heading2"].fontSize = 12
        self._styles["Heading2"].leading = 16
        self._styles["Heading2"].spaceBefore = 12
        self._styles["BodyText"].leading = 14
        self._styles.add(
            ParagraphStyle(
                "ReportCell",
                fontName="Helvetica",
                fontSize=9,
                leading=12,
                textColor=INK,
                splitLongWords=True,
            )
        )
        self._styles.add(
            ParagraphStyle(
                "ReportPath",
                parent=self._styles["ReportCell"],
                fontSize=7,
                leading=10,
            )
        )
        self._styles.add(
            ParagraphStyle(
                "ReportHeader",
                parent=self._styles["ReportCell"],
                fontName="Helvetica-Bold",
                textColor=colors.white,
            )
        )
        self._styles.add(
            ParagraphStyle(
                "ReportCaption",
                parent=self._styles["BodyText"],
                fontSize=9,
                leading=12,
                textColor=colors.HexColor("#52615A"),
                spaceBefore=8,
            )
        )
        self._logo = Path(logo) if logo is not None else None
        if self._logo is not None and not self._logo.is_file():
            raise FileNotFoundError(f"Report logo does not exist: {self._logo}")
        if self._logo is None:
            packaged = Path(__file__).parent.parent / "files" / "Pylinac-GREEN.png"
            if packaged.is_file():
                self._logo = packaged

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
        field = self._fields.get(key)
        return (field.title if field is not None else None) or _label(key)

    def _table(
        self,
        headings: Sequence[str],
        rows: Iterable[Sequence[object]],
        widths: Sequence[float],
        path_column: int | None = None,
    ) -> LongTable:
        table_rows = [[self._paragraph(name, "ReportHeader") for name in headings]]
        table_rows.extend(
            [
                self._paragraph(
                    _value(value),
                    "ReportPath" if index == path_column else "ReportCell",
                )
                for index, value in enumerate(row)
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
                    ("BACKGROUND", (0, 0), (-1, 0), GREEN),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.5, GREEN),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.25, LINE),
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
            chart.valueAxis.gridStrokeColor = LINE
            chart.valueAxis.labels.fontName = "Helvetica"
            chart.valueAxis.labels.fontSize = 9
            chart.valueAxis.labelTextFormat = "%d" if whole_values else "%.3g"
            if whole_values:
                chart.valueAxis.valueStep = max(1, math.ceil((maximum - minimum) / 5))
            chart.categoryAxis.categoryNames = [
                f"{name} *" if name in failed else name for name in page_categories
            ]
            chart.categoryAxis.labels.fontName = "Helvetica"
            chart.categoryAxis.labels.fontSize = 9
            chart.categoryAxis.labels.angle = 45
            chart.categoryAxis.labels.boxAnchor = "ne"
            chart.categoryAxis.labels.dy = -5
            chart.bars[0].fillColor = GREEN
            chart.bars[0].strokeColor = INK
            chart.bars[0].strokeWidth = 0.3
            for index, category in enumerate(page_categories):
                if category in failed:
                    chart.bars[(0, index)].fillColor = RED
            drawing.add(chart)
            drawing.add(
                String(
                    0,
                    329,
                    value_label,
                    fontName="Helvetica-Bold",
                    fontSize=10,
                    fillColor=INK,
                )
            )
            drawing.add(
                String(
                    chart.x + chart.width / 2,
                    8,
                    category_label,
                    textAnchor="middle",
                    fontName="Helvetica",
                    fontSize=9,
                    fillColor=INK,
                )
            )
            if failed:
                drawing.add(
                    String(
                        CONTENT_WIDTH,
                        329,
                        "* Failed leaf",
                        textAnchor="end",
                        fontName="Helvetica",
                        fontSize=9,
                        fillColor=RED,
                    )
                )
            for index, (name, limit) in enumerate(limits):
                line_color = RED if index == 0 else AMBER
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
                        fontName="Helvetica",
                        fontSize=9,
                        fillColor=INK,
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
        status = "PASSED" if passed is True else "FAILED" if passed is False else "Not evaluated"
        story: list[Flowable] = [
            self._paragraph(self.title, "Title"),
            Spacer(1, 8),
            self._paragraph(f"Analysis status: {status}", "Heading2"),
        ]
        identity = {
            "Analysis date": self.values.get("date_of_analysis"),
            "Pylinac version": self.values.get("pylinac_version"),
            **self._context,
        }
        story.append(
            self._table(
                ("Report identity", "Value"),
                identity.items(),
                (CONTENT_WIDTH * 0.4, CONTENT_WIDTH * 0.6),
            )
        )
        summary = [
            (self._field_title(key), value)
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
                    self._paragraph("Report metadata", "Heading2"),
                    self._table(
                        ("Field", "Value"),
                        self._metadata.items(),
                        (CONTENT_WIDTH * 0.4, CONTENT_WIDTH * 0.6),
                    ),
                ]
            )
        if self._notes:
            story.append(self._paragraph("Notes", "Heading2"))
            notes = [self._notes] if isinstance(self._notes, str) else self._notes
            story.extend(self._paragraph(note) for note in notes)
        return story

    def _result_tables(self, value: object, path: str) -> list[Flowable]:
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
                            "Index columns are 0-based. 'No entry' means that index "
                            "is absent from the list, not a measured value.",
                            "ReportCaption",
                        ),
                        Spacer(1, 6),
                    ]
                    for start in range(0, length, 6):
                        indices = list(range(start, min(start + 6, length)))
                        tables.append(
                            self._table(
                                ["JSON key"] + [f"Index {index}" for index in indices],
                                (
                                    [key]
                                    + [
                                        child[index] if index < len(child) else "No entry"
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
                if not isinstance(child, dict) or any(
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
                                ["JSON key"] + selection,
                                (
                                    [key] + [child.get(column, "No entry") for column in selection]
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
                ("JSON field path", "Value"),
                _leaves(value, path),
                (CONTENT_WIDTH * 0.68, CONTENT_WIDTH * 0.32),
                path_column=0,
            )
        ]

    def _complete_results(self) -> list[Flowable]:
        story: list[Flowable] = [PageBreak()]
        story.extend(self._section("Complete analysis results"))
        story.append(
            self._paragraph(
                "All results are listed below. Display values use up to eight significant "
                "digits; the attached results.json preserves the original JSON precision.",
                "ReportCaption",
            )
        )
        for key, value in self.values.items():
            field = self._fields.get(key)
            path = f"$[{json.dumps(key)}]"
            story.extend(self._section(self._field_title(key), level=1))
            story.append(self._paragraph(path, "ReportPath"))
            if field is not None and field.description:
                story.append(self._paragraph(field.description, "ReportCaption"))
            story.append(Spacer(1, 6))
            story.extend(self._result_tables(value, path))
        return story

    def _draw_page(self, canvas: Canvas, document: SimpleDocTemplate) -> None:
        if document.page == 1:
            _attach_json(canvas, self.results_json.encode("utf-8"))
            canvas.setCreator("Pylinac detailed reports")
            canvas.showOutline()
        canvas.saveState()
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
        else:
            canvas.setFont("Helvetica-Bold", 14)
            canvas.setFillColor(GREEN)
            canvas.drawString(1.8 * cm, A4[1] - 1.7 * cm, "PYLINAC")
        canvas.setStrokeColor(LINE)
        canvas.line(1.8 * cm, A4[1] - 2.2 * cm, A4[0] - 1.8 * cm, A4[1] - 2.2 * cm)
        canvas.line(1.8 * cm, 1.5 * cm, A4[0] - 1.8 * cm, 1.5 * cm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(INK)
        canvas.drawString(1.8 * cm, 1.0 * cm, "Pylinac QA report")
        canvas.drawRightString(A4[0] - 1.8 * cm, 1.0 * cm, f"Page {document.page}")
        canvas.restoreState()

    def write(self, filename: str | Path | BinaryIO) -> None:
        """Write the report to a file or caller-owned binary stream."""
        document = _ReportTemplate(
            str(filename) if isinstance(filename, Path) else filename,
            pagesize=A4,
            leftMargin=1.8 * cm,
            rightMargin=1.8 * cm,
            topMargin=2.7 * cm,
            bottomMargin=2.0 * cm,
            title=self.title,
            author="Pylinac",
        )
        contents = TableOfContents()
        contents.levelStyles = [
            ParagraphStyle(
                "ReportContents",
                fontName="Helvetica-Bold",
                fontSize=10,
                leading=15,
                spaceBefore=5,
                textColor=INK,
            ),
            ParagraphStyle(
                "ReportContentsDetail",
                fontName="Helvetica",
                fontSize=9,
                leading=13,
                leftIndent=12,
                textColor=INK,
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