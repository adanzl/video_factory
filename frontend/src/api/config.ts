/**
 * API 配置
 */
import axios, { type AxiosError } from "axios";
import { logAndNoticeError } from "@/utils/error";
import { getAccessToken } from "./api-auth";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  withCredentials: true,
});

api.interceptors.request.use(config => {
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  response => response,
  (error: AxiosError<{ error?: string; msg?: string }>) => {
    logAndNoticeError(error, "请求失败");
    return Promise.reject(error);
  }
);
