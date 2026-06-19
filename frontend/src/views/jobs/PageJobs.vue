<template>
  <div>
    <el-tabs v-model="activeTab">
      <el-tab-pane label="任务列表" name="jobs">
        <TabJobs @view-detail="openJobDetail" />
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
import { ref } from "vue";
import TabJobs from "./TabJobs.vue";
import TabJobDetail from "./detail/TabJobDetail.vue";
import TabJobHistory from "./TabJobHistory.vue";

const activeTab = ref("jobs");
const selectedJobId = ref<number>();

const openJobDetail = (jobId: number) => {
  selectedJobId.value = jobId;
  activeTab.value = "detail";
};
</script>
