<template>
  <div>
    <StageActionBar
      :loading="submitting"
      :disabled="actionDisabled"
      :disabled-reason="actionDisabledReason"
      @primary="handleRun(false)"
      @to-end="handleRun(true)"
    />

    <div :class="STAGE_TWO_COL_CLASS">
      <div class="min-w-70 max-w-full shrink-0 basis-105">
        <div :class="STAGE_PANEL_CLASS">
          <div :class="STAGE_PANEL_TITLE_CLASS">角色配音配置</div>
          <el-form :label-width="STAGE_FORM_LABEL_WIDTH" :class="STAGE_FORM_CLASS">
            <el-form-item v-for="spk in speakers" :key="spk.key" :label="spk.label">
              <div class="flex w-full flex-wrap items-center gap-2">
                <span class="shrink-0 text-xs text-gray-500">声音</span>
                <el-select
                  v-model="speakerConfigs[spk.key].voice_id"
                  filterable
                  class="min-w-24 flex-1!"
                >
                  <el-option
                    v-for="voice in TTS_VOICE_OPTIONS"
                    :key="voice.value"
                    :label="voice.label"
                    :value="voice.value"
                  />
                </el-select>
                <span class="shrink-0 text-xs text-gray-500">语速</span>
                <el-input-number
                  v-model="speakerConfigs[spk.key].speech_rate"
                  :min="0.5"
                  :max="2"
                  :step="0.05"
                  :precision="2"
                  controls-position="right"
                  class="w-24! shrink-0"
                />
              </div>
            </el-form-item>
            <el-form-item label="句间停留">
              <div class="flex items-center gap-2">
                <el-input-number
                  v-model="phraseGapSec"
                  :min="0"
                  :max="3"
                  :step="0.1"
                  :precision="1"
                  controls-position="right"
                  class="w-32!"
                />
                <span class="text-xs text-gray-400">秒</span>
              </div>
            </el-form-item>
          </el-form>
          <el-form :label-width="STAGE_FORM_LABEL_WIDTH" class="[&_.el-form-item]:mb-2 mt-2">
            <el-form-item label="音频路径">
              <span class="break-all text-gray-600">{{ job.audio_path || "-" }}</span>
            </el-form-item>
            <el-form-item label="TTS 用量">
              <span class="text-gray-700">{{ ttsTotalCharactersText }}</span>
            </el-form-item>
            <el-form-item label="实测语速">
              <div class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <span class="text-gray-700">{{ measuredSpeechRateText }}</span>
                <span class="text-xs text-gray-400">文案字数/音频时间</span>
              </div>
            </el-form-item>
          </el-form>
        </div>
      </div>

      <div :class="STAGE_COL_WIDE_RIGHT_CLASS">
        <div :class="STAGE_PANEL_CLASS">
          <div :class="STAGE_PANEL_TITLE_CLASS">音频预览</div>
          <div v-if="audioUrl" class="w-full overflow-hidden rounded-lg border border-gray-200 bg-gray-50 p-4">
            <div class="mb-3">
              <div class="mb-2 text-sm text-gray-600">倍速</div>
              <el-radio-group v-model="playbackSpeed" size="small" class="flex flex-wrap gap-1">
                <el-radio-button
                  v-for="speed in AUDIO_PLAYBACK_SPEED_OPTIONS"
                  :key="speed"
                  :value="speed"
                >
                  {{ speed.toFixed(1) }}x
                </el-radio-button>
              </el-radio-group>
            </div>
            <audio
              ref="audioRef"
              :key="audioUrl"
              class="block w-full"
              :src="lazyAudioUrl"
              :crossorigin="MEDIA_CROSS_ORIGIN"
              controls
              preload="metadata"
              @error="onAudioError"
              @loadedmetadata="applyPlaybackSpeed"
            />
          </div>
          <div v-else-if="!job.audio_path" :class="STAGE_EMPTY_CLASS">
            暂无配音音频，请先生成
          </div>
          <el-alert
            v-else-if="loadError"
            type="warning"
            :title="loadError"
            :closable="false"
            class="mt-2"
          />
        </div>
      </div>
    </div>

    <div v-if="segmentClips.length" class="mt-4">
      <div :class="STAGE_PANEL_CLASS">
        <div :class="STAGE_PANEL_TITLE_CLASS">分镜音频</div>
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div
            v-for="item in segmentClips"
            :key="item.segment_index"
            class="rounded border border-gray-100 bg-gray-50 px-3 py-2"
          >
            <div class="mb-1 flex items-center gap-2">
              <span class="shrink-0 rounded bg-blue-100 px-1.5 py-0.5 text-xs font-medium text-blue-700">
                #{{ item.segment_index }}
              </span>
              <el-tooltip v-if="item.text" placement="top" :show-after="300">
                <template #content>
                  <div class="max-w-sm whitespace-pre-wrap wrap-break-word text-xs">{{ item.text }}</div>
                </template>
                <div class="line-clamp-2 min-h-[2lh] flex-1 cursor-default text-xs leading-relaxed wrap-break-word text-gray-600">
                  {{ item.text }}
                </div>
              </el-tooltip>
            </div>
            <audio
              v-if="item.clipUrl"
              class="block w-full"
              :src="item.clipUrl"
              controls
              preload="metadata"
            />
            <div v-else class="py-1 text-xs text-gray-400">音频不可用</div>
          </div>
        </div>
      </div>
    </div>

    <StageLogsSection :logs="logs" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { runJobStageAction } from "@/api/api-jobs";
import { getMediaDuration, getMediaFileUrl } from "@/api/api-media";
import { DEFAULT_TTS_VOICE, TTS_VOICE_MOM, TTS_VOICE_OPTIONS, TTS_VOICE_ZHAO } from "@/constants/tts-voices";
import type { JobDetail, JobLog } from "@/types/jobs";
import type { ScriptJson } from "@/types/jobs/script";
import type { RunStageActionPayload } from "@/types/jobs/stageAction";
import { MEDIA_CROSS_ORIGIN, lazyMediaSrc } from "@/utils/media";
import { useErrorHandler } from "@/composables/useErrorHandler";
import StageActionBar from "../detail/StageActionBar.vue";
import StageLogsSection from "../detail/StageLogsSection.vue";
import {
  STAGE_COL_WIDE_RIGHT_CLASS,
  STAGE_EMPTY_CLASS,
  STAGE_FORM_CLASS,
  STAGE_FORM_LABEL_WIDTH,
  STAGE_PANEL_CLASS,
  STAGE_PANEL_TITLE_CLASS,
  STAGE_TWO_COL_CLASS,
} from "../detail/stageLayout";

const AUDIO_PLAYBACK_SPEED_OPTIONS = Array.from({ length: 8 }, (_, index) =>
  Math.round((0.8 + index * 0.1) * 10) / 10
);

interface SpeakerConfig {
  voice_id: string;
  speech_rate: number;
}

const speakers = [
  { key: "昭昭", label: "昭昭（弟弟）" },
  { key: "灿灿", label: "灿灿（姐姐）" },
  { key: "妈妈", label: "妈妈" },
];

const defaultSpeakerConfigs: Record<string, SpeakerConfig> = {
  昭昭: { voice_id: TTS_VOICE_ZHAO, speech_rate: 1.15 },
  灿灿: { voice_id: DEFAULT_TTS_VOICE, speech_rate: 1.3 },
  妈妈: { voice_id: TTS_VOICE_MOM, speech_rate: 1.2 },
};

const props = defineProps<{
  job: JobDetail;
  logs: JobLog[];
  stageActive?: boolean;
}>();

const emit = defineEmits<{
  refresh: [];
}>();

const { handleError } = useErrorHandler();

const submitting = ref(false);
const loadError = ref("");
const playbackSpeed = ref(1);
const audioRef = ref<HTMLAudioElement | null>(null);

const phraseGapSec = ref(0.2);
const speakerConfigs = ref<Record<string, SpeakerConfig>>(
  loadSavedSpeakerConfigs()
);
syncPhraseGapFromJob();

function loadSavedSpeakerConfigs(): Record<string, SpeakerConfig> {
  const defaults = JSON.parse(JSON.stringify(defaultSpeakerConfigs)) as Record<
    string,
    SpeakerConfig
  >;
  const info = props.job.info as Record<string, unknown> | null | undefined;
  const tts = info?.tts as Record<string, unknown> | undefined;
  const saved = tts?.speaker_configs as Record<string, unknown> | undefined;
  if (!saved) return defaults;
  for (const [key, val] of Object.entries(saved)) {
    if (key === "phrase_gap_sec") continue;
    const cfg = val as Partial<SpeakerConfig> | undefined;
    if (cfg?.voice_id) {
      defaults[key] = {
        voice_id: cfg.voice_id,
        speech_rate: cfg.speech_rate ?? defaults[key]?.speech_rate ?? 1.0,
      };
    }
  }
  return defaults;
}

function syncPhraseGapFromJob() {
  const info = props.job.info as Record<string, unknown> | null | undefined;
  const tts = info?.tts as Record<string, unknown> | undefined;
  const saved = tts?.speaker_configs as Record<string, unknown> | undefined;
  const savedGap = saved?.phrase_gap_sec;
  if (typeof savedGap === "number") {
    phraseGapSec.value = savedGap;
  } else if (typeof tts?.phrase_gap_sec === "number") {
    phraseGapSec.value = tts.phrase_gap_sec;
  }
}

const actionDisabled = computed(() => props.job.status === "running");
const actionDisabledReason = computed(() =>
  props.job.status === "running" ? "任务运行中，请稍后再试" : ""
);

const audioUrl = computed(() => getMediaFileUrl(props.job.audio_path ?? "", props.job.audio_version));
const lazyAudioUrl = computed(() => lazyMediaSrc(audioUrl.value, props.stageActive));

interface SegmentClip {
  segment_index: number;
  text: string;
  clipUrl: string;
}

const scriptTextByIndex = computed<Record<number, string>>(() => {
  const script = (props.job.script_json as ScriptJson | null | undefined) || {};
  const map: Record<number, string> = {};
  for (const seg of script.segments || []) {
    if (seg.segment_index != null && seg.text) {
      map[seg.segment_index] = seg.text;
    }
  }
  return map;
});

const segmentClips = computed<SegmentClip[]>(() => {
  const clips = props.job.tts_clips;
  if (!clips?.length) return [];
  const textMap = scriptTextByIndex.value;
  return clips
    .map(clipPath => {
      const fileName = clipPath.trim().replace(/\\/g, "/").split("/").pop() || "";
      const index = parseInt(fileName.replace(/\.mp3$/i, ""), 10);
      const segIndex = Number.isFinite(index) ? index : 0;
      return {
        segment_index: segIndex,
        text: textMap[segIndex] || "",
        clipUrl: getMediaFileUrl(clipPath, props.job.audio_version),
      };
    })
    .filter(item => item.clipUrl)
    .sort((a, b) => a.segment_index - b.segment_index);
});

const ttsTotalCharactersText = computed(() => {
  const value = props.job.tts_usage_json;
  if (value === null || value === undefined) return "-";
  if (typeof value === "object" && value !== null && "total_characters" in value) {
    const total = (value as { total_characters?: unknown }).total_characters;
    if (typeof total === "number" && Number.isFinite(total)) {
      return `${total} 字`;
    }
  }
  return "-";
});

const audioDurationSec = ref<number | null>(null);

function resolveScriptCharCount(): number | null {
  const script = (props.job.script_json as ScriptJson | null | undefined) || null;
  if (!script || typeof script !== "object") return null;

  if (typeof script.word_count === "number" && Number.isFinite(script.word_count) && script.word_count > 0) {
    return script.word_count;
  }

  const totalChars = (script as { total_chars?: unknown }).total_chars;
  if (typeof totalChars === "number" && Number.isFinite(totalChars) && totalChars > 0) {
    return totalChars;
  }

  const segments = script.segments || [];
  if (segments.length) {
    let joined = "";
    for (const seg of segments) {
      const text = String(seg.text || "").trim();
      if (text) {
        joined += text;
        continue;
      }
      const dialogue = (seg as { dialogue?: Array<{ line?: string; text?: string }> }).dialogue;
      if (Array.isArray(dialogue)) {
        for (const line of dialogue) {
          joined += String(line.line || line.text || "");
        }
      }
    }
    const chars = joined.replace(/\s+/g, "").length;
    if (chars > 0) return chars;
  }

  const narration = String(script.narration || "").replace(/\s+/g, "");
  return narration.length > 0 ? narration.length : null;
}

const measuredSpeechRateText = computed(() => {
  const chars = resolveScriptCharCount();
  const duration = audioDurationSec.value;
  if (chars == null || duration == null || duration <= 0) return "-";
  return `${(chars / duration).toFixed(1)} 字/秒`;
});

const onAudioError = () => {
  loadError.value = "音频加载失败，请确认文件已生成且服务可访问";
};

const applyPlaybackSpeed = () => {
  if (audioRef.value) {
    audioRef.value.playbackRate = playbackSpeed.value;
  }
};

const handleRun = async (toEnd: boolean) => {
  const actionLabel = toEnd ? "从此成片" : "重新生成";
  try {
    await ElMessageBox.confirm(`确定对「配音」阶段执行「${actionLabel}」吗？`, "确认执行", {
      type: "warning",
      confirmButtonText: "执行",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }

  submitting.value = true;
  try {
    const payload: RunStageActionPayload = {
      id: props.job.id,
      to_end: toEnd,
      speaker_configs: { ...speakerConfigs.value, phrase_gap_sec: phraseGapSec.value },
    };
    await runJobStageAction("tts", payload);
    ElMessage.success(`已提交${actionLabel}，任务已开始执行`);
    emit("refresh");
  } catch (error) {
    handleError(error, `${actionLabel}失败`);
  } finally {
    submitting.value = false;
  }
};

watch(playbackSpeed, () => {
  applyPlaybackSpeed();
});

watch(
  () => props.job.audio_path,
  () => {
    loadError.value = "";
  }
);

watch(
  () => [props.job.audio_path, props.stageActive] as const,
  ([path, active]) => {
    if (active === false || !path) {
      audioDurationSec.value = null;
      return;
    }
    void (async () => {
      audioDurationSec.value = await getMediaDuration(path);
    })();
  },
  { immediate: true }
);

</script>
