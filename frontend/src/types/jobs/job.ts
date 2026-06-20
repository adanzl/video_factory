export interface FinalAsset {
  path: string;
  duration?: number | null;
  size?: number | null;
}

export interface JobListItem {
  id: number;
  title: string;
  stage: string;
  status: string;
  final_path?: FinalAsset | null;
  updated_at?: string | null;
  error_message?: string | null;
}

export interface JobDetail extends JobListItem {
  fail_stage?: string | null;
  retry_count?: number;
  skip_publish?: boolean;
  script_json?: unknown;
  quality_report?: unknown;
  cover_path?: string | null;
  intro_path?: string | null;
  audio_path?: string | null;
  subtitle_path?: string | null;
  tts_usage_json?: unknown;
  created_at?: string | null;
}

export type Job = JobDetail;

export interface ListJobsParams {
  status?: string;
  limit?: number;
  offset?: number;
}
