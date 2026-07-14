/**
 * 任务 API
 */
import { api } from "./config";
import type {
  CreateJobParams,
  JobDetail,
  JobLog,
  JobSegment,
  ListJobsParams,
  ListJobsResponse,
  UpdateJobInfoParams,
} from "@/types/jobs";
import type { RunStageActionPayload } from "@/types/jobs/stageAction";
import type { LlmPromptStep } from "@/types/jobs/script";

export async function listJobs(params: ListJobsParams = {}): Promise<ListJobsResponse> {
  const response = await api.get<ListJobsResponse>("/v_factory/api/jobs/list", { params });
  return response.data;
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
  jobId: number,
  overrides?: { title?: string; orientation?: string; content_style?: string }
): Promise<LlmPromptStep[]> {
  const payload: Record<string, any> = { id: jobId };
  if (overrides?.title) payload.title = overrides.title;
  if (overrides?.orientation) payload.orientation = overrides.orientation;
  if (overrides?.content_style) payload.content_style = overrides.content_style;
  const response = await api.post<{ prompts: LlmPromptStep[] }>(
    "/v_factory/api/jobs/script/prompts",
    payload
  );
  return Array.isArray(response.data.prompts) ? response.data.prompts : [];
}

export async function previewDailyScriptPrompts(jobId: number): Promise<LlmPromptStep[]> {
  const response = await api.post<{ prompts: LlmPromptStep[] }>(
    "/v_factory/api/jobs/script/prompts",
    { id: jobId }
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

export async function generatePrompts(
  jobId: number,
  options: { type?: string; segments?: number[] } = {}
): Promise<JobDetail> {
  const payload: { id: number; type?: string; segments?: number[] } = { id: jobId };
  if (options.type) {
    payload.type = options.type;
  }
  if (options.segments?.length) {
    payload.segments = options.segments;
  }
  const response = await api.post<JobDetail>("/v_factory/api/jobs/script/generate", payload);
  return response.data;
}

export async function previewSegmentPrompts(
  jobId: number,
  segmentIndex: number,
  step: "image_prompts" | "motion_prompt" = "image_prompts"
): Promise<{ system: string; user: string }> {
  const response = await api.post<{ prompts: LlmPromptStep[] }>(
    "/v_factory/api/jobs/script/prompts",
    { id: jobId, step, segment_index: segmentIndex }
  );
  const steps = Array.isArray(response.data.prompts) ? response.data.prompts : [];
  const matched = steps.find(s => s.step === step);
  return { system: matched?.system ?? "", user: matched?.user ?? "" };
}

export async function updateSegmentText(
  jobId: number,
  segmentIndex: number,
  text: string
): Promise<JobDetail> {
  const response = await api.post<JobDetail>("/v_factory/api/jobs/segment/updateText", {
    id: jobId,
    segment_index: segmentIndex,
    text,
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

export async function clearJobLogs(jobId: number): Promise<{ id: number; cleared: boolean; deleted_count: number }> {
  const response = await api.post("/v_factory/api/jobs/logs/clear", { id: jobId });
  return response.data;
}
