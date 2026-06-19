export interface JobStageDef {
  name: string;
  label: string;
}

/** 与后端 worker/stages/registry.py STAGE_CHAIN 顺序一致 */
export const JOB_STAGES: JobStageDef[] = [
  { name: "title", label: "标题" },
  { name: "script", label: "脚本" },
  { name: "intro", label: "片头" },
  { name: "cover", label: "封面" },
  { name: "tts", label: "配音" },
  { name: "segment", label: "分段" },
  { name: "host", label: "讲解人" },
  { name: "merge", label: "合成" },
  { name: "publish", label: "发布" },
];

export const JOB_STAGE_NAMES = new Set(JOB_STAGES.map(stage => stage.name));
