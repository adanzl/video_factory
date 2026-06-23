export interface JobStageDef {
  name: string;
  label: string;
}

export const PIPELINE_STANDARD = "standard";
export const PIPELINE_MATERIAL = "material";

/** 标准流水线（AI 分镜），对齐 backend app/core/pipelines.py STANDARD_CHAIN */
export const STANDARD_JOB_STAGES: JobStageDef[] = [
  { name: "title", label: "标题" },
  { name: "script", label: "脚本" },
  { name: "intro", label: "片头/封面" },
  { name: "tts", label: "配音" },
  { name: "segment", label: "分段" },
  { name: "host", label: "讲解人" },
  { name: "merge", label: "合成" },
  { name: "publish", label: "发布" },
];

/** 素材流水线，对齐 backend app/core/pipelines.py MATERIAL_CHAIN */
export const MATERIAL_JOB_STAGES: JobStageDef[] = [
  { name: "prepare", label: "基底" },
  { name: "script", label: "脚本" },
  { name: "intro", label: "片头/封面" },
  { name: "tts", label: "配音" },
  { name: "merge", label: "合成" },
  { name: "publish", label: "发布" },
];

/** @deprecated 使用 stagesForJob */
export const JOB_STAGES = STANDARD_JOB_STAGES;

export function stagesForJob(job: { pipeline?: string | null }): JobStageDef[] {
  return job.pipeline === PIPELINE_MATERIAL ? MATERIAL_JOB_STAGES : STANDARD_JOB_STAGES;
}

export function stageNamesForJob(job: { pipeline?: string | null }): Set<string> {
  return new Set(stagesForJob(job).map(stage => stage.name));
}

export function isMaterialJob(job: { pipeline?: string | null }): boolean {
  return job.pipeline === PIPELINE_MATERIAL;
}

export const JOB_STAGE_NAMES = new Set(STANDARD_JOB_STAGES.map(stage => stage.name));

export function pipelineLabel(pipeline?: string | null): string {
  return pipeline === PIPELINE_MATERIAL ? "素材" : "标准";
}
