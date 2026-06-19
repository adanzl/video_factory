/**
 * 任务 API（占位）
 */
import { api } from "./config";
import type { Job } from "@/types/jobs";

export async function listJobs(): Promise<Job[]> {
  const response = await api.get<{ data?: Job[] }>("/v_factory/api/jobs");
  return response.data?.data ?? [];
}
