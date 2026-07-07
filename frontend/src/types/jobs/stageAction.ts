export type StageParamType = "text" | "boolean" | "select" | "segment-indices" | "number";

export interface StageParamOption {
  label: string;
  value: string;
}

export interface StageParamDef {
  key: string;
  label: string;
  type: StageParamType;
  placeholder?: string;
  defaultValue?: string | boolean | number;
  options?: StageParamOption[];
  min?: number;
  max?: number;
  step?: number;
}

export interface StageActionConfig {
  endpoint?: string;
  unsupported?: boolean;
  unsupportedReason?: string;
  params: StageParamDef[];
}

export interface RunStageActionPayload {
  id: number;
  to_end: boolean;
  segments?: number[];
  hold_tail_sec?: number;
  orientation?: "portrait" | "landscape" | "auto";
  speech_rate?: number;
  voice_id?: string;
  title?: string;
  segment_target_sec?: number;
  max_title_length?: number;
  estimated_duration_min?: number;
  narration_target_words?: number;
  speech_chars_per_sec?: number;
  skip_title_optimize?: boolean;
  generate_image_prompts?: boolean;
  supplementary_info?: string;
  video_timeline?: string;
  content_style?: "science_child" | "life_experience" | "history_mystery";
  intro_category?: "百科" | "历史悬案";
  image_provider?: "z_image_t2i" | "wan_t2i" | "sd15_t2i" | "agnes_t2i";
  video_provider?: "ffmpeg" | "wan_i2v" | "agnes_i2v";
  segment_index?: number;
}

export interface PreviewScriptPromptsPayload {
  id: number;
  title?: string;
  segment_target_sec?: number;
  max_title_length?: number;
  estimated_duration_min?: number;
  narration_target_words?: number;
  speech_chars_per_sec?: number;
  skip_title_optimize?: boolean;
  supplementary_info?: string;
  video_timeline?: string;
  orientation?: "portrait" | "landscape";
  content_style?: "science_child" | "life_experience" | "history_mystery";
}

export type StageParamValues = Record<string, string | boolean | number | number[]>;
