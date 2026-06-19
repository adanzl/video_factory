/**
 * 通用 API 接口（占位模板）
 */
import { api } from "./config";
import type { PaginatedResponse } from "@/types/api";

export async function getList<T = unknown>(
  table: string,
  conditions?: Record<string, unknown>,
  pageNum?: number,
  pageSize?: number
): Promise<PaginatedResponse<T>> {
  const params: Record<string, unknown> = { table };
  if (conditions) params.conditions = JSON.stringify(conditions);
  if (pageNum) params.pageNum = pageNum;
  if (pageSize) params.pageSize = pageSize;

  const response = await api.get("/getAll", { params });
  return response.data;
}
