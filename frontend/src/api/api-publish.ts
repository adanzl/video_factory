import { api } from "./config";

export interface BiliSessionInfo {
  ok: boolean;
  uname?: string;
  mid?: number;
}

export interface BiliQrLoginSession {
  session_id: string;
  status: string;
  expires_in: number;
  qrcode_url: string;
  qrcode_svg: string;
}

export interface BiliQrLoginStatus {
  ok: boolean;
  status: string;
  message: string;
  uname?: string;
  mid?: number;
}

export async function getBiliSession(): Promise<BiliSessionInfo> {
  const response = await api.get<BiliSessionInfo>(
    "/v_factory/api/publish/bili/session",
    { skipErrorNotice: true } as { skipErrorNotice?: boolean }
  );
  return response.data;
}

export async function createBiliLoginQr(): Promise<BiliQrLoginSession> {
  const response = await api.post<BiliQrLoginSession>(
    "/v_factory/api/publish/bili/login/qrcode",
    {}
  );
  return response.data;
}

export async function pollBiliLoginQr(sessionId: string): Promise<BiliQrLoginStatus> {
  const response = await api.get<BiliQrLoginStatus>(
    "/v_factory/api/publish/bili/login/qrcode/status",
    {
      params: { session_id: sessionId },
      skipErrorNotice: true,
    } as { params: { session_id: string }; skipErrorNotice?: boolean }
  );
  return response.data;
}
