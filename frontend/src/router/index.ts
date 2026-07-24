import { setupChunkReloadGuard } from "@/utils/utils";
import { createRouter, createWebHashHistory, type RouteRecordRaw } from "vue-router";
import PageHome from "@/views/PageHome.vue";
import PageJobs from "@/views/jobs/PageJobs.vue";
import PageMaterialVideo from "@/views/material/PageMaterialVideo.vue";
import PageMaterialAudio from "@/views/material/PageMaterialAudio.vue";
import PageClipSearch from "@/views/clips/PageClipSearch.vue";
import PageTopic from "@/views/topic/PageTopic.vue";
import PageDailyStory from "@/views/daily_story/PageDailyStory.vue";
import PageConfig from "@/views/config/PageConfig.vue";

const routes: RouteRecordRaw[] = [
  {
    path: "/",
    redirect: "/home",
  },
  {
    path: "/home",
    name: "Home",
    component: PageHome,
  },
  {
    path: "/jobs",
    name: "Jobs",
    component: PageJobs,
  },
  {
    path: "/materials/video",
    name: "MaterialsVideo",
    component: PageMaterialVideo,
  },
  {
    path: "/materials/audio",
    name: "MaterialsAudio",
    component: PageMaterialAudio,
  },
  {
    path: "/clips",
    name: "ClipSearch",
    component: PageClipSearch,
  },
  {
    path: "/topic",
    name: "Topic",
    component: PageTopic,
  },
  {
    path: "/daily-story",
    name: "DailyStory",
    component: PageDailyStory,
  },
  {
    path: "/config",
    name: "Config",
    component: PageConfig,
  },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

setupChunkReloadGuard(router);

export default router;
