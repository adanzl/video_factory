/**
 * 音频播放器 Composable
 * 提供统一的音频播放器管理功能
 */
import { onScopeDispose, ref, toValue, watch, type MaybeRefOrGetter, type Ref } from "vue";

const NOOP = () => {};
const INITIAL_TIME = 0;
const INITIAL_PROGRESS = 0;

interface AudioPlayerCallbacks {
  onPlay?: (audio: HTMLAudioElement) => void;
  onPause?: (audio: HTMLAudioElement) => void;
  onTimeUpdate?: (currentTime: number, duration: number, progress: number) => void;
  onDurationUpdate?: (duration: number) => void;
  onError?: (error: Event, audioUrl: string) => void;
  onEnded?: (audio: HTMLAudioElement) => void;
}

interface AudioPlayerOptions {
  playingFilePath?: string | null;
  playingFileIndex?: number | null;
  callbacks?: AudioPlayerCallbacks;
  /** false 时自动 clear；组件卸载时也会 clear */
  active?: MaybeRefOrGetter<boolean | undefined>;
}

export function useAudioPlayer(options: AudioPlayerOptions = {}) {
  const {
    playingFilePath: initialFilePath = null,
    playingFileIndex: initialFileIndex = null,
    callbacks = {},
    active,
  } = options;

  const callbacksRef: Required<AudioPlayerCallbacks> = {
    onPlay: callbacks.onPlay || NOOP,
    onPause: callbacks.onPause || NOOP,
    onTimeUpdate: callbacks.onTimeUpdate || NOOP,
    onDurationUpdate: callbacks.onDurationUpdate || NOOP,
    onError: callbacks.onError || NOOP,
    onEnded: callbacks.onEnded || NOOP,
  };

  const playingFilePath: Ref<string | null> = ref(initialFilePath);
  const playProgress: Ref<number> = ref(INITIAL_PROGRESS);
  const currentTime: Ref<number> = ref(INITIAL_TIME);
  const duration: Ref<number> = ref(INITIAL_TIME);
  const isPlaying: Ref<boolean> = ref(false);
  const playingFileIndex: Ref<number | null> = ref(initialFileIndex);
  /** 音量 0–1 */
  const volume: Ref<number> = ref(1);

  let audio: HTMLAudioElement | null = null;
  let currentAudioUrl: string | null = null;

  const resetPlaybackPosition = () => {
    if (audio) {
      audio.currentTime = INITIAL_TIME;
    }
  };

  const updateDuration = (newDuration: number) => {
    if (newDuration > 0 && isFinite(newDuration)) {
      duration.value = newDuration;
      callbacksRef.onDurationUpdate(newDuration);
    }
  };

  const resetPlaybackState = () => {
    playProgress.value = INITIAL_PROGRESS;
    currentTime.value = INITIAL_TIME;
    duration.value = INITIAL_TIME;
    isPlaying.value = false;
  };

  const removeEventListeners = () => {
    if (!audio) return;

    try {
      if (!audio.paused) {
        audio.pause();
      }
      audio.currentTime = 0;
      audio.removeAttribute("src");
    } catch {
      // ignore
    }

    audio = null;
  };

  const setupEventListeners = () => {
    if (!audio) return;

    audio.addEventListener("play", e => {
      const audioElement = e.target as HTMLAudioElement;
      if (!audioElement || audio !== audioElement) return;
      resetPlaybackPosition();
      isPlaying.value = true;
      callbacksRef.onPlay(audioElement);
    });

    const handleMediaLoaded = (e: Event) => {
      const audioElement = e.target as HTMLAudioElement;
      if (!audioElement || audio !== audioElement) return;
      resetPlaybackPosition();
      updateDuration(audioElement.duration);
    };
    audio.addEventListener("loadedmetadata", handleMediaLoaded);
    audio.addEventListener("loadeddata", handleMediaLoaded);

    audio.addEventListener("timeupdate", e => {
      const audioElement = e.target as HTMLAudioElement;
      if (!audioElement || audio !== audioElement) return;
      const dur = audioElement.duration;
      if (dur > 0 && isFinite(dur)) {
        const current = audioElement.currentTime;
        const progress = (current / dur) * 100;
        currentTime.value = current;
        playProgress.value = progress;
        if (duration.value !== dur) {
          duration.value = dur;
        }
        callbacksRef.onTimeUpdate(current, dur, progress);
      }
    });

    audio.addEventListener("pause", e => {
      const audioElement = e.target as HTMLAudioElement;
      if (!audioElement || audio !== audioElement) return;
      isPlaying.value = false;
      if (audioElement.ended) {
        callbacksRef.onEnded(audioElement);
      } else {
        callbacksRef.onPause(audioElement);
      }
    });

    audio.addEventListener("error", e => {
      const audioElement = e.target as HTMLAudioElement;
      if (!audioElement || audio !== audioElement) return;
      console.error("音频播放失败:", e, "URL:", currentAudioUrl);
      isPlaying.value = false;
      callbacksRef.onError(e, currentAudioUrl || "");
    });

    audio.addEventListener("ended", e => {
      const audioElement = e.target as HTMLAudioElement;
      if (!audioElement || audio !== audioElement) return;
      isPlaying.value = false;
      callbacksRef.onEnded(audioElement);
    });
  };

  const load = (
    audioUrl: string,
    fileInfo: { playingFilePath?: string; playingFileIndex?: number } = {}
  ) => {
    if (!audioUrl || typeof audioUrl !== "string" || audioUrl.trim() === "") {
      console.error("音频URL不能为空或无效:", audioUrl);
      return;
    }

    try {
      const url = new URL(audioUrl, window.location.origin);
      if (!url.pathname || url.pathname === "/" || url.pathname.endsWith(".html")) {
        console.error("音频URL格式无效，可能是HTML页面:", audioUrl);
        return;
      }
    } catch {
      if (audioUrl.includes("index.html") || audioUrl.endsWith(".html")) {
        console.error("音频URL格式无效，可能是HTML页面:", audioUrl);
        return;
      }
    }

    if (audio) {
      removeEventListeners();
    }

    resetPlaybackState();

    audio = new Audio(audioUrl);
    audio.volume = volume.value;
    currentAudioUrl = audioUrl;
    resetPlaybackPosition();

    if (fileInfo.playingFilePath !== undefined) {
      playingFilePath.value = fileInfo.playingFilePath;
    }
    if (fileInfo.playingFileIndex !== undefined) {
      playingFileIndex.value = fileInfo.playingFileIndex;
    }

    setupEventListeners();
  };

  const play = (): Promise<void> => {
    if (!audio) {
      console.warn("音频未加载，无法播放");
      return Promise.reject(new Error("音频未加载"));
    }
    return audio.play().catch(error => {
      console.error("播放失败:", error);
      throw error;
    });
  };

  const pause = () => {
    if (audio) {
      audio.pause();
    }
  };

  const seek = (percentage: number) => {
    if (!audio) {
      console.warn("音频未加载，无法跳转");
      return;
    }
    const audioDuration = audio.duration;
    if (audioDuration > 0 && isFinite(audioDuration) && isFinite(percentage)) {
      const targetTime = Math.max(0, Math.min((percentage / 100) * audioDuration, audioDuration));
      audio.currentTime = targetTime;
      currentTime.value = targetTime;
      playProgress.value = percentage;
    }
  };

  const clear = () => {
    if (audio) {
      try {
        if (!audio.paused) {
          audio.pause();
        }
        audio.currentTime = INITIAL_TIME;
      } catch {
        // ignore
      }
      removeEventListeners();
    }
    currentAudioUrl = null;
    playingFilePath.value = null;
    playingFileIndex.value = null;
    resetPlaybackState();
  };

  const updateCallbacks = (newCallbacks: Partial<AudioPlayerCallbacks>) => {
    Object.assign(callbacksRef, newCallbacks);
  };

  const isFilePlaying = (filePath: string): boolean => {
    if (!filePath) return false;
    return playingFilePath.value === filePath && audio !== null && !audio.paused;
  };

  const getFilePlayProgress = (filePath: string): number => {
    if (!filePath || playingFilePath.value !== filePath || !audio) {
      return INITIAL_PROGRESS;
    }
    return playProgress.value;
  };

  const getFileCurrentTime = (filePath: string): number => {
    if (!filePath || playingFilePath.value !== filePath) {
      return INITIAL_TIME;
    }
    return currentTime.value;
  };

  const getFileDuration = (filePath: string, fallbackDuration: number = INITIAL_TIME): number => {
    if (!filePath) return fallbackDuration;
    if (playingFilePath.value === filePath) {
      return duration.value || fallbackDuration;
    }
    return fallbackDuration;
  };

  const seekFile = (filePath: string, percentage: number) => {
    if (!audio || !filePath) return;
    if (playingFilePath.value === filePath) {
      seek(percentage);
    }
  };

  const setVolume = (value: number) => {
    const next = Math.max(0, Math.min(1, value));
    volume.value = next;
    if (audio) {
      audio.volume = next;
    }
  };

  if (active !== undefined) {
    watch(
      () => toValue(active),
      value => {
        if (value === false) {
          clear();
        }
      }
    );
  }

  onScopeDispose(() => {
    clear();
  });

  return {
    get audio() {
      return audio;
    },
    playingFilePath,
    playProgress,
    currentTime,
    duration,
    isPlaying,
    playingFileIndex,
    volume,
    load,
    play,
    pause,
    seek,
    clear,
    updateCallbacks,
    isFilePlaying,
    getFilePlayProgress,
    getFileCurrentTime,
    getFileDuration,
    seekFile,
    setVolume,
  };
}
