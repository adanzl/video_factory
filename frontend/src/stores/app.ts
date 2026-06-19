import { defineStore } from "pinia";
import { ref } from "vue";

export const useAppStore = defineStore("app", () => {
  const appTitle = ref("Video Factory");
  const loading = ref(false);

  const setLoading = (value: boolean) => {
    loading.value = value;
  };

  return {
    appTitle,
    loading,
    setLoading,
  };
});
