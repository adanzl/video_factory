<template>
  <div>
    <div class="mb-4 rounded-lg border border-gray-200 bg-gray-50 p-4">
      <el-form inline @submit.prevent="handleSearch('original')">
        <el-form-item label="关键词">
          <el-input
            v-model="keyword"
            :placeholder="clipSearchKeywordPlaceholder(language)"
            clearable
            :class="keywordInputClass"
            @keyup.enter="handleSearch('original')"
          />
        </el-form-item>
        <el-form-item label="语言">
          <el-select v-model="language" class="w-28!">
            <el-option label="不限" value="" />
            <el-option label="中文" value="zh" />
            <el-option label="英文" value="en" />
          </el-select>
        </el-form-item>
        <el-form-item label="画幅">
          <el-select v-model="orientation" clearable placeholder="不限" class="w-28!">
            <el-option label="竖屏" value="portrait" />
            <el-option label="横屏" value="landscape" />
            <el-option label="方形" value="square" />
          </el-select>
        </el-form-item>
        <el-form-item label="来源">
          <el-checkbox-group v-model="selectedProviders">
            <el-checkbox
              v-for="source in sources"
              :key="source.provider"
              :value="source.provider"
              :disabled="!source.available"
            >
              {{ providerLabel(source.provider) }}
            </el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item>
          <el-button :loading="searching" @click="handleSearch('original')">原文搜索</el-button>
          <el-button type="primary" :loading="searching" @click="handleSearch('ai')">AI 搜索</el-button>
        </el-form-item>
      </el-form>
      <div v-if="sources.length" class="text-xs text-gray-500">
        <span v-for="source in sources" :key="source.provider" class="mr-4">
          {{ providerLabel(source.provider) }}：
          <span v-if="source.available" class="text-green-600">可用</span>
          <span v-else class="text-amber-600">{{ source.reason || "未配置" }}</span>
        </span>
      </div>
    </div>

    <div v-if="lastQuery" class="mb-3 flex flex-wrap items-center gap-2 text-sm text-gray-600">
      <span>「{{ lastQuery }}」共 {{ clips.length }} 条</span>
      <span v-if="resolvedQuery && resolvedQuery !== lastQuery" class="text-xs text-gray-500">
        AI 搜索词：{{ resolvedQuery }}
      </span>
      <el-tag
        v-for="meta in providerMeta"
        :key="meta.provider"
        size="small"
        :type="providerMetaTagType(meta.status)"
      >
        {{ providerLabel(meta.provider) }} {{ meta.status === "ok" ? meta.count : meta.status }}
      </el-tag>
    </div>

    <div v-loading="searching" :class="resultsWrapperClass">
      <div :class="gridClass">
        <div
          v-for="clip in clips"
          :key="clip.id"
          class="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm"
        >
          <div class="relative aspect-video bg-black">
            <video
              :src="clipPreviewUrl(clip.video_url)"
              :poster="clipPosterUrl(clip.preview_url)"
              class="h-full w-full object-contain"
              controls
              preload="metadata"
              playsinline
              crossorigin="anonymous"
            />
          </div>
          <div class="space-y-2 p-3">
            <div class="flex items-start justify-between gap-2">
              <div class="min-w-0 flex-1">
                <div class="truncate text-sm font-medium" :title="clip.title">{{ clip.title }}</div>
                <div class="mt-1 flex flex-wrap gap-1">
                  <el-tag size="small" type="info">{{ providerLabel(clip.provider) }}</el-tag>
                  <el-tag v-if="clip.duration_sec != null" size="small">
                    {{ formatClipDuration(clip.duration_sec) }}
                  </el-tag>
                  <el-tag v-if="clip.width && clip.height" size="small" type="info">
                    {{ clip.width }}×{{ clip.height }}
                  </el-tag>
                </div>
              </div>
            </div>
            <div v-if="showMeta" class="text-xs text-gray-500">
              {{ clip.license }}
              <span v-if="clip.author"> · {{ clip.author }}</span>
            </div>
            <slot name="actions" :clip="clip" />
          </div>
        </div>
      </div>

      <div
        v-if="!searching && searched && !clips.length"
        :class="emptyClass"
      >
        未找到片段，可换英文关键词或检查 API Key 配置
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import { clipPosterUrl, clipPreviewUrl } from "@/api/api-clips";
import { useClipSearch } from "@/composables/useClipSearch";
import type { ClipOrientation } from "@/utils/clipSearch";
import type { ClipSearchLanguage } from "@/types/clipSearch";
import { clipSearchKeywordPlaceholder, formatClipDuration, providerLabel, providerMetaTagType } from "@/utils/clipSearch";

const props = withDefaults(
  defineProps<{
    initialKeyword?: string;
    initialOrientation?: ClipOrientation;
    initialLanguage?: ClipSearchLanguage;
    keywordInputClass?: string;
    gridClass?: string;
    resultsWrapperClass?: string;
    emptyClass?: string;
    showMeta?: boolean;
    autoSearch?: boolean;
    ready?: boolean;
  }>(),
  {
    initialKeyword: "",
    initialOrientation: "",
    initialLanguage: "zh",
    keywordInputClass: "w-72!",
    gridClass: "grid grid-cols-3 gap-4",
    resultsWrapperClass: "",
    emptyClass: "py-16 text-center text-sm text-gray-400",
    showMeta: true,
    autoSearch: false,
    ready: true,
  }
);

const {
  keyword,
  orientation,
  language,
  sources,
  selectedProviders,
  clips,
  providerMeta,
  lastQuery,
  resolvedQuery,
  searching,
  searched,
  handleSearch,
  initialize,
} = useClipSearch({
  initialKeyword: () => props.initialKeyword,
  initialOrientation: () => props.initialOrientation,
  initialLanguage: () => props.initialLanguage,
  autoSearch: props.autoSearch,
});

onMounted(() => {
  if (props.ready) {
    void initialize();
  }
});

defineExpose({ initialize });
</script>
