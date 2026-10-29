<template>
  <div class="flex h-[calc(100vh-120px)] min-h-0 flex-col gap-3 overflow-auto pb-1">
    <header class="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
      <div class="min-w-0">
        <div class="flex flex-wrap items-center gap-2">
          <h1 class="text-base font-semibold text-gray-800">总览</h1>
          <el-button size="small" plain title="刷新" :disabled="loading" @click="loadOverview()">
            <el-icon><Refresh /></el-icon>
          </el-button>
          <span class="text-xs text-gray-400">{{ todayLabel }}</span>
          <span v-if="loading" class="text-xs text-gray-400">加载中</span>
        </div>
        <p class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-gray-500">
          <span v-if="dangerCount" class="text-red-600">{{ dangerCount }} 项失败</span>
          <span v-if="warnCount" class="text-amber-600">{{ warnCount }} 项待处理</span>
          <span>共 {{ alerts.length }} 项待跟进</span>
        </p>
      </div>

      <dl class="flex flex-wrap items-center gap-y-1 text-xs">
        <div
          v-for="progress in progresses"
          :key="progress.label"
          class="flex items-baseline gap-1 border-l border-gray-200 px-3 first:border-l-0 first:pl-0 last:pr-0"
        >
          <dt class="text-gray-500">{{ progress.label }}</dt>
          <dd class="font-medium tabular-nums text-gray-700">{{ progress.value }}</dd>
        </div>
      </dl>
    </header>

    <section class="rounded-xl border border-gray-200 bg-white px-4 py-3">
      <div class="flex items-center gap-2">
        <span class="flex size-6 items-center justify-center rounded-md bg-blue-50 text-blue-600">
          <el-icon :size="14"><Monitor /></el-icon>
        </span>
        <h2 class="text-sm font-medium">机器</h2>
        <span class="text-xs text-gray-400">{{ host }}</span>
      </div>

      <div class="mt-3 grid gap-x-8 gap-y-3 sm:grid-cols-2 xl:grid-cols-4">
        <div v-for="meter in meters" :key="meter.label" class="min-w-0">
          <div class="flex items-baseline justify-between gap-2">
            <span
              class="flex shrink-0 items-center gap-1.5 whitespace-nowrap text-xs text-gray-500"
            >
              <el-icon :size="13"><component :is="meter.icon" /></el-icon>
              {{ meter.label }}
            </span>
            <span
              class="min-w-0 truncate text-right text-sm font-medium tabular-nums"
              :class="toneText(meterTone(meter.percent)) || 'text-gray-700'"
            >
              {{ meter.value }}
            </span>
          </div>
          <div class="mt-1.5 h-1 overflow-hidden rounded-full bg-gray-100">
            <div
              class="h-full rounded-full"
              :class="barClass(meter.percent)"
              :style="{ width: `${meter.percent}%` }"
            />
          </div>
          <div class="mt-1 truncate text-xs text-gray-400">{{ meter.note }}</div>
        </div>
      </div>
    </section>

    <section class="rounded-xl border border-gray-200 bg-white px-4 py-3">
      <div class="flex items-center gap-2">
        <span class="flex size-6 items-center justify-center rounded-md bg-red-50 text-red-600">
          <el-icon :size="14"><Warning /></el-icon>
        </span>
        <h2 class="text-sm font-medium">需要处理</h2>
        <span class="rounded-full bg-gray-100 px-1.5 py-0.5 text-xs tabular-nums text-gray-500">
          {{ alerts.length }}
        </span>
        <span v-if="alerts.length" class="ml-auto text-xs text-gray-400">按严重程度排序</span>
      </div>

      <ul class="mt-1 grid grid-cols-1 gap-x-6 sm:grid-cols-2">
        <li v-if="!alerts.length" class="col-span-full px-1.5 py-3 text-sm text-gray-400">
          {{ loaded ? "没有要处理的" : "—" }}
        </li>
        <li v-for="alert in alerts" :key="`${alert.to}-${alert.title}-${alert.note}`">
          <button
            type="button"
            class="group -mx-1.5 flex w-full cursor-pointer items-center gap-2.5 rounded-md px-1.5 py-2 text-left transition hover:bg-gray-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
            @click="go(alert.to)"
          >
            <span class="size-1.5 shrink-0 rounded-full" :class="dotClass(alert.tone)" />
            <span class="shrink-0 rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500">
              {{ alert.module }}
            </span>
            <span
              v-if="alert.id != null"
              class="shrink-0 font-mono text-xs tabular-nums text-gray-400"
            >
              #{{ alert.id }}
            </span>
            <span class="min-w-0 flex-1 truncate text-sm">{{ alert.title }}</span>
            <span class="shrink-0 text-xs" :class="toneText(alert.tone)">{{ alert.note }}</span>
            <el-icon
              :size="12"
              class="shrink-0 text-gray-300 transition group-hover:translate-x-0.5 group-hover:text-gray-500"
            >
              <ArrowRight />
            </el-icon>
          </button>
        </li>
      </ul>
    </section>

    <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <button
        v-for="mod in modules"
        :key="mod.title"
        type="button"
        class="group flex h-full min-w-0 cursor-pointer flex-col rounded-xl border border-gray-200 bg-white p-4 text-left transition hover:border-gray-300 hover:bg-gray-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
        @click="go(mod.to)"
      >
        <div class="flex items-center gap-2.5">
          <span
            class="flex size-8 shrink-0 items-center justify-center rounded-lg"
            :class="accentTile(mod.accent)"
          >
            <el-icon :size="16"><component :is="mod.icon" /></el-icon>
          </span>
          <span class="min-w-0 flex-1 truncate text-sm font-medium">{{ mod.title }}</span>
          <el-icon
            :size="13"
            class="shrink-0 text-gray-300 transition group-hover:translate-x-0.5 group-hover:text-gray-500"
          >
            <ArrowRight />
          </el-icon>
        </div>

        <div class="mt-3 flex min-h-6 flex-wrap items-center gap-1.5">
          <span
            v-for="stat in mod.stats"
            :key="stat.label"
            class="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs"
            :class="
              stat.tone === 'danger'
                ? 'bg-red-50'
                : stat.tone === 'warn'
                  ? 'bg-amber-50'
                  : 'bg-gray-100'
            "
          >
            <span :class="toneText(stat.tone) || 'text-gray-500'">{{ stat.label }}</span>
            <span class="font-medium tabular-nums" :class="toneText(stat.tone) || 'text-gray-700'">
              {{ stat.value }}
            </span>
          </span>
        </div>

        <div class="mt-3 min-h-11 space-y-1.5 border-t border-gray-100 pt-3">
          <div v-if="!mod.lines.length" class="truncate text-xs text-gray-400">
            {{ loaded ? "暂无" : "—" }}
          </div>
          <div
            v-for="line in mod.lines"
            :key="`${line.title}-${line.note}`"
            class="flex items-baseline justify-between gap-2"
          >
            <span class="min-w-0 truncate text-xs text-gray-600">{{ line.title }}</span>
            <span class="shrink-0 text-xs text-gray-400">{{ line.note }}</span>
          </div>
        </div>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Component } from "vue";
import { computed, onActivated, onDeactivated, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import {
  ArrowRight,
  Calendar,
  ChatDotRound,
  Cpu,
  Document,
  Files,
  FolderOpened,
  Headset,
  Histogram,
  List,
  Medal,
  Monitor,
  Refresh,
  Search,
  VideoCamera,
  Warning,
} from "@element-plus/icons-vue";
import { formatDailyStoryType } from "@/api/api-daily-story";
import {
  getHomeOverview,
  type HomeAlert,
  type HomeLine,
  type HomeMeter,
  type HomeOverview,
  type HomeStat,
} from "@/api/api-home";
import { useErrorHandler } from "@/composables/useErrorHandler";
import { usePageRefresh } from "@/stores/app";

type Tone = "danger" | "warn";
type Accent = "blue" | "emerald" | "amber" | "slate";

interface MeterView extends HomeMeter {
  label: string;
  icon: Component;
}

interface ModuleDef {
  key: string;
  title: string;
  icon: Component;
  to: string;
  accent: Accent;
}

interface StatView {
  label: string;
  value: number | string;
  tone?: Tone;
}

interface LineView {
  title: string;
  note: string;
  to: string;
}

interface ModuleView extends ModuleDef {
  stats: StatView[];
  lines: LineView[];
}

interface AlertView {
  module: string;
  title: string;
  note: string;
  tone: Tone;
  to: string;
  id?: number;
}

interface ProgressView {
  label: string;
  value: string;
}

const WEEKDAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
const METER_META: Record<string, { label: string; icon: Component }> = {
  cpu: { label: "CPU", icon: Cpu },
  memory: { label: "内存", icon: Histogram },
  disk: { label: "硬盘", icon: FolderOpened },
  project: { label: "项目", icon: Files },
};

const MODULE_DEFS: ModuleDef[] = [
  { key: "jobs", title: "任务队列", icon: List, to: "/jobs", accent: "blue" },
  {
    key: "daily_story",
    title: "日常故事",
    icon: ChatDotRound,
    to: "/daily-story",
    accent: "emerald",
  },
  { key: "gold_chat", title: "金牌故事", icon: Medal, to: "/gold-chat", accent: "amber" },
  { key: "topic", title: "选题库", icon: Document, to: "/topic", accent: "slate" },
  { key: "video", title: "视频素材", icon: VideoCamera, to: "/materials/video", accent: "blue" },
  { key: "audio", title: "音频素材", icon: Headset, to: "/materials/audio", accent: "emerald" },
  { key: "clips", title: "片段搜索", icon: Search, to: "/clips", accent: "slate" },
  { key: "checkin", title: "每日签到", icon: Calendar, to: "/tools", accent: "amber" },
];

const router = useRouter();
const { handleError } = useErrorHandler();

const now = new Date();
const todayLabel = `${now.getMonth() + 1}月${now.getDate()}日 ${WEEKDAYS[now.getDay()]}`;

const loading = ref(false);
const loaded = ref(false);
const overview = ref<HomeOverview | null>(null);

const PROGRESS_TEXT: Record<string, { label: string; unit: string }> = {
  stories_today: { label: "今日生成", unit: "篇" },
  running: { label: "正在跑", unit: "个" },
  published_today: { label: "今日发布", unit: "条" },
};

const STAT_LABEL: Record<string, Record<string, string>> = {
  jobs: {
    failed: "失败",
    pending: "待处理",
    idle: "待处理",
    queued: "排队中",
    running: "运行中",
    done: "已完成",
  },
  daily_story: { today: "今天生成", no_job: "无任务", has_job: "有任务" },
  gold_chat: {
    not_imported: "未导入",
    review_pending: "待审核",
    convert_failed: "转换失败",
  },
  topic: { pending: "待打分", queued: "可入队", enqueued: "已入队" },
  video: { active: "正常", analyzing: "分析中", analyze_failed: "分析失败" },
  audio: { total: "素材", today: "今天新增" },
  clips: { available: "可用来源" },
  checkin: { ok: "今日成功", fail: "今日失败" },
};

const STAGE_LABEL: Record<string, string> = {
  prepare: "基底",
  script: "脚本",
  tts: "配音",
  segment: "分镜",
  intro: "片头",
  merge: "合成",
  publish: "发布",
};

const PROVIDER_LABEL: Record<string, string> = {
  pexels: "Pexels",
  pixabay: "Pixabay",
  nasa: "NASA",
};

const host = computed(() => overview.value?.host || "");
const progresses = computed<ProgressView[]>(() =>
  (overview.value?.progress ?? []).map(item => {
    if (!item.key) return { label: item.label ?? "", value: String(item.value) };
    const text = PROGRESS_TEXT[item.key];
    return {
      label: text?.label ?? item.key,
      value: text ? `${item.value} ${text.unit}` : String(item.value),
    };
  })
);
const alerts = computed<AlertView[]>(() =>
  (overview.value?.alerts ?? []).map(alert => ({
    module: moduleTitle(alert.module),
    title: lineTitle(alert.module, alert),
    note: lineNote(alert.module, alert),
    tone: alert.tone,
    to: alert.to,
    id: alertRecordId(alert),
  }))
);
const dangerCount = computed(() => alerts.value.filter(alert => alert.tone === "danger").length);
const warnCount = computed(() => alerts.value.filter(alert => alert.tone === "warn").length);

const METER_KEYS = ["cpu", "memory", "disk", "project"] as const;

const meters = computed<MeterView[]>(() =>
  METER_KEYS.map(key => {
    const meta = METER_META[key];
    const remote = overview.value?.meters.find(item => item.key === key);
    return {
      key,
      label: meta.label,
      icon: meta.icon,
      value: remote?.value || "—",
      percent: remote?.percent ?? 0,
      note: meterNote(remote),
    };
  })
);

const presentStat = (moduleKey: string, stat: HomeStat): StatView => {
  if (!stat.key) {
    if (moduleKey === "jobs" && stat.label === "停住") {
      return { label: "待处理", value: stat.value };
    }
    return { label: stat.label ?? "", value: stat.value, tone: stat.tone };
  }
  if (moduleKey === "checkin" && stat.key === "disabled") {
    return { label: "状态", value: "未启用" };
  }
  if (moduleKey === "checkin" && stat.key === "unavailable") {
    return { label: "状态", value: "读不到", tone: "warn" };
  }
  const value = typeof stat.value === "number" ? stat.value : Number(stat.value);
  return {
    label: STAT_LABEL[moduleKey]?.[stat.key] ?? stat.key,
    value: stat.value,
    tone: statTone(moduleKey, stat.key, Number.isFinite(value) ? value : 0),
  };
};

const modules = computed<ModuleView[]>(() =>
  MODULE_DEFS.map(def => {
    const remote = overview.value?.modules.find(item => item.key === def.key);
    return {
      ...def,
      stats: (remote?.stats ?? []).map(stat => presentStat(def.key, stat)),
      lines: (remote?.lines ?? []).map(line => ({
        title: lineTitle(def.key, line),
        note: lineNote(def.key, line),
        to: line.to,
      })),
    };
  })
);

function alertRecordId(alert: HomeAlert): number | undefined {
  if (typeof alert.id === "number") return alert.id;
  const matched = /[?&]id=(\d+)/.exec(alert.to);
  return matched ? Number(matched[1]) : undefined;
}

function moduleTitle(key: string): string {
  return MODULE_DEFS.find(item => item.key === key)?.title ?? key;
}

function statTone(moduleKey: string, statKey: string, value: number): Tone | undefined {
  if (value <= 0) return undefined;
  if (moduleKey === "jobs" && statKey === "failed") return "danger";
  if (moduleKey === "daily_story" && statKey === "no_job") return "warn";
  if (moduleKey === "gold_chat" && (statKey === "not_imported" || statKey === "review_pending")) {
    return "warn";
  }
  if (moduleKey === "gold_chat" && statKey === "convert_failed") return "danger";
  if (moduleKey === "video" && statKey === "analyze_failed") return "danger";
  if (moduleKey === "checkin" && statKey === "fail") return "danger";
  return undefined;
}

function stageLabel(stage?: string): string {
  if (!stage) return "当前阶段";
  return STAGE_LABEL[stage] ?? stage;
}

function formatDuration(raw: number | null | undefined): string {
  if (raw == null || Number.isNaN(Number(raw))) return "—";
  const sec = Number(raw);
  return sec < 10 ? `${sec.toFixed(1)} 秒` : `${Math.round(sec)} 秒`;
}

function lineTitle(moduleKey: string, line: HomeLine): string {
  if (!line.code) return line.title;
  if (moduleKey === "clips" && line.code === "configured") {
    return (line.providers ?? []).map(name => PROVIDER_LABEL[name] ?? name).join(" / ");
  }
  if (moduleKey === "clips") return "没有可用的来源";
  if (moduleKey === "checkin" && line.code === "disabled") return "未配置签到目录";
  if (moduleKey === "checkin" && line.code === "unavailable") return "签到结果暂时读不到";
  if (moduleKey === "checkin" && line.code === "all_ok") return "今天";
  if (moduleKey === "checkin" && line.code === "fail") {
    const name = line.title || "账号";
    return line.account_index != null && line.account_index !== ""
      ? `${name} · 账号 ${line.account_index}`
      : name;
  }
  return line.title;
}

function lineNote(moduleKey: string, line: HomeLine): string {
  if (!line.code) {
    if (line.note?.startsWith("停在")) return line.note.slice(2);
    return line.note ?? "";
  }
  if (moduleKey === "jobs") {
    const stage = stageLabel(line.stage);
    return line.code === "failed" ? `${stage}失败` : stage;
  }
  if (moduleKey === "daily_story") {
    return line.story_type ? formatDailyStoryType(line.story_type) : "还没建任务";
  }
  if (moduleKey === "gold_chat") {
    if (line.code === "review_pending") return "待审核";
    if (line.code === "convert_failed") return "转换失败";
    return "未导入";
  }
  if (moduleKey === "topic") return line.score == null ? "待打分" : `${line.score} 分`;
  if (moduleKey === "video") {
    if (line.code === "analyze_failed") return "分析失败";
    if (line.code === "analyzing") return "分析中";
    if (line.code === "active") return "正常";
    return line.code;
  }
  if (moduleKey === "audio") return formatDuration(line.duration_sec);
  if (moduleKey === "clips") return line.code === "configured" ? "已配置" : "未配置密钥";
  if (moduleKey === "checkin") {
    if (line.code === "fail") return "签到失败";
    if (line.code === "all_ok") return "全部成功";
  }
  return "";
}

function meterNote(meter?: HomeMeter): string {
  if (!meter) return "—";
  if (meter.key === "memory" && meter.state === "unreadable") return "读不到内存";
  if (meter.key === "project" && meter.state === "missing") return "data 不存在";
  if (meter.key === "project" && meter.state === "unreadable") return "data 读不到";
  if (meter.key === "cpu" && meter.threads) {
    return meter.note ? `${meter.note} · ${meter.threads} 线程` : `${meter.threads} 线程`;
  }
  return meter.note || "—";
}

const REFRESH_MS = 15000;
let refreshTimer: ReturnType<typeof setInterval> | null = null;
let overviewInFlight = false;

const loadOverview = async (opts?: { quiet?: boolean }) => {
  if (overviewInFlight) return;
  overviewInFlight = true;
  const quiet = opts?.quiet === true;
  if (!quiet) loading.value = true;
  try {
    overview.value = await getHomeOverview();
    loaded.value = true;
  } catch (error) {
    if (!quiet) handleError(error, "首页总览加载失败");
  } finally {
    overviewInFlight = false;
    loading.value = false;
  }
};

function startAutoRefresh() {
  if (refreshTimer != null) return;
  refreshTimer = setInterval(() => {
    void loadOverview({ quiet: true });
  }, REFRESH_MS);
}

function stopAutoRefresh() {
  if (refreshTimer == null) return;
  clearInterval(refreshTimer);
  refreshTimer = null;
}

onMounted(() => {
  void loadOverview();
  startAutoRefresh();
});
onActivated(startAutoRefresh);
onDeactivated(stopAutoRefresh);
onUnmounted(stopAutoRefresh);
usePageRefresh(() => loadOverview());

const meterTone = (percent: number): Tone | undefined => {
  if (percent >= 90) return "danger";
  if (percent >= 75) return "warn";
  return undefined;
};

const toneText = (tone?: Tone) => {
  if (tone === "danger") return "text-red-600";
  if (tone === "warn") return "text-amber-600";
  return "";
};

const dotClass = (tone: Tone) => (tone === "danger" ? "bg-red-500" : "bg-amber-500");

const barClass = (percent: number) => {
  const tone = meterTone(percent);
  if (tone === "danger") return "bg-red-600";
  if (tone === "warn") return "bg-amber-600";
  return "bg-blue-600";
};

const accentTile = (accent: Accent) => {
  switch (accent) {
    case "emerald":
      return "bg-emerald-50 text-emerald-600";
    case "amber":
      return "bg-amber-50 text-amber-600";
    case "slate":
      return "bg-slate-100 text-slate-700";
    default:
      return "bg-blue-50 text-blue-600";
  }
};

const go = (path: string) => {
  void router.push(path);
};
</script>
