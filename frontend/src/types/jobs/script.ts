export interface ScriptSegment {
  segment_index: number;
  text: string;
  visual_brief?: string;
  image_prompt?: string;
  visual_mode?: string;
}

export interface ScriptJson {
  title?: string;
  narration?: string;
  word_count?: number;
  visual_style?: string;
  segments?: ScriptSegment[];
}
