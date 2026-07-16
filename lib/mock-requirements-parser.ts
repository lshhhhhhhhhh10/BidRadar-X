import type { ProjectProfile } from "@/lib/tender-api";

export type MockRequirementTemplate = {
  id: string;
  name: string;
  description: string;
  rawText: string;
};

export type ParsedRequirementItem = {
  label: string;
  found: boolean;
  value?: string;
  evidence?: string;
};

export type ParsedRequirementModule = {
  id: string;
  title: string;
  englishTitle: string;
  items: ParsedRequirementItem[];
  foundCount: number;
};

type RequirementModuleDefinition = {
  id: string;
  title: string;
  englishTitle: string;
  items: string[];
};

export const REQUIREMENT_MODULES: RequirementModuleDefinition[] = [
  {
    id: "project-procurement",
    title: "项目及采购内容",
    englishTitle: "Project & Procurement",
    items: [
      "招标项目名称",
      "招标人、项目业主、付款主体",
      "项目所属行业",
      "标段或标包划分",
      "采购对象",
      "采购数量或项目规模",
      "主要工作范围",
      "主要交付成果",
      "实施或交付地点",
      "项目预算及最高限价",
    ],
  },
  {
    id: "bidder-qualification",
    title: "投标人资格要求",
    englishTitle: "Bidder Qualification",
    items: [
      "企业性质要求",
      "企业资质及等级要求",
      "行政许可要求",
      "财务状况要求",
      "纳税、社保要求",
      "信用记录要求",
      "类似项目业绩要求",
      "项目负责人要求",
      "项目团队人员要求",
      "是否接受联合体资质",
      "招标文件明确规定的其他资格条件",
    ],
  },
  {
    id: "technical-service",
    title: "技术与服务要求",
    englishTitle: "Technical & Service",
    items: [
      "核心技术参数",
      "产品、工程或服务标准",
      "功能要求",
      "性能指标",
      "人员配置要求",
      "设备和场地要求",
      "安全、环保要求",
      "数据安全及保密要求",
      "样品、测试、演示要求",
      "培训、售后及运维要求",
    ],
  },
  {
    id: "timeline-acceptance",
    title: "项目周期与验收要求",
    englishTitle: "Timeline & Acceptance",
    items: [
      "合同履行期限",
      "开工、实施或供货时间",
      "主要阶段和里程碑",
      "分阶段交付要求",
      "最终交付时间",
      "驻场要求",
      "验收主体",
      "验收程序",
      "验收标准",
      "质保期及售后期限",
    ],
  },
  {
    id: "pricing-payment",
    title: "报价、付款与保证金",
    englishTitle: "Pricing & Payment",
    items: [
      "项目预算",
      "最高投标限价",
      "报价方式",
      "报价包含的费用",
      "税率及发票要求",
      "预付款安排",
      "进度款支付节点",
      "验收款及尾款支付条件",
      "质保金比例及返还条件",
      "投标保证金",
      "履约保证金",
      "保函或保证保险要求",
      "价格调整规则",
    ],
  },
  {
    id: "bidding-documents",
    title: "投标组织与文件要求",
    englishTitle: "Bidding Org & Documents",
    items: [
      "是否允许联合体投标",
      "联合体成员数量和牵头方要求",
      "是否允许分包",
      "可分包的内容和比例",
      "是否允许备选方案",
      "投标文件组成",
      "签字、盖章要求",
      "文件格式和份数",
      "电子投标要求",
      "投标有效期",
      "现场踏勘及答疑要求",
      "投标文件递交方式",
    ],
  },
  {
    id: "evaluation-award",
    title: "评标与定标规则",
    englishTitle: "Evaluation & Award Criteria",
    items: [
      "资格审查方式",
      "符合性审查内容",
      "采用的评标方法",
      "价格分权重",
      "技术分权重",
      "商务分权重",
      "报价得分计算公式",
      "客观评分项",
      "主观评分项",
      "加分条件",
      "扣分条件",
      "异常低价处理规则",
      "否决投标情形",
      "中标候选人确定规则",
    ],
  },
  {
    id: "objective-references",
    title: "客观参考信息",
    englishTitle: "Objective References",
    items: [
      "招标人及项目业主公开信息",
      "实际付款主体信息",
      "历史相似招标项目",
      "历史中标单位",
      "历史预算金额",
      "历史中标金额",
      "历史中标折扣率",
      "公开的司法案件",
      "公开的被执行记录",
      "公开的行政处罚",
      "信息来源及更新时间",
    ],
  },
];

const ITEM_ALIASES: Record<string, string[]> = {
  "招标人、项目业主、付款主体": ["招标人", "项目业主", "付款主体"],
  "纳税、社保要求": ["纳税", "社保"],
  "安全、环保要求": ["安全要求", "环保要求"],
  "项目预算及最高限价": ["预算及最高限价"],
  "开工、实施或供货时间": ["实施时间", "供货时间", "开工时间"],
};

/**
 * A deterministic browser-side stand-in for LLM extraction. Each field is
 * independently matched, then the nearest source clause becomes its evidence.
 */
export function parseMockRequirements(rawText: string): ParsedRequirementModule[] {
  const clauses = rawText
    .split(/[。；\n]+/)
    .map((clause) => clause.trim())
    .filter(Boolean);

  return REQUIREMENT_MODULES.map((module) => {
    const items = module.items.map((label) => {
      const keywords = [label, ...(ITEM_ALIASES[label] ?? [])];
      const evidence = clauses.find(
        (clause) =>
          !clause.includes("[原文未提及]") &&
          keywords.some((keyword) => clause.includes(keyword)),
      );
      if (!evidence) return { label, found: false };

      const matchedKeyword = keywords.find((keyword) => evidence.includes(keyword)) ?? label;
      const colonIndex = evidence.search(/[：:]/);
      const value = colonIndex >= 0 && evidence.slice(0, colonIndex).includes(matchedKeyword)
        ? evidence.slice(colonIndex + 1).trim()
        : evidence;

      return { label, found: true, value: value || evidence, evidence };
    });

    return {
      ...module,
      items,
      foundCount: items.filter((item) => item.found).length,
    };
  });
}

function createProjectScenarioTemplates(project: ProjectProfile): MockRequirementTemplate[] {
  const purchaser = project.purchaser || "采购人详见原公告";
  const projectName = project.title;

  return [
    {
      id: "property-service",
      name: "项目 A · 物业综合服务",
      description: "服务、人员、付款及评标条款较完整，部分历史信息未披露。",
      rawText: `
招标项目名称：${projectName}。
招标人、项目业主、付款主体：${purchaser}，项目业主与付款主体一致。
项目所属行业：物业管理与综合服务。采购对象：园区物业客服、保洁、秩序及设施维护服务。
采购数量或项目规模：服务建筑面积约 12.8 万平方米。主要工作范围：客服接待、环境保洁、秩序维护、设施设备巡检。
主要交付成果：月度服务报告、巡检记录和年度总结。实施或交付地点：上海市项目现场。
项目预算及最高限价：预算人民币 1,280 万元，最高限价人民币 1,250 万元。
企业性质要求：中华人民共和国境内依法注册的独立法人。企业资质及等级要求：具有物业服务履约能力及有效质量管理体系认证。
财务状况要求：近三年财务状况良好。纳税、社保要求：提供近六个月依法纳税及缴纳社会保障资金证明。
信用记录要求：未被列入失信被执行人及重大税收违法失信主体。类似项目业绩要求：近三年完成两个单项合同 500 万元以上同类项目。
项目负责人要求：具有五年以上物业项目管理经验。项目团队人员要求：项目团队不少于 45 人，关键岗位持证上岗。
是否接受联合体资质：不接受。招标文件明确规定的其他资格条件：单位负责人相同的不同单位不得同时投标。
核心技术参数：重点设备完好率不低于 98%，报修响应时间不超过 15 分钟。产品、工程或服务标准：执行国家及上海市物业管理服务标准。
功能要求：建立 7×24 小时客服与工单闭环。性能指标：月度服务满意度不低于 90%。
人员配置要求：项目经理 1 名、工程人员 8 名、客服及保洁人员按排班配置。设备和场地要求：自备巡检工具并设置现场项目办公室。
安全、环保要求：落实安全生产责任制并使用环保清洁剂。数据安全及保密要求：项目资料不得向第三方披露。
培训、售后及运维要求：每季度组织岗位培训并持续提供设施运维服务。
合同履行期限：自合同签订之日起 24 个月。开工、实施或供货时间：合同生效后 10 日内进场。
主要阶段和里程碑：首月完成接管验收，第二月进入稳定运营。驻场要求：项目经理及核心团队全周期驻场。
验收主体：招标人与项目业主共同验收。验收程序：按月考核、季度复核、年度总评。
验收标准：依据招标文件服务指标及考核表验收。质保期及售后期限：设施维修成果质保 12 个月。
项目预算：人民币 1,280 万元。最高投标限价：人民币 1,250 万元。报价方式：固定总价报价。
报价包含的费用：人员、材料、设备、保险、税费及管理费用。税率及发票要求：开具符合国家规定的增值税专用发票。
进度款支付节点：按月考核合格后支付当月服务费。验收款及尾款支付条件：年度验收通过后支付至结算价的 97%。
质保金比例及返还条件：结算价的 3%，质保期满无息返还。投标保证金：人民币 20 万元。履约保证金：合同金额的 5%。
是否允许联合体投标：不允许。是否允许分包：核心物业服务不得分包。投标文件组成：资格、商务、技术及报价文件。
签字、盖章要求：法定代表人或授权代表签字并加盖公章。文件格式和份数：电子文件一套，纸质正本一份、副本四份。
电子投标要求：通过指定电子交易平台加密上传。投标有效期：自投标截止日起 90 日。
现场踏勘及答疑要求：投标人可自行踏勘，疑问应在截止日前十日提交。投标文件递交方式：电子文件在线递交。
资格审查方式：资格后审。符合性审查内容：签章、报价、有效期及响应完整性。
采用的评标方法：综合评分法。价格分权重：20 分。技术分权重：55 分。商务分权重：25 分。
报价得分计算公式：满足要求的最低报价为基准价，其他报价按基准价除以投标报价乘价格权重计分。
客观评分项：资质、业绩、人员证书。主观评分项：服务方案、应急预案及现场管理方案。
否决投标情形：报价超过最高限价或实质性条款未响应。中标候选人确定规则：按综合得分由高到低推荐前三名。
招标人及项目业主公开信息：公开登记状态正常。实际付款主体信息：由合同所列项目业主支付。
历史相似招标项目：近三年公开过两次同区域物业服务采购。历史中标单位：公开记录显示由两家物业企业先后承接。
历史预算金额：上一周期预算约 1,180 万元。信息来源及更新时间：招标公告、企业公开信息，更新于 2026-07-15。
      `.trim(),
    },
    {
      id: "strict-qualification",
      name: "项目 B · 严格资格审查",
      description: "突出企业、人员和文件合规要求，不提供历史参考数据。",
      rawText: `
招标项目名称：${projectName}。招标人、项目业主、付款主体：${purchaser}。
标段或标包划分：本项目划分为一个标包。采购对象：专业设施运维服务。主要工作范围：设施巡检、维修和应急保障。
企业性质要求：须为境内独立法人。企业资质及等级要求：具有建筑机电安装工程专业承包二级及以上资质。
行政许可要求：具有有效安全生产许可证。财务状况要求：最近三年连续盈利且资产负债率不高于 70%。
纳税、社保要求：提供连续十二个月纳税及社保记录。信用记录要求：三年内无重大违法记录。
类似项目业绩要求：五年内完成三个公共建筑运维项目。项目负责人要求：具备一级注册建造师及安全 B 证。
项目团队人员要求：技术负责人具有高级职称，专职安全员不少于两名。是否接受联合体资质：不接受。
招标文件明确规定的其他资格条件：不得存在控股、管理关系的不同投标人同时参与。
人员配置要求：关键岗位人员须提供劳动合同和社保证明。安全、环保要求：执行安全生产标准化管理。
合同履行期限：合同签订后 18 个月。验收标准：按月度运维考核得分进行验收。
项目预算：人民币 860 万元。最高投标限价：人民币 820 万元。报价方式：综合单价与总价同时报价。
投标保证金：人民币 10 万元。履约保证金：中标合同金额的 8%。保函或保证保险要求：可采用银行保函。
是否允许联合体投标：不允许。是否允许分包：未经招标人书面批准不得分包。是否允许备选方案：不允许。
投标文件组成：资格证明、商务响应、技术方案及报价清单。签字、盖章要求：所有指定位置须签字盖章。
电子投标要求：使用 CA 证书签章并加密上传。投标有效期：120 日。投标文件递交方式：电子交易系统递交。
资格审查方式：资格后审。符合性审查内容：投标主体、授权、保证金和实质性响应。
采用的评标方法：综合评分法。价格分权重：15 分。技术分权重：45 分。商务分权重：40 分。
客观评分项：资质等级、认证、业绩及人员证书。主观评分项：运维组织方案和风险控制方案。
异常低价处理规则：低于有效报价平均值 80% 时须作出书面说明。否决投标情形：资格证明无效或拒绝澄清。
中标候选人确定规则：推荐综合得分最高的三名投标人为候选人。
      `.trim(),
    },
    {
      id: "technical-delivery",
      name: "项目 C · 技术交付优先",
      description: "突出技术、里程碑与验收，组织和历史类条款大量缺失。",
      rawText: `
招标项目名称：${projectName}。项目所属行业：数字化物业与设施管理。
采购对象：智慧物业工单与设备巡检平台。采购数量或项目规模：一个管理平台、三个移动端应用和 120 个设备接入点。
主要工作范围：系统设计、开发、部署、数据迁移和运维。主要交付成果：软件平台、接口文档、测试报告和用户手册。
实施或交付地点：上海市招标人指定机房。项目预算及最高限价：预算及最高限价均为人民币 460 万元。
核心技术参数：支持不少于 500 个并发用户，接口平均响应时间小于两秒。产品、工程或服务标准：遵循国家网络安全等级保护要求。
功能要求：实现报修、派单、巡检、统计分析和移动审批。性能指标：系统全年可用性不低于 99.9%。
人员配置要求：配置项目经理、架构师、测试和实施工程师。设备和场地要求：适配现有服务器及指定私有云环境。
安全、环保要求：施工期间执行机房安全管理制度。数据安全及保密要求：数据境内存储，敏感字段加密，人员签署保密承诺。
样品、测试、演示要求：投标现场完成核心流程演示，中标后通过第三方安全测试。培训、售后及运维要求：提供管理员培训及三年免费运维。
合同履行期限：九个月。开工、实施或供货时间：合同签订后五个工作日启动。
主要阶段和里程碑：第一个月完成蓝图，第四个月完成开发，第七个月试运行。分阶段交付要求：按蓝图、测试版、正式版三阶段交付。
最终交付时间：合同生效后第九个月。驻场要求：实施阶段至少两名工程师驻场。
验收主体：招标人信息部门及使用部门。验收程序：初验、试运行、终验。验收标准：功能通过率 100%，重大缺陷清零。
质保期及售后期限：终验后 36 个月。最高投标限价：人民币 460 万元。报价方式：总价包干。
报价包含的费用：软件、实施、接口、测试、培训及三年运维。税率及发票要求：开具增值税专用发票。
进度款支付节点：蓝图确认支付 20%，上线支付 40%。验收款及尾款支付条件：终验后支付 30%，质保期满支付 10%。
投标文件组成：商务文件、技术方案、演示材料和报价表。电子投标要求：在线上传加密投标文件。
投标有效期：90 日。投标文件递交方式：指定电子采购平台递交。
采用的评标方法：综合评分法。价格分权重：10 分。技术分权重：70 分。商务分权重：20 分。
主观评分项：总体架构、实施方案、演示效果。否决投标情形：核心参数负偏离或未参加现场演示。
信息来源及更新时间：项目招标文件模拟文本，更新于 2026-07-15。
      `.trim(),
    },
  ];
}

/**
 * Turns the complete mock source into eight module-specific source views.
 * Every line corresponds to exactly one field in the selected module.
 */
export function createRequirementTemplates(project: ProjectProfile): MockRequirementTemplate[] {
  const completeSource = createProjectScenarioTemplates(project)[0]?.rawText ?? "";
  const sourceClauses = completeSource
    .split(/[。；\n]+/)
    .map((clause) => clause.trim())
    .filter(Boolean);

  return REQUIREMENT_MODULES.map((module, moduleIndex) => {
    let foundCount = 0;
    const lines = module.items.map((label) => {
      const keywords = [label, ...(ITEM_ALIASES[label] ?? [])];
      const evidence = sourceClauses.find((clause) =>
        keywords.some((keyword) => clause.includes(keyword)),
      );

      if (!evidence) return `${label}：[原文未提及]`;
      foundCount += 1;
      const colonIndex = evidence.search(/[：:]/);
      const originalValue = evidence.startsWith(label) && colonIndex >= 0
        ? evidence.slice(colonIndex + 1).trim()
        : evidence;
      return `${label}：${originalValue}`;
    });

    return {
      id: module.id,
      name: `模块 ${moduleIndex + 1} · ${module.title}`,
      description: `${module.englishTitle} · ${foundCount}/${module.items.length} 项原文提及`,
      rawText: lines.join("\n"),
    };
  });
}
