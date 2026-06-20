export interface ScriptSegment {
  segment_index: number;
  text: string;
  visual_brief?: string;
  image_prompt?: string;
  motion_prompt?: string;
  visual_mode?: string;
}

export interface ScriptJson {
  title?: string;
  draft_title?: string;
  narration?: string;
  word_count?: number;
  cost_time?: number;
  visual_style?: string;
  script_mode?: "ai" | "manual";
  segments?: ScriptSegment[];
}
