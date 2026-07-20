/**
 * 系统配置类型
 */
export type ConfigFieldType = "string" | "secret" | "bool" | "number" | "select";

export interface ConfigField {
  attr: string;
  env_key: string;
  label: string;
  type: ConfigFieldType;
  value: string | number | boolean;
  /** secret 字段：是否已配置真实值（value 为脱敏后的展示） */
  configured?: boolean | null;
  description: string;
  options: string[];
  min: number | null;
  max: number | null;
  readonly: boolean;
}

export interface ConfigGroup {
  id: string;
  label: string;
  items: ConfigField[];
}

export interface ConfigPayload {
  env_path: string;
  groups: ConfigGroup[];
}

export interface UpdateConfigResult {
  updated: string[];
  env_keys: string[];
  skipped?: string[];
  count: number;
}
