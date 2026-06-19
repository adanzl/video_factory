<template>
  <div class="video-preview">
    <div v-if="videoUrl" class="video-preview__player">
      <video
        :key="videoUrl"
        class="video-preview__video"
        :src="videoUrl"
        :poster="posterUrl || undefined"
        controls
        playsinline
        preload="metadata"
        @error="onVideoError"
      />
    </div>
    <EmptyHint v-else-if="!path" :text="emptyText" />
    <el-alert
      v-else-if="loadError"
      type="warning"
      :title="loadError"
      :closable="false"
      class="mt-2"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { getMediaFileUrl } from "@/api/api-media";
import EmptyHint from "./JobDetailEmptyHint.vue";

const props = withDefaults(
  defineProps<{
    path?: string | null;
    posterPath?: string | null;
    emptyText?: string;
  }>(),
  {
    emptyText: "暂无视频，请先生成",
  }
);

const loadError = ref("");

const videoUrl = computed(() => getMediaFileUrl(props.path ?? ""));

const posterUrl = computed(() => {
  const explicit = props.posterPath?.trim();
  if (explicit) {
    return getMediaFileUrl(explicit);
  }
  const videoPath = props.path?.trim();
  if (!videoPath) {
    return "";
  }
  return getMediaFileUrl(videoPath.replace(/\.mp4$/i, ".png"));
});

watch(
  () => props.path,
  () => {
    loadError.value = "";
  }
);

const onVideoError = () => {
  loadError.value = "视频加载失败，请确认文件已生成且服务可访问";
};
</script>

<style scoped>
.video-preview__player {
  width: 100%;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  overflow: hidden;
  background: #000;
}

.video-preview__video {
  display: block;
  width: 100%;
  max-height: 405px;
  background: #000;
}
</style>
