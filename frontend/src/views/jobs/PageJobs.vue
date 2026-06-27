<template>
  <div>
    <el-tabs v-model="activeTab">
      <el-tab-pane label="任务列表" name="jobs">
        <TabJobs ref="jobsTabRef" @view-detail="openJobDetail" />
      </el-tab-pane>
      <el-tab-pane label="任务详情" name="detail">
        <TabJobDetail :job-id="selectedJobId" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import TabJobs from "./TabJobs.vue";
import TabJobDetail from "./TabJobDetail.vue";

const route = useRoute();
const router = useRouter();

const activeTab = ref("jobs");
const selectedJobId = ref<number>();
const jobsTabRef = ref<InstanceType<typeof TabJobs> | null>(null);

const openJobDetail = (jobId: number) => {
  void router.push({ path: "/jobs", query: { id: String(jobId) } });
};

const applyJobFromQuery = () => {
  const raw = route.query.id;
  const jobId = typeof raw === "string" ? Number.parseInt(raw, 10) : Number.NaN;
  if (Number.isFinite(jobId) && jobId > 0) {
    selectedJobId.value = jobId;
    activeTab.value = "detail";
    return;
  }
  selectedJobId.value = undefined;
  if (activeTab.value === "detail") {
    activeTab.value = "jobs";
  }
};

onMounted(applyJobFromQuery);
watch(() => route.query.id, applyJobFromQuery);

watch(activeTab, tab => {
  if (tab === "jobs") {
    jobsTabRef.value?.refresh();
    if (route.query.id) {
      void router.replace({ path: "/jobs" });
    }
    return;
  }
  if (tab === "detail" && selectedJobId.value && route.query.id !== String(selectedJobId.value)) {
    void router.replace({ path: "/jobs", query: { id: String(selectedJobId.value) } });
  }
});
</script>
