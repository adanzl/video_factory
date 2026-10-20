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
        v-if="!environment.run_script_exists || !environment.db_script_exists"
        type="warning"
        show-icon
        :closable="false"
      >
        <template #title>
          <span v-if="!environment.dc_dir_exists">签到目录不存在：{{ environment.dc_dir }}</span>
          <span v-else-if="!environment.run_script_exists"
            >找不到运行脚本：{{ environment.run_script }}</span
          >
          <span v-else>找不到查询脚本：{{ environment.db_script }}</span>
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
        </span>
      </div>

      <div ref="tableWrap" class="min-h-0 flex-1 overflow-hidden">
        <el-table
          :data="records"
          :height="tableHeight"
          stripe
          class="w-full [&_.el-table\_\_body_tr.checkin-row-fail>td]:bg-rose-50!"
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
          <el-table-column label="ID" prop="id" width="72" />
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
              <el-tooltip
                placement="top"
                :show-after="300"
                :disabled="!row.message"
                popper-class="max-w-96 [&_.el-popper\_\_arrow]:size-2.5 [&_.el-popper\_\_arrow::before]:size-2.5"
              >
                <template #content>
                  <div class="max-w-96 text-xs leading-5 break-all whitespace-pre-wrap">
                    {{ row.message }}
                  </div>
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

    <el-dialog v-model="showSetting" title="签到设置" width="640px" align-center>
      <div class="flex max-h-[70vh] flex-col gap-5 overflow-auto pr-1">
        <section class="overflow-hidden rounded-md border border-gray-200">
          <div class="grid grid-cols-2 divide-x divide-gray-100">
            <label class="block px-3 py-3">
              <span class="text-xs text-gray-500">运行脚本</span>
              <el-input
                v-model="settingForm.run_script"
                placeholder="run.sh"
                size="small"
                class="mt-1.5"
              />
              <span class="mt-1 block text-xs text-gray-400">DC_DIR 下的文件名</span>
            </label>
            <label class="block px-3 py-3">
              <span class="text-xs text-gray-500">超时</span>
              <div class="mt-1.5 flex items-center gap-2">
                <el-input-number
                  v-model="settingForm.timeout_sec"
                  :min="60"
                  :max="86400"
                  :step="60"
                  size="small"
                  controls-position="right"
                />
                <span class="text-xs text-gray-400">秒</span>
              </div>
            </label>
          </div>
          <div class="flex items-center justify-between gap-3 border-t border-gray-100 px-3 py-3">
            <div class="min-w-0">
              <div class="text-xs text-gray-500">每天定时</div>
              <div class="mt-1 text-xs text-gray-400">
                {{ schedule.enabled ? `已生效 ${scheduleText}` : "当前未启用" }}
                · 按本机时区
              </div>
            </div>
            <div class="flex shrink-0 items-center gap-2">
              <el-time-picker
                v-model="settingForm.run_time"
                format="HH:mm"
                value-format="HH:mm"
                placeholder="09:00"
                :disabled="!settingForm.auto_run"
                size="small"
                class="w-28!"
              />
              <el-switch v-model="settingForm.auto_run" />
            </div>
          </div>
        </section>

        <section>
          <div class="mb-2 text-xs text-gray-400">环境</div>
          <div class="overflow-hidden rounded-md border border-gray-200">
            <div
              v-for="row in environmentRows"
              :key="row.label"
              class="flex items-center gap-3 border-b border-gray-100 px-3 py-2 last:border-b-0"
            >
              <span class="w-16 shrink-0 text-xs text-gray-500">{{ row.label }}</span>
              <span class="min-w-0 flex-1 truncate font-mono text-xs text-gray-700" :title="row.path">
                {{ row.path || "-" }}
              </span>
              <el-tag :type="row.ok ? 'success' : 'danger'" size="small" effect="plain">
                {{ row.ok ? "存在" : "缺失" }}
              </el-tag>
            </div>
          </div>
        </section>

        <section>
          <div class="mb-2 flex items-baseline justify-between gap-3">
            <span class="text-xs text-gray-400">上次输出</span>
            <span
              v-if="lastResultText"
              class="text-xs"
              :class="runState.last_result?.success ? 'text-gray-400' : 'text-red-500'"
            >
              {{ lastResultText }}
            </span>
          </div>
          <pre
            class="max-h-48 overflow-auto rounded-md border border-gray-200 bg-gray-50 px-3 py-2 font-mono text-xs leading-5 whitespace-pre-wrap text-gray-600"
            >{{ runState.last_result?.output_tail || "还没有运行记录" }}</pre
          >
        </section>
      </div>
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
import {
  fetchCheckinOverview,
  fetchCheckinSetting,
  fetchCheckinState,
  listCheckinRecords,
  saveCheckinSetting,
  startCheckinRun,
} from "@/api/api-checkin";
import { useErrorHandler } from "@/composables/useErrorHandler";
import type {
  CheckinEnvironment,
  CheckinOverview,
  CheckinPlatformStat,
  CheckinRecord,
  CheckinRunState,
  CheckinSchedule,
  CheckinSetting,
} from "@/types/checkin";

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
  next_run_at: null,
});
const redisOk = ref(true);

const statusFilter = ref("");
const platformFilter = ref<string>();
const dateFilter = ref<string>();
const page = ref(1);
const pageSize = ref(parseInt(localStorage.getItem("checkinPageSize") || "15", 10));
const total = ref(0);
const showSetting = ref(false);
const saving = ref(false);
const settingForm = reactive<CheckinSetting>({
  run_script: "run.sh",
  timeout_sec: 1800,
  auto_run: false,
  run_time: "09:00",
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

const environmentRows = computed(() => [
  { label: "目录", path: environment.dc_dir, ok: environment.dc_dir_exists },
  { label: "运行脚本", path: environment.run_script, ok: environment.run_script_exists },
  { label: "查询脚本", path: environment.db_script, ok: environment.db_script_exists },
]);

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
  const data = await listCheckinRecords({
    status: statusFilter.value || undefined,
    platform: platformFilter.value || undefined,
    date: dateFilter.value || undefined,
    page: page.value,
    page_size: pageSize.value,
  });
  records.value = data.items;
  total.value = data.total;
};

const fetchAll = async () => {
  loading.value = true;
  try {
    applyOverview(await fetchCheckinOverview());
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
    const data = await fetchCheckinState();
    Object.assign(runState, data.run_state);
    Object.assign(schedule, data.schedule);
    Object.assign(environment, data.environment);
    redisOk.value = data.redis_ok !== false;
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
    await startCheckinRun();
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
    const data = await fetchCheckinSetting();
    Object.assign(settingForm, data.setting);
    redisOk.value = data.redis_ok !== false;
    showSetting.value = true;
  } catch (error) {
    handleError(error, "读取签到设置失败");
  }
};

const saveSetting = async () => {
  saving.value = true;
  try {
    const data = await saveCheckinSetting({ ...settingForm });
    Object.assign(settingForm, data.setting);
    Object.assign(schedule, data.schedule);
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
