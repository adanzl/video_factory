import { defineStore } from "pinia";
import { onActivated, onDeactivated, ref, watch } from "vue";

export const useAppStore = defineStore("app", () => {
  const appTitle = ref("Video Factory");
  const loading = ref(false);
  /** 同路由再次点击左侧菜单时递增，驱动当前页刷新 */
  const pageRefreshSeq = ref(0);

  const setLoading = (value: boolean) => {
    loading.value = value;
  };

  const requestPageRefresh = () => {
    pageRefreshSeq.value += 1;
  };

  return {
    appTitle,
    loading,
    setLoading,
    pageRefreshSeq,
    requestPageRefresh,
  };
});

/**
 * keep-alive 下：切回页面时刷新；同路由再次点菜单时也刷新。
 * 首次激活跳过（由页面 onMounted 拉数，避免重复请求）。
 */
export function usePageRefresh(refresh: () => void | Promise<void>) {
  const appStore = useAppStore();
  let active = false;
  let firstActivate = true;

  onActivated(() => {
    active = true;
    if (firstActivate) {
      firstActivate = false;
      return;
    }
    void refresh();
  });

  onDeactivated(() => {
    active = false;
  });

  watch(
    () => appStore.pageRefreshSeq,
    () => {
      if (active) {
        void refresh();
      }
    }
  );
}
