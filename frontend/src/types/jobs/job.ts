export interface JobListItem {
  id: number;
  title: string;
  stage: string;
  status: string;
  final_path?: string | null;
  updated_at?: string | null;
  error_message?: string | null;
}

export type Job = JobListItem;

export interface ListJobsParams {
  status?: string;
  limit?: number;
  offset?: number;
}
