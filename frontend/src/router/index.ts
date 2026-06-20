import { setupChunkReloadGuard } from "@/utils/chunk-reload";
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
    path: "/materials",
    name: "Materials",
    component: () => import("@/views/material/PageMaterial.vue"),
  },
  {
    path: "/topic",
    name: "Topic",
    component: () => import("@/views/topic/PageTopic.vue"),
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
