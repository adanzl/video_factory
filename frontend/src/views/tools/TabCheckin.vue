<template>
  <div class="checkin-page flex h-full min-h-0 flex-col bg-white">
    <el-empty
      v-if="!environment.enabled"
      description="未在 .env 配置 DC_DIR，每日签到功能未启用"
      :image-size="80"
      class="m-auto"
    />

    <div v-else class="flex h-full min-h-0 flex-col gap-3">
      <el-alert
        v-if="!environment.run_script_exists || !environment.db_exists || !environment.db_script_exists"
        type="warning"
        show-icon
        :closable="false"
      >
        <template #title>
          <span v-if="!environment.dc_dir_exists">签到目录不存在：{{ environment.dc_dir }}</span>
          <span v-else-if="!environment.run_script_exists"
            >找不到运行脚本：{{ environment.run_script }}</span
          >
          <span v-else-if="!environment.db_script_exists"
            >找不到查询脚本：{{ environment.db_script }}</span
          >
          <span v-else>结果库尚未生成：{{ environment.db_path }}（跑一次后自动出现）</span>
        </template>
      </el-alert>

      <el-alert
        v-if="!redisOk || !schedule.scheduler_enabled"
        :type="redisOk ? 'warning' : 'error'"
        show-icon
        :closable="false"
      >
        <template #title>
          <span v-if="!redisOk"
            >连不上 Redis：下面显示的可能是默认配置，保存会被拒绝，请先确认 Redis</span
          >
          <span v-else
            >定时调度总开关（ENABLE_SCHEDULER）未开启：定时签到不会自动运行，手动运行不受影响</span
          >
        </template>
      </el-alert>

      <div class="flex flex-wrap items-center gap-2">
        <el-button
          type="primary"
          :disabled="loading"
          :icon="Refresh"
          size="small"
          @click="fetchAll"
        />
        <el-button
          type="success"
          size="small"
          :loading="runState.running"
          :disabled="!environment.run_script_exists"
          @click="handleRun"
        >
          {{ runState.running ? "运行中…" : "立即运行" }}
        </el-button>
        <span v-if="runState.running" class="text-xs text-amber-600">
          已跑 {{ runState.elapsed_sec }}s · {{ runState.trigger === "schedule" ? "定时" : "手动" }}
        </span>
        <span
          v-else-if="lastResultText"
          class="text-xs"
          :class="runState.last_result?.success ? 'text-gray-500' : 'text-red-600'"
        >
          {{ lastResultText }}
        </span>
        <el-radio-group v-model="statusFilter" size="small" @change="onFilterChange">
          <el-radio-button value="">全部</el-radio-button>
          <el-radio-button value="ok">成功</el-radio-button>
          <el-radio-button value="fail">失败</el-radio-button>
        </el-radio-group>
        <el-select
          v-model="platformFilter"
          placeholder="全部平台"
          clearable
          class="w-40!"
          size="small"
          @change="onFilterChange"
        >
          <el-option
            v-for="item in platforms"
            :key="item.platform"
            :label="`${item.platform_name} · 成功 ${item.ok_count} / 失败 ${item.fail_count}`"
            :value="item.platform"
          />
        </el-select>
        <el-date-picker
          v-model="dateFilter"
          type="date"
          placeholder="全部日期"
          value-format="YYYY-MM-DD"
          size="small"
          class="w-36!"
          @change="onFilterChange"
        />
        <span class="ml-auto flex flex-wrap items-center gap-2">
          <span class="text-xs text-gray-500">{{ scheduleText }}</span>
          <el-button size="small" link @click="openSetting">设置</el-button>
          <el-button size="small" link @click="showDetail = true">环境 / 输出</el-button>
        </span>
      </div>

      <div ref="tableWrap" class="min-h-0 flex-1 overflow-hidden">
        <el-table
          :data="records"
          :height="tableHeight"
          stripe
          class="checkin-table w-full"
          v-loading="loading"
          :row-class-name="recordRowClass"
        >
          <el-table-column type="expand">
            <template #default="{ row }">
              <pre
                class="m-2 max-h-64 overflow-auto rounded bg-gray-50 p-3 text-xs whitespace-pre-wrap"
                >{{ row.message || "（无输出）" }}</pre
              >
            </template>
          </el-table-column>
          <el-table-column label="时间" width="170">
            <template #default="{ row }">
              {{ row.created_at }}
            </template>
          </el-table-column>
          <el-table-column label="平台" width="150">
            <template #default="{ row }">
              {{ row.platform_name }}
              <el-tag v-if="row.account_index > 0" size="small" type="info" class="ml-1">
                #{{ row.account_index + 1 }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="row.status === 'ok' ? 'success' : 'danger'" size="small">
                {{ row.status === "ok" ? "成功" : "失败" }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="信息" min-width="220">
            <template #default="{ row }">
              <el-tooltip placement="top" :show-after="300" :disabled="!row.message">
                <template #content>
                  <pre class="max-h-64 max-w-md overflow-auto text-xs whitespace-pre-wrap">{{
                    row.message
                  }}</pre>
                </template>
                <span class="block truncate">{{ briefMessage(row.message) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[15, 20, 50]"
        layout="total, sizes, prev, pager, next"
        class="shrink-0 justify-start"
        @current-change="fetchRecords"
        @size-change="onPageSizeChange"
      />
    </div>

    <el-dialog v-model="showDetail" title="签到运行详情" width="720px">
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item label="签到目录">
          {{ environment.dc_dir }}
          <el-tag
            :type="environment.dc_dir_exists ? 'success' : 'danger'"
            size="small"
            class="ml-2"
          >
            {{ environment.dc_dir_exists ? "存在" : "缺失" }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="运行脚本">
          {{ environment.run_script }}
          <el-tag
            :type="environment.run_script_exists ? 'success' : 'danger'"
            size="small"
            class="ml-2"
          >
            {{ environment.run_script_exists ? "存在" : "缺失" }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="结果库">
          {{ environment.db_path }}
          <el-tag :type="environment.db_exists ? 'success' : 'danger'" size="small" class="ml-2">
            {{ environment.db_exists ? "存在" : "缺失" }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="查询脚本">
          {{ environment.db_script }}
          <el-tag
            :type="environment.db_script_exists ? 'success' : 'danger'"
            size="small"
            class="ml-2"
          >
            {{ environment.db_script_exists ? "存在" : "缺失" }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="定时">
          {{ schedule.enabled ? `每天 ${schedule.run_time} (${schedule.timezone})` : "未启用" }}
        </el-descriptions-item>
      </el-descriptions>

      <div class="mt-4 text-xs text-gray-500">上次输出（末尾 40 行）</div>
      <pre class="mt-1 max-h-64 overflow-auto rounded bg-gray-50 p-3 text-xs whitespace-pre-wrap">{{
        runState.last_result?.output_tail || "（还没有运行记录）"
      }}</pre>
    </el-dialog>

    <el-dialog v-model="showSetting" title="签到设置" width="520px">
      <el-form label-width="110px" size="small">
        <el-form-item label="运行脚本">
          <el-input v-model="settingForm.run_script" placeholder="run.sh" />
          <div class="mt-1 text-xs text-gray-400">相对 DC_DIR 的文件名</div>
        </el-form-item>
        <el-form-item label="运行超时">
          <el-input-number v-model="settingForm.timeout_sec" :min="60" :max="86400" :step="60" />
          <span class="ml-2 text-xs text-gray-400">秒</span>
        </el-form-item>
        <el-form-item label="启用定时">
          <el-switch v-model="settingForm.auto_run" />
        </el-form-item>
        <el-form-item label="每日运行时刻">
          <el-time-picker
            v-model="settingForm.run_time"
            format="HH:mm"
            value-format="HH:mm"
            placeholder="09:00"
            :disabled="!settingForm.auto_run"
          />
        </el-form-item>
        <el-form-item label="时区">
          <el-input v-model="settingForm.run_tz" placeholder="Asia/Shanghai" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="showSetting = false">取消</el-button>
        <el-button
          type="primary"
          size="small"
          :loading="saving"
          :disabled="!redisOk"
          @click="saveSetting"
        >
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { Refresh } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { api } from "@/api/config";
import { useErrorHandler } from "@/composables/useErrorHandler";

interface CheckinRecord {
  id: number;
  created_at: string;
  platform: string;
  platform_name: string;
  account_index: number;
  status: "ok" | "fail";
  message: string | null;
}

interface CheckinPlatformStat {
  platform: string;
  platform_name: string;
  total: number;
  ok_count: number;
  fail_count: number;
  last_at: string;
  last_status: string;
  last_message: string;
}

interface CheckinRunResult {
  finished_at: string;
  exit_code: number;
  success: boolean;
  output_tail: string;
}

interface CheckinRunState {
  running: boolean;
  started_at: string;
  elapsed_sec: number;
  trigger: string;
  last_result: CheckinRunResult | null;
}

interface CheckinSchedule {
  enabled: boolean;
  scheduler_enabled: boolean;
  run_time: string;
  timezone: string;
  next_run_at: string | null;
}

interface CheckinSetting {
  run_script: string;
  timeout_sec: number;
  auto_run: boolean;
  run_time: string;
  run_tz: string;
}

interface CheckinEnvironment {
  enabled: boolean;
  dc_dir: string;
  dc_dir_exists: boolean;
  run_script: string;
  run_script_exists: boolean;
  db_path: string;
  db_exists: boolean;
  db_script: string;
  db_script_exists: boolean;
}

interface CheckinOverview {
  today: { date: string; ok: number; fail: number; total: number };
  platforms: CheckinPlatformStat[];
  environment: CheckinEnvironment;
  run_state: CheckinRunState;
  schedule: CheckinSchedule;
  redis_ok: boolean;
}

interface CheckinRecordsResponse {
  items: CheckinRecord[];
  total: number;
  page: number;
  page_size: number;
}

const { handleError } = useErrorHandler();

const loading = ref(false);
const records = ref<CheckinRecord[]>([]);
const platforms = ref<CheckinPlatformStat[]>([]);
const environment = reactive<CheckinEnvironment>({
  enabled: false,
  dc_dir: "",
  dc_dir_exists: false,
  run_script: "",
  run_script_exists: false,
  db_path: "",
  db_exists: false,
  db_script: "",
  db_script_exists: false,
});
const runState = reactive<CheckinRunState>({
  running: false,
  started_at: "",
  elapsed_sec: 0,
  trigger: "",
  last_result: null,
});
const schedule = reactive<CheckinSchedule>({
  enabled: false,
  scheduler_enabled: true,
  run_time: "",
  timezone: "",
  next_run_at: null,
});
const redisOk = ref(true);

const statusFilter = ref("");
const platformFilter = ref<string>();
const dateFilter = ref<string>();
const page = ref(1);
const pageSize = ref(parseInt(localStorage.getItem("checkinPageSize") || "15", 10));
const total = ref(0);
const showDetail = ref(false);
const showSetting = ref(false);
const saving = ref(false);
const settingForm = reactive<CheckinSetting>({
  run_script: "run.sh",
  timeout_sec: 1800,
  auto_run: false,
  run_time: "09:00",
  run_tz: "Asia/Shanghai",
});

const tableWrap = ref<HTMLElement | null>(null);
const tableHeight = ref(280);
let tableObserver: ResizeObserver | null = null;
let pollTimer: ReturnType<typeof setTimeout> | null = null;

const firstLine = (message: string | null) => {
  if (!message) return "-";
  const line = message.split("\n").find(item => item.trim());
  return line ? line.trim() : "-";
};

const briefMessage = (message: string | null | undefined) => {
  const line = firstLine(message ?? null);
  return line === "-" ? "无输出" : line;
};

const shortTime = (value: string | null | undefined) => {
  if (!value) return "-";
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  const todayPrefix = `${now.getFullYear()}-${month}-${day}`;
  if (value.startsWith(todayPrefix)) return value.slice(11, 16);
  if (value.length >= 16) return value.slice(5, 16);
  return value;
};

const lastResultText = computed(() => {
  const result = runState.last_result;
  if (!result?.finished_at) return "";
  const time = shortTime(result.finished_at);
  if (result.success) return `上次 ${time} 成功`;
  return `上次 ${time} 失败 · exit ${result.exit_code}`;
});

const scheduleText = computed(() => {
  if (!schedule.enabled) return "未启用定时";
  const next = schedule.next_run_at ? ` · 下次 ${shortTime(schedule.next_run_at)}` : "";
  return `每天 ${schedule.run_time}${next}`;
});

const recordRowClass = ({ row }: { row: CheckinRecord }) =>
  row.status === "fail" ? "checkin-row-fail" : "";

watch(tableWrap, element => {
  tableObserver?.disconnect();
  tableObserver = null;
  if (!element) return;
  tableObserver = new ResizeObserver(entries => {
    const height = entries[0]?.contentRect.height ?? 0;
    if (height > 80) tableHeight.value = Math.floor(height);
  });
  tableObserver.observe(element);
});

const applyOverview = (data: CheckinOverview) => {
  platforms.value = data.platforms;
  Object.assign(environment, data.environment);
  Object.assign(runState, data.run_state);
  Object.assign(schedule, data.schedule);
  redisOk.value = data.redis_ok !== false;
};

const fetchRecords = async () => {
  const response = await api.get<CheckinRecordsResponse>("/v_factory/api/checkin/records", {
    params: {
      status: statusFilter.value || undefined,
      platform: platformFilter.value || undefined,
      date: dateFilter.value || undefined,
      page: page.value,
      page_size: pageSize.value,
    },
  });
  records.value = response.data.items;
  total.value = response.data.total;
};

const fetchAll = async () => {
  loading.value = true;
  try {
    const overview = await api.get<CheckinOverview>("/v_factory/api/checkin/overview");
    applyOverview(overview.data);
    await fetchRecords();
    // 本页在 keep-alive 里：切回来时只剩 fetchAll，若定时任务正在跑要接着轮询，
    // 否则按钮会一直停在「运行中」
    if (runState.running) {
      schedulePoll();
    } else {
      stopPoll();
    }
  } catch (error) {
    handleError(error, "加载签到数据失败");
  } finally {
    loading.value = false;
  }
};

const pollState = async () => {
  try {
    const response = await api.get<{
      run_state: CheckinRunState;
      schedule: CheckinSchedule;
      environment: CheckinEnvironment;
      redis_ok: boolean;
    }>("/v_factory/api/checkin/state");
    Object.assign(runState, response.data.run_state);
    Object.assign(schedule, response.data.schedule);
    Object.assign(environment, response.data.environment);
    redisOk.value = response.data.redis_ok !== false;
    if (runState.running) {
      schedulePoll();
      return;
    }
    stopPoll();
    await fetchAll();
  } catch (error) {
    stopPoll();
    handleError(error, "查询签到状态失败");
  }
};

const stopPoll = () => {
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
};

const schedulePoll = () => {
  stopPoll();
  pollTimer = setTimeout(() => void pollState(), 3000);
};

const handleRun = async () => {
  try {
    await api.post("/v_factory/api/checkin/run");
    ElMessage.success("已开始运行签到，完成后自动刷新");
    runState.running = true;
    runState.elapsed_sec = 0;
    schedulePoll();
  } catch (error) {
    handleError(error, "启动签到失败");
  }
};

const onFilterChange = () => {
  page.value = 1;
  void fetchRecords();
};

const openSetting = async () => {
  try {
    const response = await api.get<{ setting: CheckinSetting; redis_ok: boolean }>(
      "/v_factory/api/checkin/setting",
    );
    Object.assign(settingForm, response.data.setting);
    redisOk.value = response.data.redis_ok !== false;
    showSetting.value = true;
  } catch (error) {
    handleError(error, "读取签到设置失败");
  }
};

const saveSetting = async () => {
  saving.value = true;
  try {
    const response = await api.put<{
      setting: CheckinSetting;
      schedule: CheckinSchedule;
    }>("/v_factory/api/checkin/setting", { ...settingForm });
    Object.assign(settingForm, response.data.setting);
    Object.assign(schedule, response.data.schedule);
    showSetting.value = false;
    ElMessage.success("已保存，定时任务已按新配置重建");
    await fetchAll();
  } catch (error) {
    handleError(error, "保存签到设置失败");
  } finally {
    saving.value = false;
  }
};

const onPageSizeChange = () => {
  page.value = 1;
  localStorage.setItem("checkinPageSize", String(pageSize.value));
  void fetchRecords();
};

onMounted(async () => {
  await fetchAll();
  if (runState.running) {
    schedulePoll();
  }
});

onBeforeUnmount(() => {
  stopPoll();
  tableObserver?.disconnect();
  tableObserver = null;
});

defineExpose({ refresh: fetchAll });
</script>

<style scoped>
.checkin-table :deep(.el-table__body tr.checkin-row-fail > td.el-table__cell) {
  background-color: #fff1f2;
}
</style>
