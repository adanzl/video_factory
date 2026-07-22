<template>
  <div class="flex items-center gap-1.5 bg-gray-100 rounded border-gray-500 px-1" :class="widthClass">
    <el-button
      v-if="showPlayButton"
      type="default"
      plain
      size="small"
      circle
      @click.stop="togglePlay"
      :disabled="!hasAudioSource || isButtonDisabled"
      :loading="isLoading && !isPlaying"
      class="w-6! h-5.5! p-0! shrink-0 mr-1"
    >
      <span v-if="isPlaying">⏹</span>
      <el-icon v-else-if="!isLoading" class="w-3! h-3!">
        <Headset />
      </el-icon>
    </el-button>

    <el-slider
      v-if="showProgress"
      :model-value="progress"
      :min="0"
      :max="100"
      :step="0.1"
      size="small"
      class="flex-1 min-w-2.5 player-slider"
      :show-tooltip="false"
      :disabled="!hasAudioSource || !isPlaying || disabled"
      @change="handleSeek"
      @input="handleSeek"
      @click.stop
    />

    <span
      v-if="showTimeLabel"
      class="text-xs text-gray-600 shrink-0 tabular-nums text-center"
      :class="fullTimeLabel ? 'min-w-14' : 'min-w-14'"
    >
      {{ timeLabelText }}
    </span>

    <div v-if="showVol" class="flex items-center gap-1 shrink-0 w-20 pr-1.5" @click.stop>
      <i-mdi-volume-off v-if="volumePercent === 0" class="text-gray-500 w-5! h-5! shrink-0" />
      <i-mdi-volume-high v-else class="text-gray-500 w-4! h-4! shrink-0" />
      <el-slider
        :model-value="volumePercent"
        :min="0"
        :max="100"
        :step="1"
        size="small"
        class="flex-1 min-w-0 player-slider"
        :show-tooltip="false"
        :disabled="disabled"
        @change="handleVolume"
        @input="handleVolume"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from "vue";
import { Headset } from "@element-plus/icons-vue";
import { formatMediaDuration } from "@/utils/media";
import type { Ref } from "vue";

export type MediaPreload = "none" | "metadata" | "auto";

interface AudioPlayer {
  playingFilePath: Ref<string | null>;
  playProgress: Ref<number>;
  duration: Ref<number>;
  isPlaying: Ref<boolean>;
  volume?: Ref<number>;
  isFilePlaying: (filePath: string) => boolean;
  getFilePlayProgress: (filePath: string) => number;
  getFileCurrentTime: (filePath: string) => number;
  getFileDuration: (filePath: string, fallbackDuration?: number) => number;
  seekFile: (filePath: string, percentage: number) => void;
  setVolume?: (value: number) => void;
  load?: (
    audioUrl: string,
    fileInfo?: { playingFilePath?: string; playingFileIndex?: number }
  ) => void;
  play?: () => Promise<void>;
  clear?: () => void;
}

interface Props {
  /** 可播放 URL，由调用方用 getMediaFileUrl 生成 */
  src: string;
  player?: AudioPlayer;
  /** 同原生 audio.preload，默认 metadata */
  preload?: MediaPreload;
  /** 已知时长（秒）；未传则靠 preload / 播放时获取 */
  duration?: number | null;
  isPlaying?: boolean;
  progress?: number;
  currentTime?: number;
  disabled?: boolean;
  widthClass?: string;
  showPlayButton?: boolean;
  showProgress?: boolean;
  showTimeLabel?: boolean;
  fullTimeLabel?: boolean;
  showVol?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  preload: "metadata",
  isPlaying: false,
  progress: 0,
  currentTime: 0,
  disabled: false,
  widthClass: "w-32",
  showPlayButton: true,
  showProgress: true,
  showTimeLabel: true,
  fullTimeLabel: false,
  showVol: false,
});

const emit = defineEmits<{
  play: [src: string];
  seek: [src: string, value: number];
  volume: [src: string, value: number];
}>();

const playableSrc = computed(() => (props.src || "").trim());
/** 用 src 作为播放器身份键 */
const playKey = playableSrc;

const isLoading = ref(false);
const localVolumePercent = ref(100);
const preloadedDuration = ref(0);
let preloadAudio: HTMLAudioElement | null = null;

const hasAudioSource = computed(() => Boolean(playableSrc.value));

const canSelfPlay = computed(() => {
  return Boolean(
    props.player?.load && props.player?.play && props.player?.clear && playableSrc.value
  );
});

const isPlaying = computed(() => {
  if (props.player) {
    return props.player.isFilePlaying(playKey.value);
  }
  return props.isPlaying;
});

const progress = computed(() => {
  if (props.player) {
    return props.player.getFilePlayProgress(playKey.value);
  }
  return props.progress;
});

const fallbackDuration = computed(() => {
  return props.duration || preloadedDuration.value || 0;
});

const duration = computed(() => {
  if (props.player) {
    return props.player.getFileDuration(playKey.value, fallbackDuration.value);
  }
  return fallbackDuration.value;
});

const currentTime = computed(() => {
  if (props.player) {
    return props.player.getFileCurrentTime(playKey.value);
  }
  return props.currentTime;
});

const timeLabelText = computed(() => {
  const full = formatMediaDuration(duration.value);
  if (!props.fullTimeLabel) {
    return full;
  }
  return `${formatMediaDuration(currentTime.value)}/${full}`;
});

const volumePercent = computed(() => localVolumePercent.value);

const isButtonDisabled = computed(() => {
  return props.disabled || isLoading.value;
});

const isActiveFile = computed(() => {
  return Boolean(
    props.player?.playingFilePath && props.player.playingFilePath.value === playKey.value
  );
});

const applyVolumeToPlayer = () => {
  if (props.player?.setVolume) {
    props.player.setVolume(localVolumePercent.value / 100);
  }
};

const clearPreloadAudio = () => {
  if (!preloadAudio) return;
  try {
    preloadAudio.removeAttribute("src");
    preloadAudio.load();
  } catch {
    // ignore
  }
  preloadAudio = null;
};

const setupPreload = () => {
  clearPreloadAudio();
  preloadedDuration.value = 0;

  const url = playableSrc.value;
  if (!url || props.preload === "none") {
    return;
  }

  const audio = new Audio();
  audio.preload = props.preload;
  preloadAudio = audio;

  const onMeta = () => {
    if (audio !== preloadAudio) return;
    const dur = audio.duration;
    if (dur > 0 && isFinite(dur)) {
      preloadedDuration.value = dur;
    }
  };

  audio.addEventListener("loadedmetadata", onMeta);
  audio.src = url;
};

const togglePlay = () => {
  if (!hasAudioSource.value || isButtonDisabled.value) {
    return;
  }

  if (canSelfPlay.value && props.player) {
    if (isPlaying.value) {
      props.player.clear?.();
      return;
    }
    isLoading.value = true;
    applyVolumeToPlayer();
    props.player.load?.(playableSrc.value, { playingFilePath: playKey.value });
    // load 会重建 Audio，需再设一次音量
    applyVolumeToPlayer();
    props.player.play?.().catch(() => {
      isLoading.value = false;
      props.player?.clear?.();
    });
    return;
  }

  if (isPlaying.value) {
    emit("play", playableSrc.value);
    return;
  }

  isLoading.value = true;
  emit("play", playableSrc.value);
};

const handleSeek = (value: number) => {
  if (!props.disabled && isPlaying.value && hasAudioSource.value) {
    if (props.player) {
      props.player.seekFile(playKey.value, value);
    }
    emit("seek", playableSrc.value, value);
  }
};

const handleVolume = (value: number) => {
  if (props.disabled) return;
  const percent = Number(value);
  localVolumePercent.value = percent;
  // 仅当前播放项写入共享 player，避免一改全变
  if (isActiveFile.value) {
    applyVolumeToPlayer();
  }
  emit("volume", playableSrc.value, percent / 100);
};

watch(
  [isPlaying, duration],
  ([playing, dur]) => {
    if (playing && dur > 0) {
      isLoading.value = false;
    }
  },
  { immediate: true }
);

watch(
  () => [playableSrc.value, props.preload] as const,
  () => {
    isLoading.value = false;
    setupPreload();
  },
  { immediate: true }
);

onBeforeUnmount(() => {
  isLoading.value = false;
  clearPreloadAudio();
});
</script>

<style scoped>
.player-slider {
  --el-slider-button-size: 10px;
  --el-slider-button-wrapper-size: 20px;
  --el-slider-height: 6px;
  /* 与播放按钮 h-5.5 对齐，避免整行视觉偏斜 */
  height: 22px;
}

.player-slider :deep(.el-slider__button-wrapper) {
  top: 50%;
  margin-top: calc(var(--el-slider-button-wrapper-size) / -2);
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 0;
}

/* Element Plus 用 ::after + vertical-align 居中，缩小时易偏，关掉 */
.player-slider :deep(.el-slider__button-wrapper::after) {
  display: none;
}
</style>
