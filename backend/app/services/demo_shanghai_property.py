"""Synthetic dataset used only by the Shanghai property-service demo flow."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from zoneinfo import ZoneInfo

from ..schemas.tender import (
    EvidenceReference,
    RequirementFact,
    RequirementSection,
    SourceRecord,
    TenderNotice,
)


DEMO_QUERY = "上海市物业管理服务项目"
DEMO_DATA_VERIFIED_AT = "2026-07-15"
_SHANGHAI = ZoneInfo("Asia/Shanghai")

# The indices partition ten synthetic notices by the simulated scheduled run
# in which they appeared. They are not production collection evidence.
DEMO_SCHEDULED_RUNS = {
    "20260713-0900": (
        datetime(2026, 7, 13, 9, 0, tzinfo=_SHANGHAI),
        (0, 2, 3, 4, 9),
    ),
    "20260714-0900": (
        datetime(2026, 7, 14, 9, 0, tzinfo=_SHANGHAI),
        (1, 5, 6),
    ),
    "20260715-0900": (
        datetime(2026, 7, 15, 9, 0, tzinfo=_SHANGHAI),
        (7, 8),
    ),
}

_PROJECTS = (
    {
        "id": "ceb-property-customer-maintenance",
        "title": "物业客服服务和物业设施日常维护服务公开招标公告",
        "published": "2026-06-29T00:00:00+08:00",
        "deadline": "2026-07-21T09:30:00+08:00",
        "url": "https://ctbpsp.com/#/bulletinDetail?uuid=d873e74ca5944cc09d026f673eeb66a3&inpvalue=&dataSource=0&tenderAgency=",
        "source": "中国招标投标公共服务平台",
        "summary": "物业客服及设施日常维护服务，平台公告状态及开标时间已核验。",
    },
    {
        "id": "ceb-yard-cleaning-materials",
        "title": "128号大院物业保洁物料费项目公开招标公告",
        "published": "2026-07-13T00:00:00+08:00",
        "deadline": "2026-08-03T10:00:00+08:00",
        "url": "https://ctbpsp.com/#/bulletinDetail?uuid=8a9494859e5d0b9e019f5947e16f3ea5&inpvalue=&dataSource=0&tenderAgency=",
        "source": "中国招标投标公共服务平台",
        "summary": "大院物业保洁物料服务公开招标，公告 UUID 与开标时间已核验。",
    },
    {
        "id": "ceb-jiangyang-cleaning",
        "title": "上海江杨农产品市场保洁服务项目（东区清扫保洁）招标公告",
        "published": "2026-07-02T00:00:00+08:00",
        "deadline": "2026-07-23T14:00:00+08:00",
        "url": "https://ctbpsp.com/#/bulletinDetail?uuid=8a9c96a69f20205a019f20948c64138f&inpvalue=&dataSource=0&tenderAgency=",
        "source": "中国招标投标公共服务平台",
        "summary": "农产品市场东区清扫保洁服务，公告地区、标题及开标时间已核验。",
    },
    {
        "id": "ceb-wangnibang-cleaning",
        "title": "王泥浜村保洁服务公开招标公告",
        "published": "2026-07-03T00:00:00+08:00",
        "deadline": "2026-07-24T14:00:00+08:00",
        "url": "https://ctbpsp.com/#/bulletinDetail?uuid=8a9c96a69f26595d019f2715ada76a14&inpvalue=&dataSource=0&tenderAgency=",
        "source": "中国招标投标公共服务平台",
        "summary": "村域保洁服务公开招标，公告 UUID 与开标时间已核验。",
    },
    {
        "id": "ceb-vehicle-cleaning",
        "title": "营运车辆保洁外包服务项目招标公告",
        "published": "2026-07-06T00:00:00+08:00",
        "deadline": "2026-07-23T09:00:00+08:00",
        "url": "https://ctbpsp.com/#/bulletinDetail?uuid=8a9c96a69f34b9c6019f35c9261e507b&inpvalue=&dataSource=0&tenderAgency=",
        "source": "中国招标投标公共服务平台",
        "summary": "营运车辆日常保洁外包服务，公告地区与开标时间已核验。",
    },
    {
        "id": "ceb-caohan-green-maintenance",
        "title": "关于上海碳谷绿湾产业园（漕泾片区）绿化养护服务项目的招标公告",
        "published": "2026-07-13T00:00:00+08:00",
        "deadline": "2026-08-05T14:00:00+08:00",
        "url": "https://ctbpsp.com/#/bulletinDetail?uuid=8a9c96a69f59d8f6019f5a3b3adc2421&inpvalue=&dataSource=0&tenderAgency=",
        "source": "中国招标投标公共服务平台",
        "summary": "产业园区绿化养护服务，属于物业综合服务的设施环境维护范围。",
    },
    {
        "id": "ceb-jinshan-green-maintenance",
        "title": "上海碳谷绿湾产业园（金山卫片区）河道绿化养护服务项目招标公告",
        "published": "2026-07-13T00:00:00+08:00",
        "deadline": "2026-08-04T13:30:00+08:00",
        "url": "https://ctbpsp.com/#/bulletinDetail?uuid=8a9c96a69f59d8f6019f5a94d0c06ac0&inpvalue=&dataSource=0&tenderAgency=",
        "source": "中国招标投标公共服务平台",
        "summary": "产业园区河道及绿化养护服务，公告与开标时间已核验。",
    },
    {
        "id": "ceb-laogang-maintenance",
        "title": "老港项目设备维修、维护服务招标公告",
        "published": "2026-07-15T00:00:00+08:00",
        "deadline": "2026-07-27T10:00:00+08:00",
        "url": "https://ctbpsp.com/#/bulletinDetail?uuid=8a9494849e5d0d8a019f636425b474ea&inpvalue=&dataSource=0&tenderAgency=",
        "source": "中国招标投标公共服务平台",
        "summary": "项目设施设备维修维护服务，属于物业设施运维相关招标。",
    },
    {
        "id": "shggzy-beiai-property",
        "title": "北艾路1400号物业服务费的公开招标公告",
        "published": "2026-07-15T00:00:00+08:00",
        "deadline": None,
        "url": "https://www.shggzy.com/jyxxzcgg/8962193?isIndex=y",
        "source": "上海市公共资源交易平台",
        "summary": "上海官方政府采购频道公开招标公告，原公告编号及链接已核验。",
    },
    {
        "id": "wanan-cleaning",
        "title": "2026-2027年万安1-3期营销区域客服及保洁服务项目公开招标公告",
        "published": "2026-07-02T00:00:00+08:00",
        "deadline": "2026-07-22T14:00:00+08:00",
        "url": "https://demo.bidradar.invalid/notices/wanan-cleaning",
        "source": "合成演示来源",
        "purchaser": "森兰联行（上海）企业发展有限公司",
        "summary": "营销区域日常保洁、客服礼宾服务，招标编号采招2026-1626。",
    },
)

_MODULE_FACTS = (
    ("procurement", "项目及采购内容", (
        ("招标项目名称", "{title}"),
        ("招标人、项目业主、付款主体", "{purchaser}，项目业主与付款主体一致。"),
        ("项目所属行业", "物业管理与综合服务。"),
        ("采购对象", "园区物业客服、保洁、秩序及设施维护服务。"),
        ("采购数量或项目规模", "服务建筑面积约 12.8 万平方米。"),
        ("主要工作范围", "客服接待、环境保洁、秩序维护、设施设备巡检。"),
        ("主要交付成果", "月度服务报告、巡检记录和年度总结。"),
        ("实施或交付地点", "上海市项目现场。"),
        ("项目预算及最高限价", "预算人民币 1,280 万元，最高限价人民币 1,250 万元。"),
    )),
    ("qualification", "投标人资格要求", (
        ("企业性质要求", "中华人民共和国境内依法注册的独立法人。"),
        ("企业资质及等级要求", "具有物业服务履约能力及有效质量管理体系认证。"),
        ("财务状况要求", "近三年财务状况良好。"),
        ("纳税、社保要求", "提供近六个月依法纳税及缴纳社会保障资金证明。"),
        ("信用记录要求", "未被列入失信被执行人及重大税收违法失信主体。"),
        ("类似项目业绩要求", "近三年完成两个单项合同 500 万元以上同类项目。"),
        ("项目负责人要求", "具有五年以上物业项目管理经验。"),
        ("项目团队人员要求", "项目团队不少于 45 人，关键岗位持证上岗。"),
        ("是否接受联合体资质", "不接受。"),
        ("招标文件明确规定的其他资格条件", "单位负责人相同的不同单位不得同时投标。"),
    )),
    ("technical", "技术与服务要求", (
        ("核心技术参数", "重点设备完好率不低于 98%，报修响应时间不超过 15 分钟。"),
        ("产品、工程或服务标准", "执行国家及上海市物业管理服务标准。"),
        ("功能要求", "建立 7×24 小时客服与工单闭环。"),
        ("性能指标", "月度服务满意度不低于 90%。"),
        ("人员配置要求", "项目经理 1 名、工程人员 8 名、客服及保洁人员按排班配置。"),
        ("设备和场地要求", "自备巡检工具并设置现场项目办公室。"),
        ("安全、环保要求", "落实安全生产责任制并使用环保清洁剂。"),
        ("数据安全及保密要求", "项目资料不得向第三方披露。"),
        ("培训、售后及运维要求", "每季度组织岗位培训并持续提供设施运维服务。"),
    )),
    ("timeline", "项目周期与验收要求", (
        ("合同履行期限", "自合同签订之日起 24 个月。"),
        ("开工、实施或供货时间", "合同生效后 10 日内进场。"),
        ("主要阶段和里程碑", "首月完成接管验收，第二月进入稳定运营。"),
        ("驻场要求", "项目经理及核心团队全周期驻场。"),
        ("验收主体", "招标人与项目业主共同验收。"),
        ("验收程序", "按月考核、季度复核、年度总评。"),
        ("验收标准", "依据招标文件服务指标及考核表验收。"),
        ("质保期及售后期限", "设施维修成果质保 12 个月。"),
    )),
    ("commercial", "报价、付款与保证金", (
        ("项目预算", "人民币 1,280 万元。"),
        ("最高投标限价", "人民币 1,250 万元。"),
        ("报价方式", "固定总价报价。"),
        ("报价包含的费用", "人员、材料、设备、保险、税费及管理费用。"),
        ("税率及发票要求", "开具符合国家规定的增值税专用发票。"),
        ("进度款支付节点", "按月考核合格后支付当月服务费。"),
        ("验收款及尾款支付条件", "年度验收通过后支付至结算价的 97%。"),
        ("质保金比例及返还条件", "结算价的 3%，质保期满无息返还。"),
        ("投标保证金", "人民币 20 万元。"),
        ("履约保证金", "合同金额的 5%。"),
    )),
    ("submission", "投标组织与文件要求", (
        ("是否允许联合体投标", "不允许。"),
        ("是否允许分包", "核心物业服务不得分包。"),
        ("投标文件组成", "资格、商务、技术及报价文件。"),
        ("签字、盖章要求", "法定代表人或授权代表签字并加盖公章。"),
        ("文件格式和份数", "电子文件一套，纸质正本一份、副本四份。"),
        ("电子投标要求", "通过指定电子交易平台加密上传。"),
        ("投标有效期", "自投标截止日起 90 日。"),
        ("现场踏勘及答疑要求", "投标人可自行踏勘，疑问应在截止日前十日提交。"),
        ("投标文件递交方式", "电子文件在线递交。"),
    )),
    ("evaluation", "评标与定标规则", (
        ("资格审查方式", "资格后审。"),
        ("符合性审查内容", "签章、报价、有效期及响应完整性。"),
        ("采用的评标方法", "综合评分法。"),
        ("价格分权重", "20 分。"),
        ("技术分权重", "55 分。"),
        ("商务分权重", "25 分。"),
        ("报价得分计算公式", "满足要求的最低报价为基准价，其他报价按基准价除以投标报价乘价格权重计分。"),
        ("客观评分项", "资质、业绩、人员证书。"),
        ("主观评分项", "服务方案、应急预案及现场管理方案。"),
        ("否决投标情形", "报价超过最高限价或实质性条款未响应。"),
        ("中标候选人确定规则", "按综合得分由高到低推荐前三名。"),
    )),
    ("reference", "客观参考信息", (
        ("招标人及项目业主公开信息", "公开登记状态正常。"),
        ("实际付款主体信息", "由合同所列项目业主支付。"),
        ("历史相似招标项目", "近三年公开过两次同区域物业服务采购。"),
        ("历史中标单位", "公开记录显示由两家物业企业先后承接。"),
        ("历史预算金额", "上一周期预算约 1,180 万元。"),
        ("信息来源及更新时间", "招标公告、企业公开信息，更新于 2026-07-15。"),
    )),
)


def demo_notices() -> list[TenderNotice]:
    """Return the ten deterministic notices displayed for the exact demo query."""

    return [_build_notice(index, project) for index, project in enumerate(_PROJECTS, start=1)]


def demo_notices_for_scheduled_run(
    run_id: str,
) -> tuple[datetime, list[TenderNotice]] | None:
    """Return only notices first seen in one deterministic scheduled run."""

    specification = DEMO_SCHEDULED_RUNS.get(run_id)
    if specification is None:
        return None
    executed_at, notice_indices = specification
    notices = demo_notices()
    return executed_at, [notices[index] for index in notice_indices]


def _build_notice(index: int, project: dict[str, str | None]) -> TenderNotice:
    project_id = str(project["id"])
    title = f"[合成演示] {project['title']}"
    purchaser = "合成演示采购人"
    source_url = f"https://example.invalid/bidradar-demo/{project_id}"
    fetched_at = datetime(2026, 7, 15, 16, 0, tzinfo=_SHANGHAI)
    evidence: list[EvidenceReference] = []

    structured = {
        "opportunity_kind": "招标公告",
        "region": "上海",
        "topic_keywords": "物业管理服务、保洁、设施维护",
        "purchaser": purchaser,
    }
    if project.get("deadline"):
        structured["deadline"] = str(project["deadline"])
    for field_path, quote in structured.items():
        evidence.append(
            EvidenceReference(
                evidence_id=f"demo-{index}-field-{field_path}",
                field_path=field_path,
                source_url=source_url,
                document_name="BidRadar-X 合成演示数据",
                locator="合成演示字段",
                quote=f"合成演示，非真实公告：{field_path}：{quote}",
                fetched_at=fetched_at,
            )
        )

    sections: list[RequirementSection] = []
    for section_id, section_title, fact_defs in _MODULE_FACTS:
        facts: list[RequirementFact] = []
        for fact_index, (label, template) in enumerate(fact_defs, start=1):
            value = template.format(title=title, purchaser=purchaser)
            evidence_id = f"demo-{index}-{section_id}-{fact_index}"
            evidence.append(
                EvidenceReference(
                    evidence_id=evidence_id,
                    field_path=f"requirement_sections.{section_id}.{fact_index}.value",
                    source_url=source_url,
                    document_name="BidRadar-X 合成演示数据",
                    section=section_title,
                    locator=f"合成演示字段/{label}",
                    quote=f"合成演示，非真实公告：{label}：{value}",
                    fetched_at=fetched_at,
                )
            )
            facts.append(RequirementFact(label=label, value=value, evidence_ids=[evidence_id]))
        sections.append(
            RequirementSection(
                section_id=section_id,
                title=section_title,
                summary=f"合成演示模块，共 {len(facts)} 项；不得作为真实公告证据。",
                facts=facts,
            )
        )

    raw_key = f"{title}|{source_url}|{project['published']}"
    return TenderNotice(
        notice_id=f"demo-notice-{project_id}",
        notice_type="tender",
        opportunity_kind="tender",
        title=title,
        published_at=datetime.fromisoformat(str(project["published"])),
        source=SourceRecord(
            source_id=f"demo-source-{project_id}",
            source_name="BidRadar-X 合成演示数据",
            source_url=source_url,
            canonical_notice_url=source_url,
            publication_role="original",
            authority=0.0,
        ),
        core_content="合成演示内容，仅用于验证界面、增量报告和 DOCX 排版，不代表真实公告事实。",
        region="上海",
        topic_keywords=["物业管理服务", "保洁", "设施维护"],
        purchaser=purchaser,
        deadline=(datetime.fromisoformat(str(project["deadline"])) if project.get("deadline") else None),
        raw_content_fingerprint=_fingerprint(f"raw|{raw_key}"),
        notice_stable_fingerprint=_fingerprint(f"notice|{project_id}"),
        project_stable_fingerprint=_fingerprint(f"project|{project_id}"),
        fetched_at=fetched_at,
        evidence=evidence,
        requirement_sections=sections,
    )


def _fingerprint(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()
