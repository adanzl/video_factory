/**
 * API 配置：支持远程 / 本地服务器自动探测与切换
 */
import axios, { type AxiosError } from "axios";
import { logAndNoticeError } from "@/utils/error";
import { logger } from "@/utils/logger";
import { getAccessToken } from "./api-auth";

const REMOTE = {
  url: "https://leo-zhao.natapp4.cc/",
  available: true,
};

const LOCAL_IP = "192.168.50.172";
const LOCAL_HTTP_PORT = 8848;
const LOCAL_HTTPS_PORT = 8843;

const LOCAL_BASE_URL = `https://${LOCAL_IP}:${LOCAL_HTTPS_PORT}`;

type ServerMode = "local" | "remote";
type ServerStatusListener = (isLocal: boolean, changed: boolean) => void;

let activeServerMode: ServerMode = "remote";
let localIpCheckPromise: Promise<boolean> | null = null;
let serverMonitorTimer: ReturnType<typeof setTimeout> | null = null;
let serverMonitorRunning = false;
let consecutiveLocalProbeFailures = 0;
const serverStatusListeners = new Set<ServerStatusListener>();

const LOCAL_IP_CHECK_TIMEOUT = 500;
const SERVER_CHECK_BASE_INTERVAL_MS = 5000;
const SERVER_CHECK_MAX_INTERVAL_MS = 60000;

function isPageHttps(): boolean {
  return typeof window !== "undefined" && window.location.protocol === "https:";
}

function getCurrentLocalPort(): number {
  return isPageHttps() ? LOCAL_HTTPS_PORT : LOCAL_HTTP_PORT;
}

function getLocalServerOrigin(): string {
  const protocol = isPageHttps() ? "https" : "http";
  const port = getCurrentLocalPort();
  return `${protocol}://${LOCAL_IP}:${port}`;
}

function getRemoteServerOrigin(): string {
  return REMOTE.url || "http://localhost:9002";
}

function normalizeOrigin(url: string): string {
  return url.replace(/\/+$/, "");
}

function markLocalProbeSuccess(): void {
  consecutiveLocalProbeFailures = 0;
}

function markLocalProbeFailure(): void {
  consecutiveLocalProbeFailures += 1;
}

function getNextServerCheckDelay(isLocalAvailable: boolean): number {
  if (isLocalAvailable) {
    return SERVER_CHECK_BASE_INTERVAL_MS;
  }

  return Math.min(
    SERVER_CHECK_BASE_INTERVAL_MS * 2 ** consecutiveLocalProbeFailures,
    SERVER_CHECK_MAX_INTERVAL_MS
  );
}

function emitServerStatus(isLocal: boolean, changed: boolean): void {
  serverStatusListeners.forEach(listener => listener(isLocal, changed));
}

function ensureTrailingSlash(url: string): string {
  return url.replace(/\/?$/, "/");
}

async function checkAddress(url: string, timeout = LOCAL_IP_CHECK_TIMEOUT): Promise<boolean> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    await fetch(ensureTrailingSlash(url), {
      method: "GET",
      signal: controller.signal,
      cache: "no-store",
      mode: "no-cors",
      credentials: "omit",
      redirect: "follow",
    });
    return true;
  } catch (error) {
    if ((error as Error).name !== "AbortError") {
      logger.debug("[API Config] Failed to check address", {
        url,
        error: (error as Error).message,
      });
    }
    return false;
  } finally {
    clearTimeout(timeoutId);
  }
}

async function probeLocalServer(): Promise<boolean> {
  try {
    const isAvailable = await checkAddress(getLocalServerOrigin());
    if (isAvailable) {
      markLocalProbeSuccess();
      return true;
    }
  } catch {
    // 静默降级到失败分支，避免探测流程打断业务
  }

  markLocalProbeFailure();
  return false;
}

function applyServerMode(mode: ServerMode): void {
  const nextBaseUrl = normalizeOrigin(
    mode === "local" ? getLocalServerOrigin() : getRemoteServerOrigin()
  );
  const changed = activeServerMode !== mode || normalizeOrigin(api.defaults.baseURL || "") !== nextBaseUrl;

  activeServerMode = mode;
  api.defaults.baseURL = nextBaseUrl;

  if (changed) {
    logger.info(`[API Config] Switched to ${mode} server: ${nextBaseUrl}`);
  }
}

export async function checkLocalIpAvailable(): Promise<boolean> {
  if (!localIpCheckPromise) {
    localIpCheckPromise = probeLocalServer();
  }

  try {
    return await localIpCheckPromise;
  } finally {
    localIpCheckPromise = null;
  }
}

export async function checkAndSwitchServer(): Promise<boolean> {
  const localAvailable = await checkLocalIpAvailable();
  applyServerMode(localAvailable ? "local" : "remote");
  return localAvailable;
}

async function runServerMonitorCycle(): Promise<void> {
  const previousMode = activeServerMode;
  const isLocal = await checkAndSwitchServer();
  const nextDelay = getNextServerCheckDelay(isLocal);

  if (!serverMonitorRunning) {
    return;
  }

  emitServerStatus(isLocal, previousMode !== activeServerMode);
  serverMonitorTimer = setTimeout(() => {
    void runServerMonitorCycle();
  }, nextDelay);
}

export async function startServerMonitor(): Promise<void> {
  if (serverMonitorRunning) {
    return;
  }

  serverMonitorRunning = true;
  logger.info(
    `[Server Monitor] Started, base ${SERVER_CHECK_BASE_INTERVAL_MS / 1000}s, max ${SERVER_CHECK_MAX_INTERVAL_MS / 1000}s`
  );
  await runServerMonitorCycle();
}

export function stopServerMonitor(): void {
  serverMonitorRunning = false;
  if (serverMonitorTimer) {
    clearTimeout(serverMonitorTimer);
    serverMonitorTimer = null;
  }
  logger.info("[Server Monitor] Stopped");
}

export function subscribeServerStatus(listener: ServerStatusListener): () => void {
  serverStatusListeners.add(listener);
  return () => {
    serverStatusListeners.delete(listener);
  };
}

export function switchToLocal(): void {
  applyServerMode("local");
}

export function switchToRemote(): void {
  applyServerMode("remote");
}

let BASE_URL: string;

if (import.meta.env.VITE_API_BASE_URL) {
  BASE_URL = import.meta.env.VITE_API_BASE_URL;
  logger.info(`[API Config] Using base URL from environment: ${BASE_URL}`);
} else {
  BASE_URL = getRemoteServerOrigin();
  logger.info(`[API Config] Initial base URL (remote): ${BASE_URL}`);
}

const API_BASE_URL = normalizeOrigin(BASE_URL);

export function getApiUrl(): string {
  return normalizeOrigin(api.defaults.baseURL || BASE_URL);
}

export function getBaseUrl(): string {
  return getApiUrl();
}

export function isLocalIpAvailable(): boolean | null {
  return activeServerMode === "local";
}

export {
  API_BASE_URL,
  BASE_URL as REMOTE_BASE_URL,
  REMOTE,
  LOCAL_IP,
  getCurrentLocalPort,
  LOCAL_HTTP_PORT,
  LOCAL_HTTPS_PORT,
  LOCAL_BASE_URL,
};

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
