export type JobPipeline = "standard" | "material";

export interface MaterialVideoRecord {
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

export interface ListMaterialVideosParams {
  limit?: number;
  offset?: number;
}

export type MaterialVideoJobRunMode = "none" | "prepare" | "full";

export interface CreateJobFromMaterialVideoParams {
  material_id: number;
  title: string;
  script_mode?: "ai" | "manual";
  narration?: string;
  skip_publish?: boolean;
  run_mode?: MaterialVideoJobRunMode;
}

export interface UploadMaterialVideoParams {
  file: File;
  name?: string;
  note?: string;
}

export interface EditMaterialVideoParams {
  id: number;
  name: string;
  note?: string;
  file?: File;
}

export interface AnalyzeMaterialVideoParams {
  material_id: number;
}

export interface AnalyzeMaterialVideoResult {
  material_id: number;
  note: string;
}
