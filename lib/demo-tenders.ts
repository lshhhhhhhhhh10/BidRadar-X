import type { ExtractedFields, ProjectSummary, ReportView, RunSummary } from "@/lib/tender-api";


export const SHANGHAI_PROPERTY_DEMO_ID = "shanghai-property";
export const SHANGHAI_PROPERTY_DEMO_QUERY = "上海市物业管理服务项目";
export const SHANGHAI_PROPERTY_DEMO_VERIFIED_AT = "2026-07-15";

export const SHANGHAI_PROPERTY_DEMO_FIELDS: ExtractedFields = {
  subject: "物业管理服务项目",
  region: "上海",
  time: "无",
  frequency: "每天9：00",
};

export function isShanghaiPropertyDemoQuery(value: string): boolean {
  const normalizedInput = value.replace(/\s+/g, "");
  return normalizedInput.includes(SHANGHAI_PROPERTY_DEMO_QUERY);
}

export const SHANGHAI_PROPERTY_DEMO_RUN: RunSummary = {
  task_id: "demo-shanghai-property",
  run_id: "demo-20260715-shanghai-property",
  query: SHANGHAI_PROPERTY_DEMO_QUERY,
  frequency: "once",
  status: "completed",
  project_count: 10,
};

export const SHANGHAI_PROPERTY_DEMO_REPORT: ReportView = {
  status: "available",
  delivery_type: "full_snapshot",
  report_scope: "full",
  notice_count: 10,
  filename: "上海市物业管理服务项目_生成时间.docx",
  download_url: "/api/demo/reports/shanghai-property/download",
};

export const SHANGHAI_PROPERTY_DEMO_PROJECTS: ProjectSummary[] = [
  demoProject({
    id: "ceb-property-customer-maintenance",
    title: "物业客服服务和物业设施日常维护服务公开招标公告",
    publishedAt: "2026-06-29",
    deadline: "2026-07-21T09:30:00+08:00",
    url: "https://ctbpsp.com/#/bulletinDetail?uuid=d873e74ca5944cc09d026f673eeb66a3&inpvalue=&dataSource=0&tenderAgency=",
    sourceName: "中国招标投标公共服务平台",
    summary: "物业客服及设施日常维护服务，平台公告状态及开标时间已核验。",
  }),
  demoProject({
    id: "ceb-yard-cleaning-materials",
    title: "128号大院物业保洁物料费项目公开招标公告",
    publishedAt: "2026-07-13",
    deadline: "2026-08-03T10:00:00+08:00",
    url: "https://ctbpsp.com/#/bulletinDetail?uuid=8a9494859e5d0b9e019f5947e16f3ea5&inpvalue=&dataSource=0&tenderAgency=",
    sourceName: "中国招标投标公共服务平台",
    summary: "大院物业保洁物料服务公开招标，公告 UUID 与开标时间已核验。",
  }),
  demoProject({
    id: "ceb-jiangyang-cleaning",
    title: "上海江杨农产品市场保洁服务项目（东区清扫保洁）招标公告",
    publishedAt: "2026-07-02",
    deadline: "2026-07-23T14:00:00+08:00",
    url: "https://ctbpsp.com/#/bulletinDetail?uuid=8a9c96a69f20205a019f20948c64138f&inpvalue=&dataSource=0&tenderAgency=",
    sourceName: "中国招标投标公共服务平台",
    summary: "农产品市场东区清扫保洁服务，公告地区、标题及开标时间已核验。",
  }),
  demoProject({
    id: "ceb-wangnibang-cleaning",
    title: "王泥浜村保洁服务公开招标公告",
    publishedAt: "2026-07-03",
    deadline: "2026-07-24T14:00:00+08:00",
    url: "https://ctbpsp.com/#/bulletinDetail?uuid=8a9c96a69f26595d019f2715ada76a14&inpvalue=&dataSource=0&tenderAgency=",
    sourceName: "中国招标投标公共服务平台",
    summary: "村域保洁服务公开招标，公告 UUID 与开标时间已核验。",
  }),
  demoProject({
    id: "ceb-vehicle-cleaning",
    title: "营运车辆保洁外包服务项目招标公告",
    publishedAt: "2026-07-06",
    deadline: "2026-07-23T09:00:00+08:00",
    url: "https://ctbpsp.com/#/bulletinDetail?uuid=8a9c96a69f34b9c6019f35c9261e507b&inpvalue=&dataSource=0&tenderAgency=",
    sourceName: "中国招标投标公共服务平台",
    summary: "营运车辆日常保洁外包服务，公告地区与开标时间已核验。",
  }),
  demoProject({
    id: "ceb-caohan-green-maintenance",
    title: "关于上海碳谷绿湾产业园（漕泾片区）绿化养护服务项目的招标公告",
    publishedAt: "2026-07-13",
    deadline: "2026-08-05T14:00:00+08:00",
    url: "https://ctbpsp.com/#/bulletinDetail?uuid=8a9c96a69f59d8f6019f5a3b3adc2421&inpvalue=&dataSource=0&tenderAgency=",
    sourceName: "中国招标投标公共服务平台",
    summary: "产业园区绿化养护服务，属于物业综合服务的设施环境维护范围。",
  }),
  demoProject({
    id: "ceb-jinshan-green-maintenance",
    title: "上海碳谷绿湾产业园（金山卫片区）河道绿化养护服务项目招标公告",
    publishedAt: "2026-07-13",
    deadline: "2026-08-04T13:30:00+08:00",
    url: "https://ctbpsp.com/#/bulletinDetail?uuid=8a9c96a69f59d8f6019f5a94d0c06ac0&inpvalue=&dataSource=0&tenderAgency=",
    sourceName: "中国招标投标公共服务平台",
    summary: "产业园区河道及绿化养护服务，公告与开标时间已核验。",
  }),
  demoProject({
    id: "ceb-laogang-maintenance",
    title: "老港项目设备维修、维护服务招标公告",
    publishedAt: "2026-07-15",
    deadline: "2026-07-27T10:00:00+08:00",
    url: "https://ctbpsp.com/#/bulletinDetail?uuid=8a9494849e5d0d8a019f636425b474ea&inpvalue=&dataSource=0&tenderAgency=",
    sourceName: "中国招标投标公共服务平台",
    summary: "项目设施设备维修维护服务，属于物业设施运维相关招标。",
  }),
  demoProject({
    id: "shggzy-beiai-property",
    title: "北艾路1400号物业服务费的公开招标公告",
    publishedAt: "2026-07-15",
    url: "https://www.shggzy.com/jyxxzcgg/8962193?isIndex=y",
    sourceName: "上海市公共资源交易平台",
    summary: "上海官方政府采购频道公开招标公告，原公告编号及链接已核验。",
  }),
  demoProject({
    id: "jianyu-wanan-cleaning",
    title: "2026-2027年万安1-3期营销区域客服及保洁服务项目公开招标公告",
    publishedAt: "2026-07-02",
    deadline: "2026-07-22T14:00:00+08:00",
    url: "https://shanghai.jianyu360.cn/jybx/20260702_26070166411730.html",
    sourceName: "剑鱼标讯",
    purchaser: "森兰联行（上海）企业发展有限公司",
    summary: "营销区域日常保洁、客服礼宾服务，招标编号采招2026-1626。",
  }),
];


function demoProject(input: {
  id: string;
  title: string;
  publishedAt: string;
  deadline?: string;
  url: string;
  sourceName: string;
  purchaser?: string;
  summary: string;
}): ProjectSummary {
  const { id, title, publishedAt, deadline } = input;
  return {
    run_id: SHANGHAI_PROPERTY_DEMO_RUN.run_id,
    project_id: `demo-${id}`,
    title: `[合成演示] ${title}`,
    purchaser: "合成演示采购人",
    published_at: `${publishedAt}T00:00:00+08:00`,
    url: `https://example.invalid/bidradar-demo/${id}`,
    source_name: "BidRadar-X 合成演示数据",
    deadline,
    summary: "合成演示内容，仅用于验证界面、增量识别和报告排版，不代表真实公告事实。",
    evidence_count: 3,
    module_count: 0,
  };
}
