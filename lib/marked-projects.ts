export type MarkedProject = {
  id: string;
  title: string;
  region: string;
  hasUpdates: boolean;
  updateTime: string;
  lastUpdatedAt: string;
  frequency: string;
  newItemCount: number;
  filteredDuplicateCount: number;
  summary: string;
  reportHref?: string;
};


export const INITIAL_MARKED_PROJECTS: MarkedProject[] = [
  {
    id: "shanghai-property-service",
    title: "上海市物业管理服务项目",
    region: "上海市",
    hasUpdates: true,
    updateTime: "15日22点",
    lastUpdatedAt: "2026-07-15 22:00",
    frequency: "每天 09:00",
    newItemCount: 2,
    filteredDuplicateCount: 8,
    summary: "本次更新新增老港项目设备维修维护服务和北艾路物业服务两条公告。",
    reportHref: "/reports/demo-shanghai-property",
  },
  {
    id: "tianjin-transit-maintenance",
    title: "天津市轨道交通维护项目",
    region: "天津市",
    hasUpdates: false,
    updateTime: "14日10点",
    lastUpdatedAt: "2026-07-14 10:00",
    frequency: "每周更新",
    newItemCount: 0,
    filteredDuplicateCount: 6,
    summary: "本次抓取结果均已在此前报告中推送，没有生成重复 Word。",
  },
  {
    id: "anhui-server-procurement",
    title: "安徽省高性能服务器项目",
    region: "安徽省",
    hasUpdates: true,
    updateTime: "15日16点",
    lastUpdatedAt: "2026-07-15 16:00",
    frequency: "每天 16:00",
    newItemCount: 1,
    filteredDuplicateCount: 4,
    summary: "检测到一条新的高性能服务器采购公告，已进入本次增量报告。",
  },
];


export function markedProjectStatus(project: MarkedProject): string {
  return project.hasUpdates
    ? `${project.updateTime}更新`
    : `上次更新时间：${project.updateTime}`;
}
