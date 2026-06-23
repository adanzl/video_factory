<template>
  <div>
    <div class="mb-4 rounded-lg border border-gray-200 bg-gray-50 p-4">
      <el-form inline @submit.prevent="handleSearch">
        <el-form-item label="关键词">
          <el-input
            v-model="keyword"
            placeholder="英文关键词效果更好，如 magnet experiment"
            clearable
            class="w-72!"
            @keyup.enter="handleSearch"
          />
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
              :label="source.provider"
              :disabled="!source.available"
            >
              {{ providerLabel(source.provider) }}
            </el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="searching" @click="handleSearch">搜索</el-button>
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
      <el-tag
        v-for="meta in providerMeta"
        :key="meta.provider"
        size="small"
        :type="providerMetaTagType(meta.status)"
      >
        {{ providerLabel(meta.provider) }} {{ meta.status === "ok" ? meta.count : meta.status }}
      </el-tag>
    </div>

    <div v-loading="searching" class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
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
          <div class="text-xs text-gray-500">
            {{ clip.license }}
            <span v-if="clip.author"> · {{ clip.author }}</span>
          </div>
          <div class="flex flex-wrap gap-2">
            <el-button size="small" @click="copyText(clip.video_url, '视频地址')">复制视频 URL</el-button>
            <el-button size="small" link type="primary" @click="openPage(clip.page_url)">来源页</el-button>
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="!searching && searched && !clips.length"
      class="py-16 text-center text-sm text-gray-400"
    >
      未找到片段，可换英文关键词或检查 API Key 配置
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { CLIP_PROVIDER_LABELS, clipPosterUrl, clipPreviewUrl, listClipSources, searchClips } from "@/api/api-clips";
import type {
  ClipProviderName,
  ClipProviderSearchMeta,
  ClipProviderStatus,
  StockClip,
} from "@/types/clipSearch";
import { useErrorHandler } from "@/composables/useErrorHandler";
import { copyText as copyToClipboard } from "@/utils/utils";

const { handleError } = useErrorHandler();

const keyword = ref("");
const orientation = ref<"" | "portrait" | "landscape" | "square">("");
const sources = ref<ClipProviderStatus[]>([]);
const selectedProviders = ref<ClipProviderName[]>(["pexels", "pixabay", "nasa"]);
const clips = ref<StockClip[]>([]);
const providerMeta = ref<ClipProviderSearchMeta[]>([]);
const lastQuery = ref("");
const searching = ref(false);
const searched = ref(false);

const providerLabel = (name: ClipProviderName) => CLIP_PROVIDER_LABELS[name] ?? name;

const providerMetaTagType = (status: ClipProviderSearchMeta["status"]) => {
  if (status === "ok") return "success";
  if (status === "skipped") return "info";
  return "warning";
};

const formatClipDuration = (seconds: number) => {
  const total = Math.max(0, Math.round(seconds));
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return mins > 0 ? `${mins}:${secs.toString().padStart(2, "0")}` : `${secs}s`;
};

const loadSources = async () => {
  try {
    sources.value = await listClipSources();
    const available = sources.value.filter(row => row.available).map(row => row.provider);
    if (available.length) {
      selectedProviders.value = available;
    }
  } catch (error) {
    handleError(error, "加载素材源失败");
  }
};

const handleSearch = async () => {
  const q = keyword.value.trim();
  if (!q) {
    ElMessage.warning("请输入搜索关键词");
    return;
  }
  if (!selectedProviders.value.length) {
    ElMessage.warning("请至少选择一个素材源");
    return;
  }

  searching.value = true;
  searched.value = true;
  try {
    const result = await searchClips({
      q,
      per_page: 24,
      providers: selectedProviders.value,
      orientation: orientation.value || undefined,
    });
    lastQuery.value = result.query;
    clips.value = result.clips ?? [];
    providerMeta.value = result.providers ?? [];
  } catch (error) {
    handleError(error, "搜索片段失败");
  } finally {
    searching.value = false;
  }
};

const copyText = async (text: string, label: string) => {
  try {
    await copyToClipboard(text);
    ElMessage.success(`${label}已复制`);
  } catch (error) {
    handleError(error, "复制失败");
  }
};

const openPage = (url: string) => {
  window.open(url, "_blank", "noopener,noreferrer");
};

onMounted(() => {
  void loadSources();
});
</script>
