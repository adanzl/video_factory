/** 每日签到 */

export interface CheckinRecord {
  id: number;
  created_at: string;
  platform: string;
  platform_name: string;
  account_index: number;
  status: "ok" | "fail";
  message: string | null;
}

export interface CheckinPlatformStat {
  platform: string;
  platform_name: string;
  total: number;
  ok_count: number;
  fail_count: number;
  last_at: string;
  last_status: string;
  last_message: string;
}

export interface CheckinRunResult {
  finished_at: string;
  exit_code: number;
  success: boolean;
  output_tail: string;
}

export interface CheckinRunState {
  running: boolean;
  started_at: string;
  elapsed_sec: number;
  trigger: string;
  last_result: CheckinRunResult | null;
}

export interface CheckinSchedule {
  enabled: boolean;
  scheduler_enabled: boolean;
  run_time: string;
  next_run_at: string | null;
}

export interface CheckinSetting {
  run_script: string;
  timeout_sec: number;
  auto_run: boolean;
  run_time: string;
}

export interface CheckinEnvironment {
  enabled: boolean;
  dc_dir: string;
  dc_dir_exists: boolean;
  run_script: string;
  run_script_exists: boolean;
  db_script: string;
  db_script_exists: boolean;
}

export interface CheckinOverview {
  today: { date: string; ok: number; fail: number; total: number };
  platforms: CheckinPlatformStat[];
  environment: CheckinEnvironment;
  run_state: CheckinRunState;
  schedule: CheckinSchedule;
  redis_ok: boolean;
}

export interface ListCheckinRecordsParams {
  status?: string;
  platform?: string;
  date?: string;
  page: number;
  page_size: number;
}

export interface ListCheckinRecordsResponse {
  items: CheckinRecord[];
  total: number;
  page: number;
  page_size: number;
}

export interface CheckinState {
  run_state: CheckinRunState;
  schedule: CheckinSchedule;
  environment: CheckinEnvironment;
  redis_ok: boolean;
}

export interface CheckinSettingResponse {
  enabled: boolean;
  setting: CheckinSetting;
  schedule: CheckinSchedule;
  redis_ok: boolean;
}

export interface SaveCheckinSettingResult {
  setting: CheckinSetting;
  schedule: CheckinSchedule;
}
