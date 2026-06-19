/**
 * 任务 API
 */
import { api } from "./config";
import type { JobDetail, JobListItem, JobLog, JobSegment, ListJobsParams } from "@/types/jobs";
import type { RunStageActionPayload } from "@/types/jobs/stageAction";

export async function listJobs(params: ListJobsParams = {}): Promise<JobListItem[]> {
  const response = await api.get<JobListItem[]>("/v_factory/api/jobs", { params });
  return Array.isArray(response.data) ? response.data : [];
}

export async function getJob(jobId: number): Promise<JobDetail> {
  const response = await api.get<JobDetail>("/v_factory/api/jobs/get", { params: { id: jobId } });
  return response.data;
}

export async function getJobSegments(jobId: number): Promise<JobSegment[]> {
  const response = await api.get<JobSegment[]>(`/v_factory/api/jobs/${jobId}/segments`);
  return Array.isArray(response.data) ? response.data : [];
}

export async function getJobLogs(jobId: number): Promise<JobLog[]> {
  const response = await api.get<JobLog[]>(`/v_factory/api/jobs/${jobId}/logs`);
  return Array.isArray(response.data) ? response.data : [];
}

export async function updateJob(
  jobId: number,
  data: Partial<Pick<JobDetail, "title" | "skip_publish" | "status">>
): Promise<JobDetail> {
  const response = await api.post<JobDetail>("/v_factory/api/jobs/update", { id: jobId, ...data });
  return response.data;
}

export async function runJobStageAction(
  endpoint: string,
  payload: RunStageActionPayload
): Promise<JobDetail> {
  const response = await api.post<JobDetail>(`/v_factory/api/jobs/${endpoint}`, payload);
  return response.data;
}

export async function cleanJob(jobId: number): Promise<{
  id: number;
  cleaned: boolean;
  media_dir: string;
}> {
  const response = await api.post("/v_factory/api/jobs/clean", { id: jobId });
  return response.data;
}

export async function deleteJob(jobId: number): Promise<{ id: number; deleted: boolean }> {
  const response = await api.post("/v_factory/api/jobs/delete", { id: jobId });
  return response.data;
}
