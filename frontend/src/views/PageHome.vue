<template>
  <div class="flex h-[calc(100vh-120px)] min-h-0 flex-col gap-3 overflow-auto pb-1">
    <header class="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
      <div class="min-w-0">
        <div class="flex flex-wrap items-center gap-2">
          <h1 class="text-base font-semibold text-gray-800">总览</h1>
          <el-button
            type="plain"
            size="small"
            title="刷新"
            :disabled="loading"
            @click="loadOverview"
          >
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

      <div class="mt-3 grid gap-x-8 gap-y-3 md:grid-cols-3">
        <div v-for="meter in meters" :key="meter.label" class="min-w-0">
          <div class="flex items-baseline justify-between gap-2">
            <span class="flex items-center gap-1.5 text-xs text-gray-500">
              <el-icon :size="13"><component :is="meter.icon" /></el-icon>
              {{ meter.label }}
            </span>
            <span
              class="text-sm font-medium tabular-nums"
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
        <span class="ml-auto text-xs text-gray-400">按严重程度排序</span>
      </div>

      <ul class="mt-1 grid grid-cols-1 gap-x-6 sm:grid-cols-2">
        <li v-if="loaded && !alerts.length" class="px-1.5 py-4 text-sm text-gray-400 sm:col-span-2">
          没有要处理的
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

        <div class="mt-3 flex flex-wrap items-center gap-1.5">
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

        <div class="mt-auto space-y-1.5 border-t border-gray-100 pt-3">
          <div v-if="loaded && !mod.lines.length" class="text-xs text-gray-400">暂无</div>
          <div
            v-for="line in mod.lines"
            :key="line.title"
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
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import {
  ArrowRight,
  Calendar,
  ChatDotRound,
  Cpu,
  Document,
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
import {
  getHomeOverview,
  type HomeAlert,
  type HomeLine,
  type HomeMeter,
  type HomeOverview,
  type HomeProgress,
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

interface ModuleView extends ModuleDef {
  stats: HomeStat[];
  lines: HomeLine[];
}

const WEEKDAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
const METER_META: Record<string, { label: string; icon: Component }> = {
  cpu: { label: "CPU", icon: Cpu },
  memory: { label: "内存", icon: Histogram },
  disk: { label: "硬盘", icon: FolderOpened },
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

const host = computed(() => overview.value?.host || "");
const progresses = computed<HomeProgress[]>(() => overview.value?.progress ?? []);
const alerts = computed<HomeAlert[]>(() => overview.value?.alerts ?? []);
const dangerCount = computed(() => alerts.value.filter(alert => alert.tone === "danger").length);
const warnCount = computed(() => alerts.value.filter(alert => alert.tone === "warn").length);

const meters = computed<MeterView[]>(() =>
  (overview.value?.meters ?? []).map(meter => {
    const meta = METER_META[meter.key] ?? { label: meter.key, icon: Monitor };
    return { ...meter, label: meta.label, icon: meta.icon };
  })
);

const modules = computed<ModuleView[]>(() =>
  MODULE_DEFS.map(def => {
    const remote = overview.value?.modules.find(item => item.key === def.key);
    return {
      ...def,
      stats: remote?.stats ?? [],
      lines: remote?.lines ?? [],
    };
  })
);

const loadOverview = async () => {
  loading.value = true;
  try {
    overview.value = await getHomeOverview();
    loaded.value = true;
  } catch (error) {
    handleError(error, "首页总览加载失败");
  } finally {
    loading.value = false;
  }
};

onMounted(() => {
  void loadOverview();
});
usePageRefresh(loadOverview);

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
