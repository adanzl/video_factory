export type StageParamType = "text" | "boolean" | "select" | "segment-indices";

export interface StageParamOption {
  label: string;
  value: string;
}

export interface StageParamDef {
  key: string;
  label: string;
  type: StageParamType;
  placeholder?: string;
  defaultValue?: string | boolean;
  options?: StageParamOption[];
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
}

export type StageParamValues = Record<string, string | boolean | number[]>;
