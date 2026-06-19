/**
 * 任务 API（占位）
 */
import { api } from "./config";
import type { Job } from "@/types/jobs";

export async function listJobs(): Promise<Job[]> {
  const response = await api.get<{ data?: Job[] }>("/v_factory/api/jobs");
  return response.data?.data ?? [];
}

export async function cleanJob(jobId: number): Promise<{
  id: number;
  cleaned: boolean;
  media_dir: string;
}> {
  const response = await api.post("/v_factory/api/jobs/clean", { id: jobId });
  return response.data;
}
