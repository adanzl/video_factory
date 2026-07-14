import type { ListResponse } from "../api/api";

export interface FinalAsset {
  path: string;
  duration?: number | null;
  size?: number | null;
  cost_time?: number | null;
}

export interface JobScriptParams {
  segment_target_sec?: number;
  max_title_length?: number;
  estimated_duration_min?: number;
  narration_target_words?: number;
  speech_chars_per_sec?: number;
  skip_title_optimize?: boolean;
  generate_image_prompts?: boolean;
  supplementary_info?: string;
  video_timeline?: string;
}

export interface JobInfo {
  orientation?: "auto" | "portrait" | "landscape";
  content_style?: "science_child" | "life_experience" | "history_mystery";
  intro_category?: IntroCategory;
  image_provider?: "z_image_t2i" | "wan_t2i" | "sd15_t2i" | "agnes_t2i";
  video_provider?: "ffmpeg" | "wan_i2v" | "agnes_i2v";
  script?: JobScriptParams;
}

export type IntroCategory = "百科" | "历史悬案";

export interface JobListItem {
  id: number;
  title: string;
  stage: string;
  status: string;
  pipeline?: string | null;
  material_id?: number | null;
  final_path?: FinalAsset | null;
  updated_at?: string | null;
  error_message?: string | null;
}

export interface JobDetail extends JobListItem {
  fail_stage?: string | null;
  retry_count?: number;
  skip_publish?: boolean;
  info?: JobInfo | null;
  script_json?: unknown;
  quality_report?: unknown;
  cover_path?: string | null;
  intro_path?: string | null;
  base_path?: string | null;
  audio_path?: string | null;
  subtitle_path?: string | null;
  tts_usage_json?: unknown;
  tts_clips?: string[];
  created_at?: string | null;
}

export type Job = JobDetail;

export interface ListJobsParams {
  status?: string;
  limit?: number;
  offset?: number;
}

export type ListJobsResponse = ListResponse<JobListItem>;

export type CreateJobRunMode = "none" | "script" | "full";

export interface CreateJobParams {
  title: string;
  skip_publish?: boolean;
  run_mode?: CreateJobRunMode;
}

export interface UpdateJobInfoParams {
  orientation?: "portrait" | "landscape";
  content_style?: "science_child" | "life_experience" | "history_mystery";
  intro_category?: IntroCategory;
  image_provider?: JobInfo["image_provider"];
  video_provider?: JobInfo["video_provider"];
}
