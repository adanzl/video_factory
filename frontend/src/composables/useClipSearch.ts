import { ref, toValue, type MaybeRefOrGetter } from "vue";
import { ElMessage } from "element-plus";
import { listClipSources, searchClips } from "@/api/api-clips";
import type {
  ClipProviderName,
  ClipProviderSearchMeta,
  ClipProviderStatus,
  ClipSearchLanguage,
  ClipSearchMode,
  StockClip,
} from "@/types/clipSearch";
import type { ClipOrientation } from "@/utils/clipSearch";
import { useErrorHandler } from "@/composables/useErrorHandler";

export interface UseClipSearchOptions {
  initialKeyword?: MaybeRefOrGetter<string>;
  initialOrientation?: MaybeRefOrGetter<ClipOrientation>;
  initialLanguage?: MaybeRefOrGetter<ClipSearchLanguage>;
  autoSearch?: boolean;
  autoSearchMode?: ClipSearchMode;
}

export function useClipSearch(options: UseClipSearchOptions = {}) {
  const { handleError } = useErrorHandler();

  const keyword = ref("");
  const orientation = ref<ClipOrientation>("");
  const language = ref<ClipSearchLanguage>("zh");
  const CLIP_SEARCH_PER_PAGE = 60;
  const sources = ref<ClipProviderStatus[]>([]);
  const selectedProviders = ref<ClipProviderName[]>(["pexels", "pixabay", "nasa"]);
  const clips = ref<StockClip[]>([]);
  const providerMeta = ref<ClipProviderSearchMeta[]>([]);
  const lastQuery = ref("");
  const lastSearchMode = ref<ClipSearchMode>("original");
  const resolvedQuery = ref("");
  const searching = ref(false);
  const searched = ref(false);

  const applyInitialValues = () => {
    keyword.value = toValue(options.initialKeyword)?.trim() ?? "";
    orientation.value = toValue(options.initialOrientation) ?? "";
    language.value = toValue(options.initialLanguage) ?? "zh";
  };

  const resetResults = () => {
    clips.value = [];
    providerMeta.value = [];
    lastQuery.value = "";
    lastSearchMode.value = "original";
    resolvedQuery.value = "";
    searched.value = false;
  };

  const reset = () => {
    applyInitialValues();
    resetResults();
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

  const handleSearch = async (searchMode: ClipSearchMode = "original") => {
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
        per_page: CLIP_SEARCH_PER_PAGE,
        providers: selectedProviders.value,
        orientation: orientation.value || undefined,
        language: searchMode === "original" ? language.value || undefined : undefined,
        search_mode: searchMode,
      });
      lastQuery.value = result.query;
      lastSearchMode.value = result.search_mode ?? searchMode;
      resolvedQuery.value = result.resolved_query?.trim() ?? "";
      clips.value = result.clips ?? [];
      providerMeta.value = result.providers ?? [];
    } catch (error) {
      handleError(error, "搜索片段失败");
    } finally {
      searching.value = false;
    }
  };

  const initialize = async () => {
    reset();
    await loadSources();
    if (options.autoSearch && keyword.value.trim()) {
      await handleSearch(options.autoSearchMode ?? "original");
    }
  };

  return {
    keyword,
    orientation,
    language,
    sources,
    selectedProviders,
    clips,
    providerMeta,
    lastQuery,
    lastSearchMode,
    resolvedQuery,
    searching,
    searched,
    reset,
    resetResults,
    loadSources,
    handleSearch,
    initialize,
  };
}
