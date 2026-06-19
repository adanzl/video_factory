<template>
  <el-aside :width="isCollapse ? '64px' : '200px'" class="transition-all duration-300">
    <el-scrollbar>
      <el-menu :default-active="route.path" :collapse="isCollapse" unique-opened router>
        <el-menu-item index="/home">
          <el-icon><HomeFilled /></el-icon>
          <template #title>首页</template>
        </el-menu-item>
        <el-menu-item index="/jobs">
          <el-icon><List /></el-icon>
          <template #title>任务队列</template>
        </el-menu-item>
        <el-menu-item index="/config">
          <el-icon><Setting /></el-icon>
          <template #title>配置</template>
        </el-menu-item>
        <el-menu-item index="#" @click="toggleCollapse">
          <el-icon><Expand v-if="isCollapse" /><Fold v-else /></el-icon>
          <template #title>折叠</template>
        </el-menu-item>
      </el-menu>
    </el-scrollbar>
  </el-aside>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRoute } from "vue-router";
import { HomeFilled, List, Setting, Expand, Fold } from "@element-plus/icons-vue";

const emit = defineEmits<{
  collapseChange: [collapsed: boolean];
}>();

const route = useRoute();
const isCollapse = ref(false);

const toggleCollapse = () => {
  isCollapse.value = !isCollapse.value;
  emit("collapseChange", isCollapse.value);
};
</script>
