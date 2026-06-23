<template>
  <div>
    <el-tabs v-model="activeTab">
      <el-tab-pane label="任务列表" name="jobs">
        <TabJobs ref="jobsTabRef" @view-detail="openJobDetail" />
      </el-tab-pane>
      <el-tab-pane label="任务详情" name="detail">
        <TabJobDetail :job-id="selectedJobId" />
      </el-tab-pane>
      <el-tab-pane label="历史记录" name="history">
        <TabJobHistory />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import TabJobs from "./TabJobs.vue";
import TabJobDetail from "./detail/TabJobDetail.vue";
import TabJobHistory from "./TabJobHistory.vue";

const route = useRoute();

const activeTab = ref("jobs");
const selectedJobId = ref<number>();
const jobsTabRef = ref<InstanceType<typeof TabJobs> | null>(null);

const openJobDetail = (jobId: number) => {
  selectedJobId.value = jobId;
  activeTab.value = "detail";
};

const applyJobFromQuery = () => {
  const raw = route.query.id;
  const jobId = typeof raw === "string" ? Number.parseInt(raw, 10) : Number.NaN;
  if (Number.isFinite(jobId) && jobId > 0) {
    openJobDetail(jobId);
  }
};

onMounted(applyJobFromQuery);
watch(() => route.query.id, applyJobFromQuery);

watch(activeTab, tab => {
  if (tab === "jobs") {
    jobsTabRef.value?.refresh();
  }
});
</script>
