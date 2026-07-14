/**
 * 素材 API（视频 + 音频）
 */
import { api } from "./config";
import type {
  AnalyzeMaterialVideoParams,
  AnalyzeMaterialVideoResult,
  CreateJobFromMaterialVideoParams,
  ListMaterialVideosParams,
  ListMaterialVideosResponse,
  MaterialVideoRecord,
  UploadMaterialVideoParams,
  EditMaterialVideoParams,
} from "@/types/material-video";
import type { JobDetail } from "@/types/jobs";
import type {
  MaterialAudioRecord,
  ListMaterialAudiosParams,
  ListMaterialAudiosResponse,
  UploadMaterialAudioParams,
  EditMaterialAudioParams,
} from "@/types/material-audio";

// ── 视频素材 ──────────────────────────────────

export async function listMaterialVideos(params: ListMaterialVideosParams = {}): Promise<ListMaterialVideosResponse> {
  const response = await api.get<ListMaterialVideosResponse>("/v_factory/api/materials/video/list", { params });
  return response.data;
}

export async function getMaterialVideo(materialId: number): Promise<MaterialVideoRecord> {
  const response = await api.get<MaterialVideoRecord>("/v_factory/api/materials/video/get", {
    params: { id: materialId },
  });
  return response.data;
}

export async function uploadMaterialVideo(params: UploadMaterialVideoParams): Promise<MaterialVideoRecord> {
  const form = new FormData();
  form.append("file", params.file);
  if (params.name) {
    form.append("name", params.name);
  }
  if (params.note) {
    form.append("note", params.note);
  }
  const response = await api.post<MaterialVideoRecord>("/v_factory/api/materials/video/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

export async function editMaterialVideo(params: EditMaterialVideoParams): Promise<MaterialVideoRecord> {
  const form = new FormData();
  form.append("id", String(params.id));
  form.append("name", params.name);
  form.append("note", params.note ?? "");
  if (params.file) {
    form.append("file", params.file);
  }
  const response = await api.post<MaterialVideoRecord>("/v_factory/api/materials/video/edit", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

export async function updateMaterialVideo(
  materialId: number,
  data: Partial<Pick<MaterialVideoRecord, "name" | "note">>
): Promise<MaterialVideoRecord> {
  const response = await api.post<MaterialVideoRecord>("/v_factory/api/materials/video/update", {
    id: materialId,
    ...data,
  });
  return response.data;
}

export async function deleteMaterialVideo(materialId: number): Promise<{ id: number; deleted: boolean }> {
  const response = await api.post("/v_factory/api/materials/video/delete", { id: materialId });
  return response.data;
}

export async function createJobFromMaterialVideo(
  params: CreateJobFromMaterialVideoParams
): Promise<JobDetail> {
  const response = await api.post<JobDetail>("/v_factory/api/materials/video/jobs/create", params);
  return response.data;
}

export async function analyzeMaterialVideo(
  params: AnalyzeMaterialVideoParams
): Promise<AnalyzeMaterialVideoResult> {
  const response = await api.post<AnalyzeMaterialVideoResult>("/v_factory/api/materials/video/analyze", params);
  return response.data;
}

// ── 音频素材 ──────────────────────────────────

export async function listMaterialAudios(params: ListMaterialAudiosParams = {}): Promise<ListMaterialAudiosResponse> {
  const response = await api.get<ListMaterialAudiosResponse>("/v_factory/api/materials/audio/list", { params });
  return response.data;
}

export async function getMaterialAudio(materialId: number): Promise<MaterialAudioRecord> {
  const response = await api.get<MaterialAudioRecord>("/v_factory/api/materials/audio/get", {
    params: { id: materialId },
  });
  return response.data;
}

export async function uploadMaterialAudio(params: UploadMaterialAudioParams): Promise<MaterialAudioRecord> {
  const form = new FormData();
  form.append("file", params.file);
  if (params.name) {
    form.append("name", params.name);
  }
  if (params.note) {
    form.append("note", params.note);
  }
  const response = await api.post<MaterialAudioRecord>("/v_factory/api/materials/audio/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

export async function editMaterialAudio(params: EditMaterialAudioParams): Promise<MaterialAudioRecord> {
  const form = new FormData();
  form.append("id", String(params.id));
  form.append("name", params.name);
  form.append("note", params.note ?? "");
  if (params.file) {
    form.append("file", params.file);
  }
  const response = await api.post<MaterialAudioRecord>("/v_factory/api/materials/audio/edit", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

export async function updateMaterialAudio(
  materialId: number,
  data: Partial<Pick<MaterialAudioRecord, "name" | "note">>
): Promise<MaterialAudioRecord> {
  const response = await api.post<MaterialAudioRecord>("/v_factory/api/materials/audio/update", {
    id: materialId,
    ...data,
  });
  return response.data;
}

export async function deleteMaterialAudio(materialId: number): Promise<{ id: number; deleted: boolean }> {
  const response = await api.post("/v_factory/api/materials/audio/delete", { id: materialId });
  return response.data;
}
