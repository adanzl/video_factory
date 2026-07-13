export interface JobStageDef {
  name: string;
  label: string;
  /** 页签展示但不可进入（流水线仍保留该 stage） */
  disabled?: boolean;
}

export const PIPELINE_STANDARD = "standard";
export const PIPELINE_MATERIAL = "material";
export const PIPELINE_CHAT = "chat";

/** 标准流水线（AI 分镜），对齐 backend app/core/pipelines.py STANDARD_CHAIN */
export const STANDARD_JOB_STAGES: JobStageDef[] = [
  { name: "script", label: "脚本" },
  { name: "tts", label: "配音" },
  { name: "segment", label: "分镜" },
  { name: "host", label: "讲解人", disabled: true },
  { name: "intro", label: "片头/封面" },
  { name: "merge", label: "合成" },
  { name: "publish", label: "发布" },
];

/** 素材流水线，对齐 backend app/core/pipelines.py MATERIAL_CHAIN */
export const MATERIAL_JOB_STAGES: JobStageDef[] = [
  { name: "prepare", label: "基底" },
  { name: "script", label: "脚本" },
  { name: "tts", label: "配音" },
  { name: "intro", label: "片头/封面" },
  { name: "merge", label: "合成" },
  { name: "publish", label: "发布" },
];

/** 对话流水线，对齐 backend app/core/pipelines.py CHAT_CHAIN */
export const CHAT_JOB_STAGES: JobStageDef[] = [
  { name: "script", label: "脚本" },
  { name: "tts", label: "配音" },
  { name: "segment", label: "分镜" },
  { name: "intro", label: "片头/封面" },
  { name: "merge", label: "合成" },
  { name: "publish", label: "发布" },
];

/** @deprecated 使用 stagesForJob */
export const JOB_STAGES = STANDARD_JOB_STAGES;

export function stagesForJob(job: { pipeline?: string | null }): JobStageDef[] {
  if (job.pipeline === PIPELINE_MATERIAL) return MATERIAL_JOB_STAGES;
  if (job.pipeline === PIPELINE_CHAT) return CHAT_JOB_STAGES;
  return STANDARD_JOB_STAGES;
}

export function stageNamesForJob(job: { pipeline?: string | null }): Set<string> {
  return new Set(stagesForJob(job).map(stage => stage.name));
}

export function isStageTabDisabled(stage: JobStageDef): boolean {
  return stage.disabled === true;
}

export function resolveActiveStageTab(
  job: { pipeline?: string | null; stage?: string | null },
  preferred?: string | null
): string {
  const stages = stagesForJob(job);
  const pickEnabled = (name: string | null | undefined) => {
    if (!name) {
      return undefined;
    }
    const def = stages.find(stage => stage.name === name);
    if (!def || isStageTabDisabled(def)) {
      return undefined;
    }
    return def.name;
  };

  const fromPreferred = pickEnabled(preferred);
  if (fromPreferred) {
    return fromPreferred;
  }

  const fromJob = pickEnabled(job.stage);
  if (fromJob) {
    return fromJob;
  }

  if (preferred && stages.some(stage => stage.name === preferred)) {
    const idx = stages.findIndex(stage => stage.name === preferred);
    const fallback = [...stages.slice(0, idx)].reverse().find(stage => !isStageTabDisabled(stage));
    if (fallback) {
      return fallback.name;
    }
  }

  return stages.find(stage => !isStageTabDisabled(stage))?.name ?? stages[0]?.name ?? "script";
}

export function isMaterialJob(job: { pipeline?: string | null }): boolean {
  return job.pipeline === PIPELINE_MATERIAL;
}

export const JOB_STAGE_NAMES = new Set(STANDARD_JOB_STAGES.map(stage => stage.name));

export function pipelineLabel(pipeline?: string | null): string {
  if (pipeline === PIPELINE_MATERIAL) return "素材";
  if (pipeline === PIPELINE_CHAT) return "对话";
  return "标准";
}
