import { setupChunkReloadGuard } from "@/utils/utils";
import { createRouter, createWebHashHistory, type RouteRecordRaw } from "vue-router";

const routes: RouteRecordRaw[] = [
  {
    path: "/",
    redirect: "/home",
  },
  {
    path: "/home",
    name: "Home",
    component: () => import("@/views/PageHome.vue"),
  },
  {
    path: "/jobs",
    name: "Jobs",
    component: () => import("@/views/jobs/PageJobs.vue"),
  },
  {
    path: "/materials/video",
    name: "MaterialsVideo",
    component: () => import("@/views/material/PageMaterialVideo.vue"),
  },
  {
    path: "/materials/audio",
    name: "MaterialsAudio",
    component: () => import("@/views/material/PageMaterialAudio.vue"),
  },
  {
    path: "/clips",
    name: "ClipSearch",
    component: () => import("@/views/clips/PageClipSearch.vue"),
  },
  {
    path: "/topic",
    name: "Topic",
    component: () => import("@/views/topic/PageTopic.vue"),
  },
  {
    path: "/daily-story",
    name: "DailyStory",
    component: () => import("@/views/daily_story/PageDailyStory.vue"),
  },
  {
    path: "/config",
    name: "Config",
    component: () => import("@/views/config/PageConfig.vue"),
  },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

setupChunkReloadGuard(router);

export default router;
