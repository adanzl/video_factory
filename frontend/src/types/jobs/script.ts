export interface ScriptSegment {
  segment_index: number;
  text: string;
  /** 景别：全景 / 中景 / 特写（日常对话分镜） */
  shot_type?: string;
  visual_brief?: string;
  image_prompt?: string;
  motion_prompt?: string;
  sd15_prompt_en?: string;
  visual_mode?: string;
  start_sec?: number;
  end_sec?: number;
  duration_sec?: number;
}

export interface LlmPromptStep {
  step: string;
  label: string;
  system: string;
  user: string;
}

export interface ScriptJson {
  title?: string;
  draft_title?: string;
  narration?: string;
  word_count?: number;
  speech_chars_per_sec?: number;
  cost_time?: number;
  visual_style?: string;
  script_mode?: "ai" | "manual";
  generate_image_prompts?: boolean;
  segments?: ScriptSegment[];
  llm_prompts?: LlmPromptStep[];
  supplementary_info?: string;
  video_timeline?: string;
  video_description?: string;
  tags?: string[];
}
