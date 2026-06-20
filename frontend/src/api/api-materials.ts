/**
 * 视频素材 API
 */
import { api } from "./config";
import type {
  CreateJobFromMaterialParams,
  ListMaterialsParams,
  MaterialRecord,
  UploadMaterialParams,
} from "@/types/material";
import type { JobDetail } from "@/types/jobs";

export async function listMaterials(params: ListMaterialsParams = {}): Promise<MaterialRecord[]> {
  const response = await api.get<MaterialRecord[]>("/v_factory/api/materials/list", { params });
  return Array.isArray(response.data) ? response.data : [];
}

export async function getMaterial(materialId: number): Promise<MaterialRecord> {
  const response = await api.get<MaterialRecord>("/v_factory/api/materials/get", {
    params: { id: materialId },
  });
  return response.data;
}

export async function uploadMaterial(params: UploadMaterialParams): Promise<MaterialRecord> {
  const form = new FormData();
  form.append("file", params.file);
  if (params.name) {
    form.append("name", params.name);
  }
  if (params.note) {
    form.append("note", params.note);
  }
  const response = await api.post<MaterialRecord>("/v_factory/api/materials/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

export async function updateMaterial(
  materialId: number,
  data: Partial<Pick<MaterialRecord, "name" | "note">>
): Promise<MaterialRecord> {
  const response = await api.post<MaterialRecord>("/v_factory/api/materials/update", {
    id: materialId,
    ...data,
  });
  return response.data;
}

export async function deleteMaterial(materialId: number): Promise<{ id: number; deleted: boolean }> {
  const response = await api.post("/v_factory/api/materials/delete", { id: materialId });
  return response.data;
}

export async function createJobFromMaterial(
  params: CreateJobFromMaterialParams
): Promise<JobDetail> {
  const response = await api.post<JobDetail>("/v_factory/api/materials/jobs/create", params);
  return response.data;
}
