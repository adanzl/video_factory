export type JobPipeline = "standard" | "material";

export interface MaterialRecord {
  id: number;
  name: string;
  file_path: string;
  duration_sec?: number | null;
  width?: number | null;
  height?: number | null;
  size_bytes?: number | null;
  thumbnail_path?: string | null;
  note?: string | null;
  status?: string;
  job_id?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ListMaterialsParams {
  limit?: number;
  offset?: number;
}

export type MaterialJobRunMode = "none" | "prepare" | "full";

export interface CreateJobFromMaterialParams {
  material_id: number;
  title: string;
  script_mode?: "ai" | "manual";
  narration?: string;
  skip_publish?: boolean;
  run_mode?: MaterialJobRunMode;
}

export interface UploadMaterialParams {
  file: File;
  name?: string;
  note?: string;
}

export interface EditMaterialParams {
  id: number;
  name: string;
  note?: string;
  file?: File;
}

export interface AnalyzeMaterialParams {
  material_id: number;
}

export interface AnalyzeMaterialResult {
  material_id: number;
  note: string;
}
