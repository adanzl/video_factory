/**
 * API 响应类型定义
 */
export interface ApiResponse<T = unknown> {
  code: number;
  msg?: string;
  data: T;
}

export interface PaginatedData<T> {
  data: T[];
  totalCount?: number;
  pageNum?: number;
  pageSize?: number;
  totalPage?: number;
}

export interface PaginatedResponse<T> extends ApiResponse<PaginatedData<T>> {
  total?: number;
  pageNum?: number;
  pageSize?: number;
}

export interface DeleteResponse {
  success: boolean;
  message?: string;
}
