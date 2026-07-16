"""Generate compact, evidence-linked Word reports for tender notices."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
import re
from typing import Literal
from zoneinfo import ZoneInfo

from docx import Document
from docx.document import Document as DocumentType
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.shared import Cm, Pt, RGBColor
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph

from ..schemas.tender import EvidenceReference, TenderNotice


ReportScope = Literal["full", "incremental"]

_SCOPE_LABELS: dict[ReportScope, str] = {
    "full": "全量报告",
    "incremental": "仅新增内容报告",
}
_SECTION_ORDER = {
    "procurement": 0,
    "qualification": 1,
    "technical": 2,
    "timeline": 3,
    "commercial": 4,
    "submission": 5,
    "evaluation": 6,
    "reference": 7,
}
_WINDOWS_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


@dataclass(frozen=True)
class DocxValidationResult:
    """Observable structure recovered by reopening a generated DOCX."""

    paragraph_count: int
    table_count: int
    hyperlink_targets: tuple[str, ...]


class DocxValidationError(ValueError):
    """Raised when a generated DOCX cannot be reopened or fails its contract."""


class DocxPublisher:
    """Render a standalone Word report without invoking the workflow."""

    def __init__(
        self,
        output_dir: Path,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.output_dir = Path(output_dir)
        self._clock = clock or (lambda: datetime.now(ZoneInfo("Asia/Shanghai")))

    def publish(
        self,
        query: str,
        notices: Sequence[TenderNotice],
        report_scope: ReportScope = "full",
    ) -> Path:
        """Generate, exclusively write, reopen, and validate one DOCX report."""

        if report_scope not in _SCOPE_LABELS:
            raise ValueError("report_scope must be 'full' or 'incremental'")
        notice_list = list(notices)
        if any(not isinstance(notice, TenderNotice) for notice in notice_list):
            raise TypeError("notices must contain only TenderNotice instances")

        generated_at = self._clock()
        filename = build_report_filename(query, generated_at)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        report_path = self.output_dir / filename
        document = _build_document(query, notice_list, report_scope, generated_at)
        buffer = BytesIO()
        document.save(buffer)

        try:
            report_file = report_path.open("xb")
        except FileExistsError as error:
            raise FileExistsError(
                f"report already exists for this query and minute: {report_path.name}"
            ) from error
        try:
            with report_file:
                report_file.write(buffer.getvalue())
        except Exception:
            report_path.unlink(missing_ok=True)
            raise

        try:
            validate_docx(
                report_path,
                expected_notices=notice_list,
                expected_scope=report_scope,
            )
        except Exception:
            report_path.unlink(missing_ok=True)
            raise
        return report_path


def build_report_filename(query: str, generated_at: datetime) -> str:
    """Build the required Windows-safe name: {question}_{YYYYMMDDHHmm}.docx."""

    safe_query = _WINDOWS_INVALID.sub("_", query)
    safe_query = re.sub(r"\s+", " ", safe_query).strip(" .")
    safe_query = re.sub(r"_+", "_", safe_query).strip(" ._")
    if not safe_query:
        safe_query = "情报任务"
    if safe_query.split(".", maxsplit=1)[0].upper() in _WINDOWS_RESERVED:
        safe_query = f"_{safe_query}"
    safe_query = safe_query[:80].rstrip(" ._") or "情报任务"
    return f"{safe_query}_{generated_at.strftime('%Y%m%d%H%M')}.docx"


def validate_docx(
    report_path: Path,
    *,
    expected_notices: Sequence[TenderNotice] | None = None,
    expected_scope: ReportScope | None = None,
) -> DocxValidationResult:
    """Reopen a DOCX and validate its core structure and external links."""

    try:
        document = Document(report_path)
    except Exception as error:
        raise DocxValidationError(f"cannot reopen generated DOCX: {report_path}") from error

    paragraphs = list(document.paragraphs)
    paragraphs.extend(
        paragraph
        for table in document.tables
        for row in table.rows
        for cell in row.cells
        for paragraph in cell.paragraphs
    )
    if not paragraphs or not document.tables:
        raise DocxValidationError("generated DOCX is missing paragraphs or tables")

    hyperlink_targets: list[str] = []
    for hyperlink in document.element.xpath(".//w:hyperlink"):
        relationship_id = hyperlink.get(qn("r:id"))
        relationship = document.part.rels.get(relationship_id)
        if relationship is None or relationship.reltype != RT.HYPERLINK:
            raise DocxValidationError("DOCX contains an invalid hyperlink relationship")
        target = relationship.target_ref
        if not relationship.is_external or not target.startswith(("http://", "https://")):
            raise DocxValidationError(f"DOCX hyperlink is not HTTP(S): {target}")
        hyperlink_targets.append(target)

    all_text = "\n".join(paragraph.text for paragraph in paragraphs)
    if expected_scope is not None and _SCOPE_LABELS[expected_scope] not in all_text:
        raise DocxValidationError("generated DOCX is missing the requested report scope")
    if expected_notices is not None:
        remaining_tables = _notice_tables(document)
        for notice in expected_notices:
            match = next(
                (
                    index for index, table in enumerate(remaining_tables)
                    if _notice_table_matches(document, table, notice)
                ),
                None,
            )
            if match is None:
                raise DocxValidationError(
                    f"generated DOCX is missing the required notice table: {notice.title}"
                )
            remaining_tables.pop(match)

    return DocxValidationResult(
        paragraph_count=len(paragraphs),
        table_count=len(document.tables),
        hyperlink_targets=tuple(hyperlink_targets),
    )


def _build_document(
    query: str,
    notices: list[TenderNotice],
    report_scope: ReportScope,
    generated_at: datetime,
) -> DocumentType:
    document = Document()
    _configure_document(document)
    _add_title_page(document, query, notices, report_scope, generated_at)

    if not notices:
        document.add_paragraph("未发现符合条件的公告。")
        return document

    ordered = sorted(notices, key=lambda item: (item.published_at, item.title), reverse=True)
    _add_overview(document, ordered)
    for index, notice in enumerate(ordered, start=1):
        document.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        _add_project(document, index, notice)
    return document


def _configure_document(document: DocumentType) -> None:
    section = document.sections[0]
    section.top_margin = Cm(1.8)
    section.bottom_margin = Cm(1.65)
    section.left_margin = Cm(1.8)
    section.right_margin = Cm(1.8)
    section.header_distance = Cm(0.7)
    section.footer_distance = Cm(0.7)

    normal = document.styles["Normal"]
    normal.font.name = "Microsoft YaHei"
    normal.font.size = Pt(9.5)
    normal.font.color.rgb = RGBColor(38, 50, 56)
    normal._element.get_or_add_rPr().get_or_add_rFonts().set(
        qn("w:eastAsia"), "Microsoft YaHei"
    )
    normal.paragraph_format.space_after = Pt(3)
    normal.paragraph_format.line_spacing = 1.15

    for style_name, size, color in (
        ("Title", 22, "17324D"),
        ("Heading 1", 16, "17324D"),
        ("Heading 2", 11, "FFFFFF"),
        ("Heading 3", 10, "315D7D"),
    ):
        style = document.styles[style_name]
        style.font.name = "Microsoft YaHei"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string(color)
        style._element.get_or_add_rPr().get_or_add_rFonts().set(
            qn("w:eastAsia"), "Microsoft YaHei"
        )
        style.paragraph_format.keep_with_next = True
        style.paragraph_format.space_before = Pt(8 if style_name != "Title" else 0)
        style.paragraph_format.space_after = Pt(4)

    header = section.header.paragraphs[0]
    header.text = "BidRadar-X  ·  招投标情报报告"
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _style_paragraph(header, 8, "6B7C8A")
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.add_run("BidRadar-X  ·  ")
    _add_page_number(footer)
    _style_paragraph(footer, 8, "7D8993")


def _add_title_page(
    document: DocumentType,
    query: str,
    notices: list[TenderNotice],
    report_scope: ReportScope,
    generated_at: datetime,
) -> None:
    kicker = document.add_paragraph("BIDRADAR-X  /  TENDER INTELLIGENCE")
    kicker.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _style_paragraph(kicker, 9, "4C7899", bold=True, spacing_after=10)
    title = document.add_paragraph(style="Title")
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.add_run("招投标信息分析报告")
    subtitle = document.add_paragraph(query)
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _style_paragraph(subtitle, 13, "315D7D", bold=True, spacing_after=14)

    metadata = document.add_table(rows=2, cols=4)
    metadata.alignment = WD_TABLE_ALIGNMENT.CENTER
    metadata.autofit = False
    widths = (Cm(2.2), Cm(5.8), Cm(2.2), Cm(5.8))
    values = (
        ("报告范围", _SCOPE_LABELS[report_scope], "项目数量", f"{len(notices)} 条"),
        ("生成时间", generated_at.strftime("%Y-%m-%d %H:%M"), "筛选区域", "上海" if "上海" in query else "按用户问题"),
    )
    for row, row_values in zip(metadata.rows, values, strict=True):
        for cell, width, value in zip(row.cells, widths, row_values, strict=True):
            cell.width = width
            cell.text = value
            _set_cell_margins(cell, 90, 110, 90, 110)
        for label_index in (0, 2):
            _shade_cell(row.cells[label_index], "E8EFF4")
            _style_cell(row.cells[label_index], 8.5, "315D7D", bold=True)
        for value_index in (1, 3):
            _style_cell(row.cells[value_index], 9.5, "263238")

    note = document.add_paragraph()
    note.alignment = WD_ALIGN_PARAGRAPH.CENTER
    note.add_run("内容由公告基本信息与八大模块条款识别结果汇总，点击“查看原公告”可回溯来源。")
    _style_paragraph(note, 8.5, "6B7C8A", spacing_before=10)


def _add_overview(document: DocumentType, notices: list[TenderNotice]) -> None:
    document.add_heading("项目总览", level=1)
    table = document.add_table(rows=1, cols=5)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    widths = (Cm(0.8), Cm(7.1), Cm(2.1), Cm(2.7), Cm(3.3))
    for cell, width, text in zip(
        table.rows[0].cells,
        widths,
        ("序号", "项目名称", "发布时间", "投标截止", "信息来源"),
        strict=True,
    ):
        cell.width = width
        cell.text = text
        _shade_cell(cell, "315D7D")
        _style_cell(cell, 8.5, "FFFFFF", bold=True)
    for index, notice in enumerate(notices, start=1):
        row = table.add_row()
        values = (
            str(index),
            notice.title,
            notice.published_at.strftime("%Y-%m-%d"),
            notice.deadline.strftime("%Y-%m-%d %H:%M") if notice.deadline else "原公告未载明",
            notice.source.source_name,
        )
        for cell, width, value in zip(row.cells, widths, values, strict=True):
            cell.width = width
            cell.text = value
            _set_cell_margins(cell, 65, 80, 65, 80)
            _style_cell(cell, 8, "263238")
        if index % 2 == 0:
            for cell in row.cells:
                _shade_cell(cell, "F4F7F9")


def _add_project(document: DocumentType, index: int, notice: TenderNotice) -> None:
    marker = document.add_paragraph(f"PROJECT {index:02d}")
    _style_paragraph(marker, 8.5, "4C7899", bold=True, spacing_after=2)
    document.add_heading(notice.title, level=1)
    _add_notice_summary(document, notice)

    summary = document.add_paragraph()
    summary.add_run("核心内容  ").bold = True
    summary.add_run(notice.core_content)
    _style_paragraph(summary, 9.5, "263238", spacing_before=5, spacing_after=6)

    sections = sorted(
        notice.requirement_sections,
        key=lambda section: _SECTION_ORDER.get(section.section_id, 99),
    )
    for section_index, section in enumerate(sections, start=1):
        _add_requirement_section(document, section_index, section, notice.evidence)


def _add_notice_summary(document: DocumentType, notice: TenderNotice) -> None:
    table = document.add_table(rows=6, cols=4)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    widths = (Cm(2.2), Cm(5.8), Cm(2.2), Cm(5.8))
    pairs = (
        ("项目名称", notice.title, "公告类型", _notice_kind_label(notice)),
        ("招标人", notice.purchaser or "原公告未载明", "项目编号", notice.project_code or "原公告未载明"),
        ("发布时间", notice.published_at.strftime("%Y-%m-%d %H:%M"), "投标截止", notice.deadline.strftime("%Y-%m-%d %H:%M") if notice.deadline else "原公告未载明"),
        ("项目区域", notice.region or "原公告未载明", "预算金额", _budget_label(notice)),
        ("信息来源", notice.source.source_name, "原公告", None),
        ("附件", None, "采集时间", notice.fetched_at.strftime("%Y-%m-%d %H:%M")),
    )
    for row, values in zip(table.rows, pairs, strict=True):
        for cell, width in zip(row.cells, widths, strict=True):
            cell.width = width
            _set_cell_margins(cell, 70, 90, 70, 90)
        for label_index in (0, 2):
            row.cells[label_index].text = values[label_index]
            _shade_cell(row.cells[label_index], "E8EFF4")
            _style_cell(row.cells[label_index], 8.5, "315D7D", bold=True)
        for value_index in (1, 3):
            value = values[value_index]
            if value is not None:
                row.cells[value_index].text = value
                _style_cell(row.cells[value_index], 8.5, "263238")

    source_paragraph = _clear_cell(table.cell(4, 3))
    _add_hyperlink(source_paragraph, str(notice.source.source_url), "查看原公告 ↗")
    attachment_paragraph = _clear_cell(table.cell(5, 1))
    if notice.attachments:
        for index, attachment in enumerate(notice.attachments):
            if index:
                attachment_paragraph.add_run("；")
            _add_hyperlink(
                attachment_paragraph,
                str(attachment.url),
                attachment.name or "查看附件",
            )
    else:
        attachment_paragraph.add_run("无")


def _add_requirement_section(document, index, section, evidence_items) -> None:
    title = section.title
    if section.section_id == "technical" and "技术要求" not in title:
        title = f"{title}（技术要求）"
    heading = document.add_heading(f"{index}. {title}", level=2)
    _shade_paragraph(heading, "315D7D")
    _set_paragraph_margins(heading, left=100, right=100)
    if section.summary:
        summary = document.add_paragraph(section.summary)
        _style_paragraph(summary, 8.5, "6B7C8A", spacing_after=4)

    evidence_by_id = {item.evidence_id: item for item in evidence_items}
    known_facts = [fact for fact in section.facts if fact.value is not None]
    if not known_facts and not section.tables:
        missing = document.add_paragraph("本公告未提及可核验条款。")
        _style_paragraph(missing, 8.5, "88959E")
        return

    if known_facts:
        table = document.add_table(rows=1, cols=4)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False
        widths = (Cm(2.8), Cm(5.2), Cm(2.8), Cm(5.2))
        for cell, width, label in zip(
            table.rows[0].cells,
            widths,
            ("要点", "识别原文", "要点", "识别原文"),
            strict=True,
        ):
            cell.width = width
            cell.text = label
            _shade_cell(cell, "DCE7EE")
            _style_cell(cell, 8, "315D7D", bold=True)
        for offset in range(0, len(known_facts), 2):
            row = table.add_row()
            for cell, width in zip(row.cells, widths, strict=True):
                cell.width = width
                _set_cell_margins(cell, 60, 70, 60, 70)
            for pair_index, fact in enumerate(known_facts[offset:offset + 2]):
                label_cell = row.cells[pair_index * 2]
                value_cell = row.cells[pair_index * 2 + 1]
                label_cell.text = fact.label
                _shade_cell(label_cell, "F2F6F8")
                _style_cell(label_cell, 7.8, "315D7D", bold=True)
                value_cell.text = fact.value or ""
                _style_cell(value_cell, 7.8, "263238")
                _append_fact_source(value_cell.paragraphs[0], fact.evidence_ids, evidence_by_id)

    for requirement_table in section.tables:
        document.add_heading(requirement_table.title, level=3)
        table = document.add_table(rows=1, cols=len(requirement_table.columns) + 1)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        for cell, label in zip(
            table.rows[0].cells,
            [*requirement_table.columns, "证据"],
            strict=True,
        ):
            cell.text = label
            _shade_cell(cell, "DCE7EE")
            _style_cell(cell, 8, "315D7D", bold=True)
        for requirement_row in requirement_table.rows:
            cells = table.add_row().cells
            for cell, value in zip(cells[:-1], requirement_row.cells, strict=True):
                cell.text = value or "原公告未载明"
                _style_cell(cell, 8, "263238")
            _append_fact_source(
                cells[-1].paragraphs[0],
                requirement_row.evidence_ids,
                evidence_by_id,
            )


def _append_fact_source(paragraph, evidence_ids, evidence_by_id) -> None:
    matching = [evidence_by_id[item] for item in evidence_ids if item in evidence_by_id]
    if not matching:
        paragraph.add_run("无")
        return
    for index, evidence in enumerate(matching):
        if index:
            paragraph.add_run("；\n")
        location = evidence.document_name or "来源"
        if evidence.page_number is not None:
            location += f" 第{evidence.page_number}页"
        if evidence.section:
            location += f" · {evidence.section}"
        if evidence.locator:
            location += f" · {evidence.locator}"
        paragraph.add_run(f"{evidence.quote}（{location}） ")
        _add_hyperlink(paragraph, str(evidence.source_url), "原文")


def _notice_kind_label(notice: TenderNotice) -> str:
    return {
        "prequalification": "资格预审公告",
        "tender": "招标公告",
        "correction": "更正公告",
    }.get(notice.opportunity_kind or "", "招标相关公告")


def _budget_label(notice: TenderNotice) -> str:
    if notice.budget is None:
        return "原公告未载明"
    return f"{notice.budget:,.2f} {notice.budget_currency}"


def _notice_tables(document: DocumentType) -> list[Table]:
    required_labels = (
        ("项目名称", "公告类型"),
        ("招标人", "项目编号"),
        ("发布时间", "投标截止"),
        ("项目区域", "预算金额"),
        ("信息来源", "原公告"),
        ("附件", "采集时间"),
    )
    matches = []
    for table in document.tables:
        if len(table.rows) != 6 or len(table.columns) != 4:
            continue
        labels = tuple((row.cells[0].text.strip(), row.cells[2].text.strip()) for row in table.rows)
        if labels == required_labels:
            matches.append(table)
    return matches


def _notice_table_matches(document: DocumentType, table: Table, notice: TenderNotice) -> bool:
    if (
        table.cell(0, 1).text.strip() != notice.title
        or table.cell(2, 1).text.strip() != notice.published_at.strftime("%Y-%m-%d %H:%M")
        or notice.source.source_name not in table.cell(4, 1).text
    ):
        return False
    if _cell_hyperlink_targets(document, table.cell(4, 3)) != {str(notice.source.source_url)}:
        return False
    expected_attachments = {str(item.url) for item in notice.attachments}
    if _cell_hyperlink_targets(document, table.cell(5, 1)) != expected_attachments:
        return False
    if not notice.attachments and table.cell(5, 1).text.strip() != "无":
        return False
    return True


def _cell_hyperlink_targets(document: DocumentType, cell: _Cell) -> set[str]:
    targets: set[str] = set()
    for hyperlink in cell._tc.xpath(".//w:hyperlink"):
        relationship = document.part.rels.get(hyperlink.get(qn("r:id")))
        if relationship is not None and relationship.reltype == RT.HYPERLINK:
            targets.add(relationship.target_ref)
    return targets


def _style_paragraph(
    paragraph: Paragraph,
    size: float,
    color: str,
    *,
    bold: bool = False,
    spacing_before: float = 0,
    spacing_after: float = 0,
) -> None:
    paragraph.paragraph_format.space_before = Pt(spacing_before)
    paragraph.paragraph_format.space_after = Pt(spacing_after)
    for run in paragraph.runs:
        run.font.name = "Microsoft YaHei"
        run.font.size = Pt(size)
        run.font.bold = bold or run.bold
        run.font.color.rgb = RGBColor.from_string(color)
        run._element.get_or_add_rPr().get_or_add_rFonts().set(
            qn("w:eastAsia"), "Microsoft YaHei"
        )


def _style_cell(cell: _Cell, size: float, color: str, *, bold: bool = False) -> None:
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    for paragraph in cell.paragraphs:
        _style_paragraph(paragraph, size, color, bold=bold)


def _shade_cell(cell: _Cell, fill: str) -> None:
    properties = cell._tc.get_or_add_tcPr()
    shading = properties.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        properties.append(shading)
    shading.set(qn("w:fill"), fill)


def _shade_paragraph(paragraph: Paragraph, fill: str) -> None:
    properties = paragraph._p.get_or_add_pPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill)
    properties.append(shading)


def _set_paragraph_margins(paragraph: Paragraph, *, left: int, right: int) -> None:
    properties = paragraph._p.get_or_add_pPr()
    indent = properties.find(qn("w:ind"))
    if indent is None:
        indent = OxmlElement("w:ind")
        properties.append(indent)
    indent.set(qn("w:left"), str(left))
    indent.set(qn("w:right"), str(right))


def _set_cell_margins(cell: _Cell, top: int, start: int, bottom: int, end: int) -> None:
    properties = cell._tc.get_or_add_tcPr()
    margins = properties.first_child_found_in("w:tcMar")
    if margins is None:
        margins = OxmlElement("w:tcMar")
        properties.append(margins)
    for name, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = margins.find(qn(f"w:{name}"))
        if node is None:
            node = OxmlElement(f"w:{name}")
            margins.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def _clear_cell(cell: _Cell) -> Paragraph:
    cell.text = ""
    return cell.paragraphs[0]


def _add_hyperlink(paragraph: Paragraph, url: str, label: str) -> None:
    relationship_id = paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), relationship_id)
    run = OxmlElement("w:r")
    run_properties = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "0563C1")
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    run_properties.extend((color, underline))
    run.append(run_properties)
    text = OxmlElement("w:t")
    text.text = label
    run.append(text)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def _add_page_number(paragraph: Paragraph) -> None:
    paragraph.add_run("第 ")
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instruction = OxmlElement("w:instrText")
    instruction.set(qn("xml:space"), "preserve")
    instruction.text = " PAGE "
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for element in (begin, instruction, end):
        run = OxmlElement("w:r")
        run.append(element)
        paragraph._p.append(run)
    paragraph.add_run(" 页")
