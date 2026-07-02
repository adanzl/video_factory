/**
 * 系统配置 API
 */
import { api } from "./config";
import type { ConfigPayload, UpdateConfigResult } from "@/types/config";

export async function fetchSystemConfig(): Promise<ConfigPayload> {
  const response = await api.get<ConfigPayload>("/v_factory/api/config");
  return response.data;
}

export async function updateSystemConfig(
  updates: Record<string, string | number | boolean>
): Promise<UpdateConfigResult> {
  const response = await api.put<UpdateConfigResult>("/v_factory/api/config", { updates });
  return response.data;
}
