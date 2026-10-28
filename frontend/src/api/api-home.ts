import { api } from "./config";

export type HomeTone = "danger" | "warn";

export interface HomeStat {
  label: string;
  value: number | string;
  tone?: HomeTone;
}

export interface HomeLine {
  title: string;
  note: string;
  tone?: HomeTone;
  to: string;
}

export interface HomeMeter {
  key: "cpu" | "memory" | "disk" | string;
  value: string;
  percent: number;
  note: string;
}

export interface HomeModule {
  key: string;
  stats: HomeStat[];
  lines: HomeLine[];
}

export interface HomeAlert {
  module: string;
  title: string;
  note: string;
  tone: HomeTone;
  to: string;
}

export interface HomeProgress {
  label: string;
  value: string;
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
