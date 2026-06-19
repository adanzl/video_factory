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
}

export type StageParamValues = Record<string, string | boolean | number | number[]>;
