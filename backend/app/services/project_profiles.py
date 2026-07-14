from __future__ import annotations

from typing import Any


def _money(value: int | float | None) -> str:
    if value is None:
        return "招标文件未明确"
    return f"人民币 {value / 10000:.0f} 万元"


def _fact(label: str, value: str, source: str) -> dict[str, str]:
    return {"label": label, "value": value, "source": source}


def build_project_profiles(state: dict[str, Any]) -> list[dict[str, Any]]:
    analyses = {item["project_id"]: item for item in state.get("analysis", [])}
    return [
        _build_profile(state["run_id"], project, analyses.get(project["project_id"], {}))
        for project in state["projects"]
    ]


def _build_profile(run_id: str, project: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    primary = project["documents"][0]
    title = project["title"]
    purchaser = project.get("purchaser") or "采购人未披露"
    budget = _money(primary.get("budget"))
    deadline = primary.get("deadline", "招标文件未明确")
    source = f"{primary.get('source_name', '原始公告')} · 招标文件第 1 页（模拟证据）"
    project_kind = "GPU服务器" if "GPU" in title else "存储服务器" if "存储" in title else "高性能服务器"

    modules = [
        {
            "id": "procurement",
            "title": "项目及采购内容",
            "summary": f"{purchaser}拟采购{project_kind}及配套软硬件，控制预算为{budget}。",
            "facts": [
                _fact("背景目标", f"为{purchaser}补充计算与存储能力，建设可交付、可验收的服务器基础环境。", source),
                _fact("工作范围与责任边界", "中标方负责供货、运输、安装、调试、测试和技术培训；甲方负责机房、电源及网络接入条件。", source),
                _fact("甲方提供条件", "标准机柜位置、双路电源、管理网络地址及现场协调窗口。", source),
                _fact("中标方工作", "完成设备到货、上架布线、系统部署、性能测试、资料移交和人员培训。", source),
                _fact("不包含内容", "不含机房土建改造、外部专线租赁及甲方既有业务系统改造。", source),
            ],
            "tables": [
                {
                    "title": "完整采购清单与标段内容",
                    "columns": ["标段", "名称", "数量", "单位", "交付成果", "格式"],
                    "rows": [
                        ["第1标段", project_kind, "4", "台", "设备及序列号清单", "XLSX/PDF"],
                        ["第1标段", "高速网络交换设备", "2", "台", "网络拓扑与配置备份", "PDF/配置文件"],
                        ["第1标段", "部署与培训服务", "1", "项", "实施报告、测试报告、培训记录", "DOCX/PDF"],
                    ],
                }
            ],
        },
        {
            "id": "qualification",
            "title": "投标人资格要求",
            "summary": "逐条展示主体资格、财务社保、类似业绩、团队和禁止投标情形，仅陈列甲方原文要求。",
            "facts": [
                _fact("资格要求原文", "投标人须为依法注册并有效存续的独立法人，能够独立承担民事责任。", source),
                _fact("资质名称与等级", "电子与智能化工程专业承包二级及以上；证书须在投标截止日有效。", source),
                _fact("颁发机构", "省级及以上住房和城乡建设主管部门。", source),
                _fact("成立年限与注册资本", "成立满3年；注册资本不低于人民币1000万元。", source),
                _fact("财务与审计报告", "提供2023—2025年度经审计财务报告。", source),
                _fact("纳税与社保证明", "提供近6个月任意连续3个月依法纳税及社保缴纳证明。", source),
                _fact("类似业绩", "近3年完成不少于2项单项合同额200万元以上服务器或数据中心项目。", source),
                _fact("项目负责人要求", "具备信息系统项目管理师或同等级证书，并提供本单位社保证明。", source),
                _fact("团队要求", "项目经理1名、系统工程师2名、网络工程师1名。", source),
                _fact("禁止投标情形", "被列入失信被执行人、重大税收违法失信主体或政府采购严重违法失信名单的不得参与。", source),
                _fact("对应证明材料与标段", "营业执照、资质证书、审计报告、纳税社保、合同及验收证明；适用于第1标段。", source),
            ],
            "tables": [],
        },
        {
            "id": "technical",
            "title": "技术与服务要求",
            "summary": "型号规格、兼容性、功能、驻场、测试运维和售后要求按参数表呈现。",
            "facts": [],
            "tables": [
                {
                    "title": "技术参数矩阵",
                    "columns": ["序号", "项目", "甲方要求值", "是否明确为强制项", "证明材料原文位置"],
                    "rows": [
                        ["1", "型号规格与材质", "2U机架式，双路处理器，冗余电源，导轨齐全", "是（原文使用“必须”）", source],
                        ["2", "国家/行业标准", "符合GB/T 9813.3及相关信息安全标准", "否", source],
                        ["3", "兼容性", "必须兼容甲方现有虚拟化平台和统一监控系统", "是（原文使用“必须”）", source],
                        ["4", "软硬件功能", "远程管理、故障告警、日志审计、批量部署", "否", source],
                        ["5", "人员驻场", "实施期至少2名工程师驻场", "否", source],
                        ["6", "样品提交", "投标阶段无需样品，中标后提供配置确认单", "否", source],
                        ["7", "测试与运维", "连续72小时压力测试，不得偏离验收基线", "是（原文使用“不得偏离”）", source],
                        ["8", "售后响应", "7×24小时受理，2小时响应，4小时到场", "否", source],
                        ["9", "保密与安全", "实施人员须签署保密承诺，配置数据不得外传", "否", source],
                    ],
                }
            ],
        },
        {
            "id": "timeline",
            "title": "项目周期与验收要求",
            "summary": f"合同生效后45日内完成供货与部署，投标截止时间为{deadline}。",
            "facts": [
                _fact("合同签订与开始条件", "中标通知书发出后30日内签订合同；收到甲方书面开工通知后开始。", source),
                _fact("总工期", "45个日历日。", source),
                _fact("阶段时刻表与交付物", "第10日完成深化设计；第25日到货；第38日完成安装调试；第45日提交验收。", source),
                _fact("驻场、交货与运输", "实施期工作日驻场；设备运至甲方指定机房，运输及保险由中标方承担。", source),
                _fact("安装调试", "完成上架、布线、固件升级、系统部署和联调。", source),
                _fact("初验与终验条件", "到货清点及开机测试通过后初验；稳定运行30日且问题闭环后终验。", source),
                _fact("验收资料清单", "到货清单、合格证、配置表、测试报告、培训记录、竣工图和保修承诺。", source),
                _fact("指标方法与不合格处理", "按技术参数逐项测试；不合格项限期整改，复验仍不合格按合同处理。", source),
                _fact("质保服务", "整机原厂质保3年，质保期自终验合格之日起计算。", source),
            ],
            "tables": [],
        },
        {
            "id": "commercial",
            "title": "报价、付款与保证金",
            "summary": f"最高限价为{budget}，报价覆盖设备、实施、税费、运输、培训和质保。",
            "facts": [
                _fact("控制价/最高限价", budget, source),
                _fact("单价、总价与费率", "采用人民币含税总价报价，同时列明设备单价和服务费，不接受选择性报价。", source),
                _fact("暂估/暂列金额", "本模拟项目无暂估价；暂列金额为合同含税价的3%。", source),
                _fact("所含与不准计入费用", "包含设备、软件许可、运输、保险、安装、测试、培训和税费；不得另计差旅及现场服务费。", source),
                _fact("税率与发票", "提供增值税专用发票，适用税率按国家现行规定执行。", source),
                _fact("付款节点", "到货初验后支付50%；终验后支付45%；质保期满后支付5%。", source),
                _fact("审计/财政拨款前提", "最终结算以甲方审计确认金额为准；付款进度受财政拨款时间影响。", source),
                _fact("质保金", "合同价5%，可用等额质量保函替代，质保期满且无未结问题后返还。", source),
                _fact("投标/履约保证金", "投标保证金5万元，未中标后退还；履约保证金为合同价5%，支持银行保函。", source),
            ],
            "tables": [],
        },
        {
            "id": "submission",
            "title": "投标组织与文件要求",
            "summary": "汇总联合体、分包、标书获取、提问踏勘、文件编制与递交安排。",
            "facts": [
                _fact("联合体与分包", "不接受联合体投标；主体设备及核心实施工作不得转包，专业配套服务须经甲方书面同意。", source),
                _fact("获取标书方式", "登录发布平台免费下载电子招标文件。", source),
                _fact("提问截止与踏勘", "提问截止为投标截止前10日；不组织统一踏勘，投标人可预约现场查看。", source),
                _fact("标书目录", "商务册、技术册、报价册分别编制并建立连续目录。", source),
                _fact("证明材料与签章", "资格及业绩证明须加盖公章；法定代表人授权书须签字盖章。", source),
                _fact("正副本份数", "纸质正本1份、副本4份，另附加密电子文件1份。", source),
                _fact("命名/上传/密封/递交", "文件以项目编号+投标人简称命名；电子版上传平台，纸质文件分别密封。", source),
                _fact("截标与开标", f"投标截止及开标时间：{deadline}；地点以平台开标通知为准。", source),
            ],
            "tables": [],
        },
        {
            "id": "evaluation",
            "title": "评标与定标规则",
            "summary": "客观呈现资格审查、评分分值、价格公式、异常低价及中标确定方式。",
            "facts": [
                _fact("资审/符合性项目", "营业执照、授权代表、保证金、签章、报价唯一性及实质性技术条款逐项审查。", source),
                _fact("价格公式与基准价", "价格分=30×评标基准价/有效投标报价；基准价为满足文件要求的最低有效报价。", source),
                _fact("偏差扣分", "一般技术参数每负偏离1项扣1分，最多扣10分；实质性要求负偏离作无效投标处理。", source),
                _fact("业绩证书与演示答辩", "业绩须提供合同及验收证明；现场演示按功能清单计分，不接受预录视频替代。", source),
                _fact("异常低价与废标", "报价明显低于成本时要求书面说明；无法合理说明的可否决。串标、虚假材料等作废标处理。", source),
                _fact("同分排序与定标", "总分相同按报价、技术、商务得分顺序排序；推荐排名第一者为中标候选人。", source),
            ],
            "tables": [
                {
                    "title": "评分标准",
                    "columns": ["评分类别", "评分项目", "分值", "甲方评分标准", "所需证明材料原文位置"],
                    "rows": [
                        ["商务", "类似项目业绩", "10", "每提供1项有效类似业绩得2分，最高10分", source],
                        ["技术", "技术参数响应", "35", "完全满足得35分，一般项负偏离按项扣分", source],
                        ["技术", "实施与售后方案", "15", "按实施计划、人员、测试和响应方案综合评分", source],
                        ["价格", "投标报价", "30", "按价格公式计算", source],
                        ["服务", "演示与答辩", "10", "按现场功能演示和项目经理答辩评分", source],
                    ],
                }
            ],
        },
        {
            "id": "reference",
            "title": "客观参考信息",
            "summary": "仅展示公开登记、历史项目、司法与行政公开记录及数据更新时间，不作评价。",
            "facts": [
                _fact("招标人登记信息", f"主体：{purchaser}；统一社会信用代码：91340000SIMU2026X（模拟）；登记状态：存续。", source),
                _fact("公开司法案件与案号", "公开检索到合同纠纷案件1件：（2025）皖01民初1001号；仅作事实陈列。", source),
                _fact("公开被执行", "本次模拟数据未检索到公开被执行记录。", source),
                _fact("公开行政处罚", "本次模拟数据未检索到公开行政处罚记录。", source),
                _fact("数据来源与更新时间", f"公告来源：{primary.get('url')}；登记信息为模拟公开数据；更新于2026-07-13 20:00。", source),
            ],
            "tables": [
                {
                    "title": "历史相似项目",
                    "columns": ["名称", "公告时间", "地点", "规模", "控制价", "投标单位", "中标单位", "金额/折扣率", "期限"],
                    "rows": [
                        ["2025年计算平台扩容项目", "2025-05-18", "安徽省合肥市", "服务器6台", "480万元", "4家", "安徽示例科技有限公司", "452万元 / 94.2%", "60日"],
                        ["2024年存储设备更新项目", "2024-08-06", "安徽省芜湖市", "存储节点4台", "210万元", "3家", "合肥示例信息有限公司", "198万元 / 94.3%", "45日"],
                    ],
                }
            ],
        },
    ]

    return {
        "run_id": run_id,
        "project_id": project["project_id"],
        "project_code": project.get("project_code"),
        "title": title,
        "purchaser": purchaser,
        "published_at": primary.get("published_at", ""),
        "url": primary.get("url", ""),
        "source_name": primary.get("source_name", ""),
        "budget": primary.get("budget"),
        "deadline": deadline,
        "summary": analysis.get("summary") or primary.get("content", "")[:160],
        "evidence_count": len(analysis.get("evidence_ids", [])),
        "modules": modules,
    }
