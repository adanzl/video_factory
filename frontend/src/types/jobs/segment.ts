export interface JobSegment {
  id: number;
  segment_index: number;
  text: string;
  image_prompt?: string | null;
  motion_prompt?: string | null;
  sd15_prompt_en?: string | null;
  visual_mode: string;
  image_path?: string | null;
  clip_path?: string | null;
  duration_sec?: number | null;
  status: string;
}

export interface JobLog {
  stage: string;
  level: string;
  message: string;
  created_at: string;
}
