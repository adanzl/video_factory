export interface MaterialAudioRecord {
  id: number;
  name: string;
  file_path: string;
  duration_sec?: number | null;
  size_bytes?: number | null;
  note?: string | null;
  status?: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ListMaterialAudiosParams {
  limit?: number;
  offset?: number;
}

export interface UploadMaterialAudioParams {
  file: File;
  name?: string;
  note?: string;
}

export interface EditMaterialAudioParams {
  id: number;
  name: string;
  note?: string;
  file?: File;
}
