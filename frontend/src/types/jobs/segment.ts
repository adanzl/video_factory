export interface SegmentDialogueLine {
  speaker: string;
  text: string;
}

export interface JobSegment {
  id: number;
  segment_index: number;
  text: string;
  /** 对白行（日常故事等）；有则文案区按角色分行展示 */
  dialogue?: SegmentDialogueLine[] | null;
  image_prompt?: string | null;
  motion_prompt?: string | null;
  sd15_prompt_en?: string | null;
  visual_mode: string;
  image_path?: string | null;
  clip_path?: string | null;
  /** 有效时长：DB / TTS 实际 / 脚本预估 */
  duration_sec?: number | null;
  /** TTS 合成后按字幕 cue 汇总的实际口播时长（秒） */
  tts_duration_sec?: number | null;
  /** 脚本阶段预估的单镜时长（秒） */
  script_duration_sec?: number | null;
  status: string;
  /** 图片/视频版本号，每次生成+1，用于 URL 缓存破坏 */
  version?: number;
  /** 分镜图片生成耗时（秒） */
  image_gen_sec?: number | null;
  /** 分镜视频片段生成耗时（秒） */
  clip_gen_sec?: number | null;
  /** 分镜扩展：video_provider 等 */
  info?: {
    video_provider?: "ffmpeg" | "wan_i2v" | "agnes_i2v";
  } | null;
}

export interface JobLog {
  stage: string;
  level: string;
  message: string;
  created_at: string;
}
