import { api } from "./config";

export type HomeTone = "danger" | "warn";

export interface HomeStat {
  key?: string;
  value: number | string;
  /** 旧接口直接给的展示文案 */
  label?: string;
  tone?: HomeTone;
}

export interface HomeLine {
  title: string;
  code?: string;
  note?: string;
  to: string;
  stage?: string;
  story_type?: string;
  score?: number;
  duration_sec?: number | null;
  providers?: string[];
  account_index?: number | string;
  id?: number;
}

export interface HomeMeter {
  key: "cpu" | "memory" | "disk" | "project" | string;
  value: string | null;
  percent: number;
  note?: string;
  threads?: number;
  state?: "unreadable" | "missing";
}

export interface HomeModule {
  key: string;
  stats: HomeStat[];
  lines: HomeLine[];
}

export interface HomeAlert extends HomeLine {
  module: string;
  tone: HomeTone;
}

export interface HomeProgress {
  key?: string;
  value: number | string;
  /** 旧接口直接给的展示文案，value 里已带单位 */
  label?: string;
}

export interface HomeOverview {
  host: string;
  progress: HomeProgress[];
  meters: HomeMeter[];
  modules: HomeModule[];
  alerts: HomeAlert[];
}

export async function getHomeOverview(): Promise<HomeOverview> {
  const response = await api.get<HomeOverview>("/v_factory/api/home/overview");
  return response.data;
}
