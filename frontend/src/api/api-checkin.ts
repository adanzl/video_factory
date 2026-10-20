import { api } from "./config";
import type {
  CheckinOverview,
  CheckinSetting,
  CheckinSettingResponse,
  CheckinState,
  ListCheckinRecordsParams,
  ListCheckinRecordsResponse,
  SaveCheckinSettingResult,
} from "@/types/checkin";

export async function fetchCheckinOverview(): Promise<CheckinOverview> {
  const response = await api.get<CheckinOverview>("/v_factory/api/checkin/overview");
  return response.data;
}

export async function listCheckinRecords(
  params: ListCheckinRecordsParams,
): Promise<ListCheckinRecordsResponse> {
  const response = await api.get<ListCheckinRecordsResponse>("/v_factory/api/checkin/records", {
    params,
  });
  return response.data;
}

export async function fetchCheckinState(): Promise<CheckinState> {
  const response = await api.get<CheckinState>("/v_factory/api/checkin/state");
  return response.data;
}

export async function startCheckinRun(): Promise<void> {
  await api.post("/v_factory/api/checkin/run");
}

export async function fetchCheckinSetting(): Promise<CheckinSettingResponse> {
  const response = await api.get<CheckinSettingResponse>("/v_factory/api/checkin/setting");
  return response.data;
}

export async function saveCheckinSetting(
  setting: CheckinSetting,
): Promise<SaveCheckinSettingResult> {
  const response = await api.put<SaveCheckinSettingResult>("/v_factory/api/checkin/setting", {
    ...setting,
  });
  return response.data;
}
