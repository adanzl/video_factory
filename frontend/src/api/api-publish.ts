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

export interface BiliPublishPartition {
  tid: number;
  human_type2?: number | null;
  label: string;
  display: string;
}

export interface BiliPublishTopic {
  name: string;
  topic_id?: number | null;
  mission_id?: number | null;
}

export interface BiliPublishConfig {
  pipeline: string;
  partition: BiliPublishPartition;
  neutral_mark?: string | null;
  mark_id?: number | null;
  copyright: number;
  topic?: BiliPublishTopic | null;
  fixed_tags?: string[] | null;
}

export async function getBiliSession(): Promise<BiliSessionInfo> {
  const response = await api.get<BiliSessionInfo>(
    "/v_factory/api/publish/bili/session",
    { skipErrorNotice: true }
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
    }
  );
  return response.data;
}

export async function getBiliPublishConfig(
  pipeline?: string
): Promise<BiliPublishConfig> {
  const response = await api.get<BiliPublishConfig>(
    "/v_factory/api/publish/bili/config",
    {
      params: pipeline ? { pipeline } : undefined,
      skipErrorNotice: true,
    }
  );
  return response.data;
}
