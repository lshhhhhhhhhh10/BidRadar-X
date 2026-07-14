from datetime import datetime
import unittest

from pydantic import ValidationError

from app.schemas.tender import (
    Attachment,
    DeliveryRecord,
    EvidenceReference,
    FieldChange,
    RequirementFact,
    RequirementSection,
    RequirementTable,
    RequirementTableRow,
    ScheduleSpec,
    SourceRecord,
    TaskSpec,
    TenderNotice,
)


class TaskSpecTest(unittest.TestCase):
    def test_task_spec_serializes_an_explicit_monitoring_window(self) -> None:
        task = TaskSpec(
            task_id="task-20260714-001",
            query="查找安徽省服务器采购公告",
            topic="服务器采购",
            regions=["安徽省"],
            keywords=["服务器", "GPU服务器"],
            exclusions=["网站服务器故障"],
            time_range_start=datetime.fromisoformat("2026-07-01T00:00:00+08:00"),
            time_range_end=datetime.fromisoformat("2026-07-14T23:59:59+08:00"),
            schedule=ScheduleSpec(frequency="daily"),
        )

        payload = task.model_dump(mode="json")

        self.assertEqual(payload["schedule"]["frequency"], "daily")
        self.assertEqual(payload["schedule"]["timezone"], "Asia/Shanghai")
        self.assertEqual(payload["regions"], ["安徽省"])

    def test_task_spec_rejects_a_reversed_monitoring_window(self) -> None:
        with self.assertRaisesRegex(ValidationError, "time_range_end"):
            TaskSpec(
                task_id="task-20260714-002",
                query="查找服务器采购公告",
                topic="服务器采购",
                regions=[],
                keywords=["服务器"],
                time_range_start=datetime.fromisoformat("2026-07-14T00:00:00+08:00"),
                time_range_end=datetime.fromisoformat("2026-07-01T00:00:00+08:00"),
                schedule=ScheduleSpec(frequency="once"),
            )

    def test_schedule_rejects_an_unknown_timezone(self) -> None:
        with self.assertRaisesRegex(ValidationError, "IANA timezone"):
            ScheduleSpec(frequency="daily", timezone="Not/A-Timezone")


class TenderNoticeIdentityTest(unittest.TestCase):
    def test_original_and_republication_keep_distinct_records_for_one_project(self) -> None:
        original = TenderNotice(
            notice_id="notice-origin-001",
            notice_type="tender",
            title="通用设备采购公告",
            published_at="2026-07-14T09:00:00+08:00",
            source=SourceRecord(
                source_id="source-a",
                source_name="权威发布平台",
                source_url="https://source-a.example/notices/001",
                publication_role="original",
            ),
            core_content="采购通用计算设备，具体参数以附件为准。",
            attachments=[
                Attachment(
                    attachment_id="attachment-001",
                    name="采购需求.pdf",
                    url="https://source-a.example/files/001.pdf",
                    media_type="application/pdf",
                )
            ],
            region="示例地区",
            topic_keywords=["计算设备"],
            purchaser="示例采购单位",
            budget="1000000.00",
            deadline="2026-07-31T17:00:00+08:00",
            raw_content_fingerprint="a" * 64,
            notice_stable_fingerprint="b" * 64,
            project_stable_fingerprint="c" * 64,
            fetched_at="2026-07-14T09:05:00+08:00",
            evidence=[
                EvidenceReference(
                    evidence_id=f"evidence-{field_path}",
                    field_path=field_path,
                    source_url="https://source-a.example/notices/001",
                    quote="公告披露了该结构化字段。",
                    fetched_at="2026-07-14T09:05:00+08:00",
                )
                for field_path in ("region", "topic_keywords", "purchaser", "budget", "deadline")
            ],
        )
        republication = TenderNotice(
            **{
                **original.model_dump(),
                "notice_id": "notice-repost-001",
                "source": SourceRecord(
                    source_id="source-b",
                    source_name="转载平台",
                    source_url="https://source-b.example/reposts/001",
                    publication_role="republication",
                    canonical_notice_url="https://source-a.example/notices/001",
                ),
                "raw_content_fingerprint": "d" * 64,
                "fetched_at": "2026-07-14T09:10:00+08:00",
            }
        )

        self.assertEqual(original.source.publication_role, "original")
        self.assertEqual(republication.source.publication_role, "republication")
        self.assertNotEqual(original.raw_content_fingerprint, republication.raw_content_fingerprint)
        self.assertEqual(original.notice_stable_fingerprint, republication.notice_stable_fingerprint)
        self.assertEqual(original.project_stable_fingerprint, republication.project_stable_fingerprint)
        self.assertEqual(str(original.attachments[0].url), "https://source-a.example/files/001.pdf")

    def test_extracted_core_fact_requires_field_level_evidence(self) -> None:
        with self.assertRaisesRegex(ValidationError, "structured fields missing evidence"):
            TenderNotice(
                notice_id="notice-without-fact-evidence",
                notice_type="tender",
                title="通用设备采购公告",
                published_at="2026-07-14T09:00:00+08:00",
                source=SourceRecord(
                    source_id="source-a",
                    source_name="权威发布平台",
                    source_url="https://source-a.example/notices/no-evidence",
                    publication_role="original",
                ),
                core_content="公告正文。",
                purchaser="示例采购单位",
                raw_content_fingerprint="1" * 64,
                notice_stable_fingerprint="2" * 64,
                project_stable_fingerprint="3" * 64,
                fetched_at="2026-07-14T09:05:00+08:00",
            )


class WordContentContractTest(unittest.TestCase):
    def test_all_word_sections_and_field_level_evidence_are_representable(self) -> None:
        section_titles = {
            "procurement": "项目及采购内容",
            "qualification": "投标人资格要求",
            "technical": "技术与服务要求",
            "timeline": "项目周期与验收要求",
            "commercial": "报价、付款与保证金",
            "submission": "投标组织与文件要求",
            "evaluation": "评标与定标规则",
            "reference": "客观参考信息",
        }
        sections = [
            RequirementSection(
                section_id=section_id,
                title=title,
                facts=[
                    RequirementFact(
                        label="待抽取字段",
                        value=None,
                        unknown_reason="源文件未披露",
                    )
                ],
            )
            for section_id, title in section_titles.items()
        ]
        evidence = EvidenceReference(
            evidence_id="evidence-001",
            field_path="requirement_sections.technical.tables.technical_matrix",
            source_url="https://source-a.example/files/001.pdf",
            attachment_id="attachment-001",
            document_name="采购需求.pdf",
            page_number=3,
            section="技术参数",
            quote="设备应满足采购文件列明的技术参数。",
            fetched_at="2026-07-14T09:05:00+08:00",
        )
        sections[2] = RequirementSection(
            section_id="technical",
            title="技术与服务要求",
            facts=[
                RequirementFact(
                    label="技术参数",
                    value="按采购文件参数表执行",
                    evidence_ids=["evidence-001"],
                )
            ],
            tables=[
                RequirementTable(
                    title="技术参数矩阵",
                    columns=["项目", "甲方要求值", "是否强制"],
                    rows=[
                        RequirementTableRow(
                            cells=["计算设备", "按参数表执行", "是"],
                            evidence_ids=["evidence-001"],
                        )
                    ],
                )
            ],
        )
        notice = TenderNotice(
            notice_id="notice-001",
            notice_type="tender",
            title="通用设备采购公告",
            published_at="2026-07-14T09:00:00+08:00",
            source=SourceRecord(
                source_id="source-a",
                source_name="权威发布平台",
                source_url="https://source-a.example/notices/001",
                publication_role="original",
            ),
            core_content="采购通用计算设备，具体参数以附件为准。",
            attachments=[
                Attachment(
                    attachment_id="attachment-001",
                    name="采购需求.pdf",
                    url="https://source-a.example/files/001.pdf",
                )
            ],
            raw_content_fingerprint="a" * 64,
            notice_stable_fingerprint="b" * 64,
            project_stable_fingerprint="c" * 64,
            fetched_at="2026-07-14T09:05:00+08:00",
            evidence=[evidence],
            requirement_sections=sections,
        )

        payload = notice.model_dump(mode="json")

        self.assertEqual(
            [section["section_id"] for section in payload["requirement_sections"]],
            list(section_titles),
        )
        self.assertIsNone(payload["requirement_sections"][0]["facts"][0]["value"])
        self.assertEqual(payload["evidence"][0]["page_number"], 3)

    def test_known_requirement_rejects_a_dangling_evidence_reference(self) -> None:
        with self.assertRaisesRegex(ValidationError, "unknown evidence"):
            TenderNotice(
                notice_id="notice-002",
                notice_type="tender",
                title="通用设备采购公告",
                published_at="2026-07-14T09:00:00+08:00",
                source=SourceRecord(
                    source_id="source-a",
                    source_name="权威发布平台",
                    source_url="https://source-a.example/notices/002",
                    publication_role="original",
                ),
                core_content="公告正文。",
                raw_content_fingerprint="d" * 64,
                notice_stable_fingerprint="e" * 64,
                project_stable_fingerprint="f" * 64,
                fetched_at="2026-07-14T09:05:00+08:00",
                requirement_sections=[
                    RequirementSection(
                        section_id="qualification",
                        title="投标人资格要求",
                        facts=[
                            RequirementFact(
                                label="主体资格",
                                value="依法登记",
                                evidence_ids=["missing-evidence"],
                            )
                        ],
                    )
                ],
            )


class DeliveryRecordTest(unittest.TestCase):
    def test_material_change_carries_before_after_values_and_an_idempotency_key(self) -> None:
        delivery = DeliveryRecord(
            delivery_id="delivery-001",
            task_id="task-001",
            run_id="run-002",
            delivery_type="material_change",
            project_stable_fingerprint="a" * 64,
            notice_stable_fingerprint="b" * 64,
            delivery_fingerprint="c" * 64,
            changes=[
                FieldChange(
                    field_path="deadline",
                    previous_value="2026-07-30T17:00:00+08:00",
                    current_value="2026-07-31T17:00:00+08:00",
                    evidence_ids=["evidence-001"],
                )
            ],
            status="delivered",
            created_at="2026-07-14T10:00:00+08:00",
            delivered_at="2026-07-14T10:01:00+08:00",
            artifact_uri="reports/task-001/run-002.docx",
        )

        payload = delivery.model_dump(mode="json")

        self.assertEqual(payload["delivery_fingerprint"], "c" * 64)
        self.assertEqual(payload["changes"][0]["field_path"], "deadline")
        self.assertEqual(payload["status"], "delivered")

    def test_material_change_requires_at_least_one_changed_field(self) -> None:
        with self.assertRaisesRegex(ValidationError, "material_change"):
            DeliveryRecord(
                delivery_id="delivery-002",
                task_id="task-001",
                run_id="run-003",
                delivery_type="material_change",
                project_stable_fingerprint="d" * 64,
                notice_stable_fingerprint="e" * 64,
                delivery_fingerprint="f" * 64,
                changes=[],
                status="pending",
                created_at="2026-07-14T11:00:00+08:00",
            )


if __name__ == "__main__":
    unittest.main()
