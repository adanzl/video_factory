import { api } from "./config";

const STORAGE_KEY_ACCESS = "access_token";

export function getAccessToken(): string | null {
  return localStorage.getItem(STORAGE_KEY_ACCESS);
}

export function setAccessToken(token: string | null): void {
  if (!token) {
    localStorage.removeItem(STORAGE_KEY_ACCESS);
    return;
  }
  localStorage.setItem(STORAGE_KEY_ACCESS, token);
}

export async function login(username: string, password: string): Promise<void> {
  await api.post("/v_factory/api/auth/login", { username, password });
}

export async function logout(): Promise<void> {
  setAccessToken(null);
}
