/**
 * 任务 API
 */
import { api } from "./config";
import type { JobListItem, ListJobsParams } from "@/types/jobs";

export async function listJobs(params: ListJobsParams = {}): Promise<JobListItem[]> {
  const response = await api.get<JobListItem[]>("/v_factory/api/jobs", { params });
  return Array.isArray(response.data) ? response.data : [];
}

export async function cleanJob(jobId: number): Promise<{
  id: number;
  cleaned: boolean;
  media_dir: string;
}> {
  const response = await api.post("/v_factory/api/jobs/clean", { id: jobId });
  return response.data;
}
