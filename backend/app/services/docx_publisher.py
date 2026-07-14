"""Independent DOCX publisher for validated tender notices."""

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
from docx.enum.text import WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph

from ..schemas.tender import EvidenceReference, TenderNotice


ReportScope = Literal["full", "incremental"]

_SCOPE_LABELS: dict[ReportScope, str] = {
    "full": "全量报告",
    "incremental": "仅新增内容报告",
}
_WINDOWS_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
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
    """Render a standalone Word report without invoking the application workflow."""

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
    """Build the required Windows-safe report name while retaining Chinese text."""

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
    """Reopen a DOCX and validate its paragraphs, tables, and external links."""

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
    if not paragraphs:
        raise DocxValidationError("generated DOCX contains no paragraphs")
    if not document.tables:
        raise DocxValidationError("generated DOCX contains no tables")

    hyperlink_targets: list[str] = []
    for hyperlink in document.element.xpath(".//w:hyperlink"):
        relationship_id = hyperlink.get(qn("r:id"))
        relationship = document.part.rels.get(relationship_id)
        if relationship is None or relationship.reltype != RT.HYPERLINK:
            raise DocxValidationError("DOCX contains a hyperlink without a valid relationship")
        target = relationship.target_ref
        if not relationship.is_external or not target.startswith(("http://", "https://")):
            raise DocxValidationError(f"DOCX hyperlink is not an external HTTP(S) URL: {target}")
        hyperlink_targets.append(target)

    all_text = "\n".join(paragraph.text for paragraph in paragraphs)
    if expected_scope is not None and _SCOPE_LABELS[expected_scope] not in all_text:
        raise DocxValidationError("generated DOCX is missing the requested report scope")

    if expected_notices is not None:
        remaining_notice_tables = _notice_tables(document)
        for notice in expected_notices:
            matching_index = next(
                (
                    index
                    for index, table in enumerate(remaining_notice_tables)
                    if _notice_table_matches(document, table, notice)
                ),
                None,
            )
            if matching_index is None:
                raise DocxValidationError(
                    f"generated DOCX is missing the required notice table: {notice.title}"
                )
            remaining_notice_tables.pop(matching_index)

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
    _configure_styles(document)
    document.add_heading(f"BidRadar-X 招投标公告{_SCOPE_LABELS[report_scope]}", level=0)

    metadata = document.add_table(rows=4, cols=2)
    metadata.style = "Table Grid"
    metadata_rows = (
        ("用户问题", query),
        ("报告范围", _SCOPE_LABELS[report_scope]),
        ("生成时间", generated_at.isoformat(sep=" ", timespec="minutes")),
        ("公告数量", str(len(notices))),
    )
    for row, (label, value) in zip(metadata.rows, metadata_rows, strict=True):
        row.cells[0].text = label
        row.cells[1].text = value

    if not notices:
        document.add_paragraph("未发现符合条件的公告。")
        return document

    ordered_notices = sorted(
        notices,
        key=lambda notice: (notice.published_at, notice.title),
        reverse=True,
    )
    for index, notice in enumerate(ordered_notices, start=1):
        if index > 1:
            document.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        document.add_heading(f"{index}. {notice.title}", level=1)
        _add_notice_summary(document, notice)
        _add_requirement_sections(document, notice)

    return document


def _configure_styles(document: DocumentType) -> None:
    for style_name in ("Normal", "Title", "Heading 1", "Heading 2", "Heading 3"):
        style = document.styles[style_name]
        style.font.name = "Microsoft YaHei"
        style._element.get_or_add_rPr().get_or_add_rFonts().set(
            qn("w:eastAsia"), "微软雅黑"
        )


def _add_notice_summary(document: DocumentType, notice: TenderNotice) -> None:
    table = document.add_table(rows=5, cols=2)
    table.style = "Table Grid"
    labels = ("标题", "发布时间", "来源链接", "核心内容", "附件链接")
    for row, label in zip(table.rows, labels, strict=True):
        row.cells[0].text = label

    table.cell(0, 1).text = notice.title
    table.cell(1, 1).text = notice.published_at.isoformat(sep=" ", timespec="minutes")

    source_paragraph = _clear_cell(table.cell(2, 1))
    source_paragraph.add_run(f"{notice.source.source_name}：")
    _add_hyperlink(source_paragraph, str(notice.source.source_url), "查看原公告")

    table.cell(3, 1).text = notice.core_content
    attachment_paragraph = _clear_cell(table.cell(4, 1))
    if not notice.attachments:
        attachment_paragraph.add_run("无")
    else:
        for index, attachment in enumerate(notice.attachments):
            if index:
                attachment_paragraph.add_run("；")
            label = attachment.name or str(attachment.url)
            _add_hyperlink(attachment_paragraph, str(attachment.url), label)


def _add_requirement_sections(document: DocumentType, notice: TenderNotice) -> None:
    evidence_by_id = {item.evidence_id: item for item in notice.evidence}
    for section in notice.requirement_sections:
        document.add_heading(section.title, level=2)
        if section.summary:
            document.add_paragraph(section.summary)

        if section.facts:
            facts_table = document.add_table(rows=1, cols=3)
            facts_table.style = "Table Grid"
            for cell, label in zip(
                facts_table.rows[0].cells,
                ("字段", "内容", "证据"),
                strict=True,
            ):
                cell.text = label
            for fact in section.facts:
                cells = facts_table.add_row().cells
                cells[0].text = fact.label
                cells[1].text = (
                    fact.value
                    if fact.value is not None
                    else f"未知（{fact.unknown_reason}）"
                )
                _render_evidence_links(
                    _clear_cell(cells[2]),
                    fact.evidence_ids,
                    evidence_by_id,
                )

        for requirement_table in section.tables:
            document.add_heading(requirement_table.title, level=3)
            table = document.add_table(rows=1, cols=len(requirement_table.columns) + 1)
            table.style = "Table Grid"
            for cell, label in zip(
                table.rows[0].cells,
                [*requirement_table.columns, "证据"],
                strict=True,
            ):
                cell.text = label
            for requirement_row in requirement_table.rows:
                cells = table.add_row().cells
                for cell, value in zip(
                    cells[:-1], requirement_row.cells, strict=True
                ):
                    cell.text = value if value is not None else "未知"
                _render_evidence_links(
                    _clear_cell(cells[-1]),
                    requirement_row.evidence_ids,
                    evidence_by_id,
                )


def _render_evidence_links(
    paragraph: Paragraph,
    evidence_ids: Sequence[str],
    evidence_by_id: dict[str, EvidenceReference],
) -> None:
    if not evidence_ids:
        paragraph.add_run("无")
        return
    for index, evidence_id in enumerate(evidence_ids):
        if index:
            paragraph.add_run("；\n")
        evidence = evidence_by_id[evidence_id]
        locations = [evidence.document_name or "来源"]
        if evidence.page_number is not None:
            locations.append(f"第{evidence.page_number}页")
        if evidence.section:
            locations.append(evidence.section)
        if evidence.locator:
            locations.append(evidence.locator)
        location = "，".join(locations)
        _add_hyperlink(paragraph, str(evidence.source_url), evidence_id)
        paragraph.add_run(f"（{location}）：{evidence.quote}")


def _notice_tables(document: DocumentType) -> list[Table]:
    required_labels = ("标题", "发布时间", "来源链接", "核心内容", "附件链接")
    notice_tables = []
    for table in document.tables:
        if len(table.rows) != len(required_labels) or len(table.columns) != 2:
            continue
        labels = tuple(row.cells[0].text.strip() for row in table.rows)
        if labels == required_labels:
            notice_tables.append(table)
    return notice_tables


def _notice_table_matches(
    document: DocumentType,
    table: Table,
    notice: TenderNotice,
) -> bool:
    if (
        table.cell(0, 1).text.strip() != notice.title
        or table.cell(1, 1).text.strip()
        != notice.published_at.isoformat(sep=" ", timespec="minutes")
        or notice.source.source_name not in table.cell(2, 1).text
        or table.cell(3, 1).text.strip() != notice.core_content
    ):
        return False

    source_targets = _cell_hyperlink_targets(document, table.cell(2, 1))
    if source_targets != {str(notice.source.source_url)}:
        return False

    attachment_cell = table.cell(4, 1)
    expected_attachment_targets = {
        str(attachment.url) for attachment in notice.attachments
    }
    if _cell_hyperlink_targets(document, attachment_cell) != expected_attachment_targets:
        return False
    if not notice.attachments and attachment_cell.text.strip() != "无":
        return False
    return True


def _cell_hyperlink_targets(document: DocumentType, cell: _Cell) -> set[str]:
    targets: set[str] = set()
    for hyperlink in cell._tc.xpath(".//w:hyperlink"):
        relationship_id = hyperlink.get(qn("r:id"))
        relationship = document.part.rels.get(relationship_id)
        if relationship is not None and relationship.reltype == RT.HYPERLINK:
            targets.add(relationship.target_ref)
    return targets


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
    run_properties.append(color)
    run_properties.append(underline)
    run.append(run_properties)

    text = OxmlElement("w:t")
    text.text = label
    run.append(text)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)
