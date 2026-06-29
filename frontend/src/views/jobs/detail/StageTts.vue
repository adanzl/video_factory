<template>
  <div>
    <div class="flex flex-wrap items-start gap-4">
      <div class="min-w-[280px] max-w-full shrink-0 basis-80">
        <div class="rounded border border-gray-200 p-4">
          <div class="mb-3 text-sm font-medium text-gray-700">参数配置</div>
          <div>
            <div class="mb-3 flex flex-wrap items-center gap-2">
              <el-button type="primary" :loading="submitting" :disabled="actionDisabled" @click="handleRun(false)">
                重新生成
              </el-button>
              <el-button type="success" :loading="submitting" :disabled="actionDisabled" @click="handleRun(true)">
                从此成片
              </el-button>
              <span v-if="actionDisabledReason" class="text-sm text-gray-400">{{ actionDisabledReason }}</span>
            </div>
            <el-form label-width="96px">
              <el-form-item label="语速">
                <el-input-number
                  v-model="speechRate"
                  :min="0.5"
                  :max="2"
                  :step="0.05"
                  controls-position="right"
                  class="w-40!"
                />
              </el-form-item>
              <el-form-item label="声音 ID">
                <div class="flex w-full flex-wrap items-center gap-2">
                  <el-select v-model="voiceId" filterable class="min-w-0 flex-1!">
                    <el-option
                      v-for="voice in TTS_VOICE_OPTIONS"
                      :key="voice.value"
                      :label="voice.label"
                      :value="voice.value"
                    />
                  </el-select>
                  <el-button
                    :disabled="!selectedVoicePreviewUrl"
                    :loading="voicePreviewLoading"
                    @click="handleVoicePreview"
                  >
                    {{ voicePreviewPlaying ? "停止" : "预览" }}
                  </el-button>
                </div>
              </el-form-item>
            </el-form>
          </div>
          <el-form label-width="96px" class="[&_.el-form-item]:mb-2">
            <el-form-item label="音频路径">
              <span class="break-all text-gray-600">{{ job.audio_path || "-" }}</span>
            </el-form-item>
            <el-form-item label="字幕路径">
              <span class="break-all text-gray-600">{{ job.subtitle_path || "-" }}</span>
            </el-form-item>
            <el-form-item label="TTS 用量">
              <span class="text-gray-700">{{ ttsTotalCharactersText }}</span>
            </el-form-item>
          </el-form>
        </div>
      </div>

      <div class="min-w-[280px] flex-1 basis-[360px]">
        <div class="rounded border border-gray-200 p-4">
          <div class="mb-3 text-sm font-medium text-gray-700">音频预览</div>
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
              :src="audioUrl"
              :crossorigin="MEDIA_CROSS_ORIGIN"
              controls
              preload="metadata"
              @error="onAudioError"
              @loadedmetadata="applyPlaybackSpeed"
            />
          </div>
          <div v-else-if="!job.audio_path" class="py-8 text-center text-sm text-gray-400">
            暂无配音音频，请先生成
          </div>
          <el-alert
            v-else-if="loadError"
            type="warning"
            :title="loadError"
            :closable="false"
            class="mt-2"
          />

          <div class="mt-4">
            <div class="mb-3 text-sm font-medium text-gray-700">字幕预览</div>
            <el-table
              v-if="srtCues.length"
              :data="srtCues"
              stripe
              size="small"
              class="w-full"
              max-height="320"
            >
              <el-table-column prop="index" label="#" width="56" />
              <el-table-column prop="time" label="时间" width="210" show-overflow-tooltip />
              <el-table-column prop="text" label="文案" min-width="160">
                <template #default="{ row }">
                  <div class="leading-relaxed wrap-break-word whitespace-pre-wrap">{{ row.text }}</div>
                </template>
              </el-table-column>
            </el-table>
            <div v-else-if="srtLoading" class="py-8 text-center text-sm text-gray-400">加载中…</div>
            <div v-else-if="!job.subtitle_path" class="py-8 text-center text-sm text-gray-400">暂无字幕，请先生成</div>
            <el-alert
              v-else-if="srtLoadError"
              type="warning"
              :title="srtLoadError"
              :closable="false"
            />
          </div>
        </div>
      </div>
    </div>

    <div class="mt-6">
      <div class="mb-2 text-sm font-medium text-gray-600">阶段日志</div>
      <el-table v-if="logs.length" :data="logs" stripe size="small" class="w-full">
        <el-table-column label="时间" width="180">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="level" label="级别" width="80" />
        <el-table-column prop="message" label="消息" min-width="240" show-overflow-tooltip />
      </el-table>
      <div v-else class="py-8 text-center text-sm text-gray-400">暂无日志</div>
    </div>

    <audio
      ref="voicePreviewRef"
      class="hidden"
      preload="metadata"
      @ended="voicePreviewPlaying = false"
      @pause="voicePreviewPlaying = false"
      @error="onVoicePreviewError"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { runJobStageAction } from "@/api/api-jobs";
import { getMediaFileUrl, getMediaText } from "@/api/api-media";
import { DEFAULT_TTS_VOICE, TTS_VOICE_OPTIONS } from "@/constants/tts-voices";
import type { JobDetail, JobLog } from "@/types/jobs";
import { formatDateTime } from "@/utils/date";
import { MEDIA_CROSS_ORIGIN } from "@/utils/media";
import { useErrorHandler } from "@/composables/useErrorHandler";

const AUDIO_PLAYBACK_SPEED_OPTIONS = Array.from({ length: 8 }, (_, index) =>
  Math.round((0.8 + index * 0.1) * 10) / 10
);

interface SrtCueRow {
  index: string;
  time: string;
  text: string;
}

const parseSrt = (raw: string): SrtCueRow[] => {
  return raw
    .trim()
    .split(/\n\s*\n/)
    .map(block => {
      const lines = block.trim().split("\n");
      if (lines.length < 3) {
        return null;
      }
      return {
        index: lines[0],
        time: lines[1],
        text: lines.slice(2).join("\n"),
      };
    })
    .filter((item): item is SrtCueRow => item !== null);
};

const props = defineProps<{
  job: JobDetail;
  logs: JobLog[];
}>();

const emit = defineEmits<{
  refresh: [];
}>();

const { handleError } = useErrorHandler();

const submitting = ref(false);
const loadError = ref("");
const srtLoading = ref(false);
const srtLoadError = ref("");
const srtCues = ref<SrtCueRow[]>([]);
const speechRate = ref(1.15);
const voiceId = ref(DEFAULT_TTS_VOICE);
const playbackSpeed = ref(1);
const audioRef = ref<HTMLAudioElement | null>(null);
const voicePreviewRef = ref<HTMLAudioElement | null>(null);
const voicePreviewLoading = ref(false);
const voicePreviewPlaying = ref(false);

const actionDisabled = computed(() => props.job.status === "running");
const actionDisabledReason = computed(() =>
  props.job.status === "running" ? "任务运行中，请稍后再试" : ""
);

const audioUrl = computed(() => getMediaFileUrl(props.job.audio_path ?? ""));

const selectedVoicePreviewUrl = computed(
  () => TTS_VOICE_OPTIONS.find(voice => voice.value === voiceId.value)?.previewUrl ?? ""
);

const ttsTotalCharactersText = computed(() => {
  const value = props.job.tts_usage_json;
  if (value === null || value === undefined) {
    return "-";
  }
  if (typeof value === "object" && value !== null && "total_characters" in value) {
    const total = (value as { total_characters?: unknown }).total_characters;
    if (typeof total === "number" && Number.isFinite(total)) {
      return `${total} 字`;
    }
  }
  return "-";
});

const onAudioError = () => {
  loadError.value = "音频加载失败，请确认文件已生成且服务可访问";
};

const applyPlaybackSpeed = () => {
  if (audioRef.value) {
    audioRef.value.playbackRate = playbackSpeed.value;
  }
};

const stopVoicePreview = () => {
  if (!voicePreviewRef.value) {
    voicePreviewPlaying.value = false;
    return;
  }
  voicePreviewRef.value.pause();
  voicePreviewRef.value.currentTime = 0;
  voicePreviewPlaying.value = false;
};

const onVoicePreviewError = () => {
  voicePreviewLoading.value = false;
  voicePreviewPlaying.value = false;
  ElMessage.warning("音色预览加载失败");
};

const handleVoicePreview = async () => {
  if (voicePreviewPlaying.value) {
    stopVoicePreview();
    return;
  }

  const url = selectedVoicePreviewUrl.value;
  if (!url || !voicePreviewRef.value) {
    ElMessage.warning("当前音色暂无预览音频");
    return;
  }

  voicePreviewLoading.value = true;
  try {
    voicePreviewRef.value.src = url;
    voicePreviewRef.value.playbackRate = 1;
    await voicePreviewRef.value.play();
    voicePreviewPlaying.value = true;
  } catch {
    stopVoicePreview();
    ElMessage.warning("音色预览播放失败");
  } finally {
    voicePreviewLoading.value = false;
  }
};

const loadSrtPreview = async () => {
  if (!props.job.subtitle_path) {
    srtCues.value = [];
    srtLoadError.value = "";
    srtLoading.value = false;
    return;
  }

  srtLoading.value = true;
  srtLoadError.value = "";
  try {
    const content = await getMediaText(props.job.subtitle_path);
    if (!content?.trim()) {
      srtCues.value = [];
      srtLoadError.value = "字幕文件为空或无法读取";
      return;
    }
    srtCues.value = parseSrt(content);
    if (!srtCues.value.length) {
      srtLoadError.value = "字幕格式无法解析";
    }
  } catch {
    srtCues.value = [];
    srtLoadError.value = "字幕加载失败，请确认文件已生成且服务可访问";
  } finally {
    srtLoading.value = false;
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
    const payload: {
      id: number;
      to_end: boolean;
      speech_rate?: number;
      voice_id?: string;
    } = {
      id: props.job.id,
      to_end: toEnd,
    };
    if (Number.isFinite(speechRate.value)) {
      payload.speech_rate = speechRate.value;
    }
    if (voiceId.value.trim()) {
      payload.voice_id = voiceId.value.trim();
    }
    await runJobStageAction("tts", payload);
    ElMessage.success(`已提交${actionLabel}，任务已开始执行`);
    emit("refresh");
  } catch (error) {
    handleError(error, `${actionLabel}失败`);
  } finally {
    submitting.value = false;
  }
};

watch(
  () => props.job.audio_path,
  () => {
    loadError.value = "";
  }
);

watch(playbackSpeed, () => {
  applyPlaybackSpeed();
});

watch(voiceId, () => {
  stopVoicePreview();
});

watch(
  () => props.job.subtitle_path,
  () => {
    void loadSrtPreview();
  },
  { immediate: true }
);
</script>
