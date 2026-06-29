/**
 * 任务 API
 */
import { api } from "./config";
import type {
  CreateJobParams,
  JobDetail,
  JobListItem,
  JobLog,
  JobSegment,
  ListJobsParams,
  UpdateJobInfoParams,
} from "@/types/jobs";
import type { RunStageActionPayload, PreviewScriptPromptsPayload } from "@/types/jobs/stageAction";
import type { LlmPromptStep } from "@/types/jobs/script";

export async function listJobs(params: ListJobsParams = {}): Promise<JobListItem[]> {
  const response = await api.get<JobListItem[]>("/v_factory/api/jobs/list", { params });
  return Array.isArray(response.data) ? response.data : [];
}

export async function createJob(params: CreateJobParams): Promise<JobDetail> {
  const response = await api.post<JobDetail>("/v_factory/api/jobs/add", {
    title: params.title,
    skip_publish: params.skip_publish ?? true,
  });
  const job = response.data;
  const runMode = params.run_mode ?? "none";
  if (runMode === "script") {
    await runJobStageAction("script", { id: job.id, to_end: false });
  } else if (runMode === "full") {
    await runJobStageAction("script", { id: job.id, to_end: true });
  }
  return job;
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

export async function updateJobInfo(
  jobId: number,
  data: UpdateJobInfoParams
): Promise<JobDetail> {
  const response = await api.post<JobDetail>("/v_factory/api/jobs/updateInfo", {
    id: jobId,
    ...data,
  });
  return response.data;
}

export async function abortJob(jobId: number): Promise<JobDetail> {
  const response = await api.post<JobDetail>("/v_factory/api/jobs/abort", { id: jobId });
  return response.data;
}

export async function runJobStageAction(
  endpoint: string,
  payload: RunStageActionPayload
): Promise<JobDetail> {
  const response = await api.post<JobDetail>(`/v_factory/api/jobs/${endpoint}`, payload);
  return response.data;
}

export async function previewScriptPrompts(
  payload: PreviewScriptPromptsPayload
): Promise<LlmPromptStep[]> {
  const response = await api.post<{ prompts: LlmPromptStep[] }>(
    "/v_factory/api/jobs/script/previewPrompts",
    payload
  );
  return Array.isArray(response.data.prompts) ? response.data.prompts : [];
}

export async function generateVideoDescription(jobId: number): Promise<{
  video_description: string;
  job: JobDetail;
}> {
  const response = await api.post<{ video_description: string; job: JobDetail }>(
    "/v_factory/api/jobs/script/description",
    { id: jobId }
  );
  return response.data;
}

export async function generateImagePrompts(jobId: number): Promise<JobDetail> {
  const response = await api.post<JobDetail>("/v_factory/api/jobs/script/imagePrompts", {
    id: jobId,
  });
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
