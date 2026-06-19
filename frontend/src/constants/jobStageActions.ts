import type { StageActionConfig } from "@/types/jobs/stageAction";

export const STAGE_ACTION_CONFIG: Record<string, StageActionConfig> = {
  title: {
    unsupported: true,
    unsupportedReason: "标题阶段暂无重跑接口，可修改标题后从脚本阶段重跑",
    params: [
      {
        key: "title",
        label: "标题",
        type: "text",
        placeholder: "任务标题",
      },
    ],
  },
  script: {
    endpoint: "script",
    params: [],
  },
  intro: {
    endpoint: "intro",
    params: [
      {
        key: "hold_tail_sec",
        label: "尾部停留 (秒)",
        type: "number",
        defaultValue: 0.35,
        min: 0,
        max: 5,
        step: 0.05,
        placeholder: "秒",
      },
    ],
  },
  cover: {
    endpoint: "cover",
    params: [],
  },
  tts: {
    endpoint: "tts",
    params: [],
  },
  segment: {
    endpoint: "segment/images",
    params: [
      {
        key: "segmentScope",
        label: "重跑范围",
        type: "select",
        defaultValue: "segment/images",
        options: [
          { label: "分镜静图", value: "segment/images" },
          { label: "图生视频", value: "segment/clips" },
        ],
      },
      {
        key: "segments",
        label: "分段序号",
        type: "segment-indices",
        placeholder: "留空表示全部",
      },
    ],
  },
  host: {
    unsupported: true,
    unsupportedReason: "讲解人阶段暂无独立 API",
    params: [],
  },
  merge: {
    endpoint: "merge",
    params: [],
  },
  publish: {
    endpoint: "publish",
    params: [
      {
        key: "skip_publish",
        label: "跳过发布",
        type: "boolean",
        defaultValue: false,
      },
    ],
  },
};

export function getStageActionConfig(stage: string): StageActionConfig {
  return (
    STAGE_ACTION_CONFIG[stage] ?? {
      unsupported: true,
      unsupportedReason: "该阶段暂不支持",
      params: [],
    }
  );
}

export function resolveStageEndpoint(
  stage: string,
  paramValues: Record<string, string | boolean | number[]>
): string | undefined {
  const config = getStageActionConfig(stage);
  if (config.unsupported || !config.endpoint) {
    return undefined;
  }
  if (stage === "segment") {
    const scope = paramValues.segmentScope;
    return typeof scope === "string" && scope ? scope : config.endpoint;
  }
  return config.endpoint;
}
