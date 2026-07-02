<template>
  <div class="flex min-h-[calc(100vh-120px)] gap-4">
    <el-card shadow="never" class="w-44 shrink-0 [&_.el-card__body]:p-2">
      <el-menu
        :default-active="activeGroupId"
        class="border-none!"
        @select="onGroupSelect"
      >
        <el-menu-item v-for="group in groups" :key="group.id" :index="group.id">
          {{ group.label }}
        </el-menu-item>
      </el-menu>
    </el-card>

    <div class="min-w-0 flex-1">
      <div class="mb-4 flex flex-wrap items-center gap-3">
        <el-button type="primary" :loading="loading" @click="loadConfig">
          <el-icon><Refresh /></el-icon>
        </el-button>
        <el-button
          type="success"
          :loading="saving"
          :disabled="!dirtyCount"
          @click="handleSave"
        >
          保存{{ dirtyCount ? ` (${dirtyCount})` : "" }}
        </el-button>
        <el-button :disabled="!dirtyCount" @click="resetDraft">撤销修改</el-button>
        <span class="text-xs text-gray-400">{{ envPath }}</span>
      </div>

      <el-card v-loading="loading" shadow="never">
        <template v-if="activeGroup">
          <el-form label-width="140px" class="max-w-3xl">
            <el-form-item
              v-for="item in activeGroup.items"
              :key="item.attr"
              :label="item.label"
              class=""
            >
              <template v-if="item.readonly">
                <span class="text-gray-500">{{ formatValue(item, draft[item.attr]) }}</span>
              </template>
              <template v-else-if="item.type === 'bool'">
                <el-switch v-model="draft[item.attr]" />
              </template>
              <template v-else-if="item.type === 'number'">
                <el-input-number
                  v-model="draft[item.attr]"
                  :min="item.min ?? undefined"
                  :max="item.max ?? undefined"
                  controls-position="right"
                  class="w-40!"
                />
              </template>
              <template v-else-if="item.type === 'select'">
                <el-select v-model="draft[item.attr]" class="w-full max-w-md!">
                  <el-option
                    v-for="opt in item.options"
                    :key="opt"
                    :label="opt"
                    :value="opt"
                  />
                </el-select>
              </template>
              <template v-else>
                <el-input
                  v-model="draft[item.attr]"
                  :type="item.type === 'secret' ? 'password' : 'text'"
                  :show-password="item.type === 'secret'"
                  clearable
                  class="max-w-md!"
                />
              </template>
              <div v-if="item.description" class="mt-1 text-xs text-gray-400 ml-2">
                {{ item.description }}
              </div>
              <div class="mt-0.5 font-mono text-xs text-gray-300 ml-2">
                {{ item.env_key }}
              </div>
            </el-form-item>
          </el-form>
        </template>
        <el-empty v-else description="暂无配置分组" />
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { Refresh } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { fetchSystemConfig, updateSystemConfig } from "@/api/api-config";
import type { ConfigField, ConfigGroup } from "@/types/config";
import { useErrorHandler } from "@/composables/useErrorHandler";

type DraftValue = string | number | boolean;

const { handleError } = useErrorHandler();

const loading = ref(false);
const saving = ref(false);
const groups = ref<ConfigGroup[]>([]);
const envPath = ref("");
const activeGroupId = ref("");
const draft = reactive<Record<string, DraftValue>>({});
const baseline = reactive<Record<string, DraftValue>>({});

const activeGroup = computed(() =>
  groups.value.find(group => group.id === activeGroupId.value)
);

const dirtyCount = computed(() =>
  Object.keys(baseline).filter(attr => !isSameValue(draft[attr], baseline[attr])).length
);

const isSameValue = (a: DraftValue | undefined, b: DraftValue | undefined) => {
  if (typeof a === "number" || typeof b === "number") {
    return Number(a) === Number(b);
  }
  return String(a ?? "") === String(b ?? "");
};

const normalizeValue = (field: ConfigField): DraftValue => {
  if (field.type === "bool") {
    return Boolean(field.value);
  }
  if (field.type === "number") {
    const num = Number(field.value);
    return Number.isFinite(num) ? num : 0;
  }
  return field.value == null ? "" : String(field.value);
};

const applyPayload = (payload: Awaited<ReturnType<typeof fetchSystemConfig>>) => {
  groups.value = payload.groups;
  envPath.value = payload.env_path;

  for (const key of Object.keys(draft)) {
    delete draft[key];
  }
  for (const key of Object.keys(baseline)) {
    delete baseline[key];
  }

  for (const group of payload.groups) {
    for (const item of group.items) {
      const value = normalizeValue(item);
      draft[item.attr] = value;
      baseline[item.attr] = value;
    }
  }

  if (!activeGroupId.value && payload.groups.length) {
    activeGroupId.value = payload.groups[0].id;
  }
};

const onGroupSelect = (groupId: string) => {
  activeGroupId.value = groupId;
};

const formatValue = (item: ConfigField, value: DraftValue | undefined) => {
  if (item.type === "bool") {
    return value ? "是" : "否";
  }
  return value == null || value === "" ? "-" : String(value);
};

const loadConfig = async () => {
  loading.value = true;
  try {
    const payload = await fetchSystemConfig();
    applyPayload(payload);
  } catch (error) {
    handleError(error, "加载配置失败");
  } finally {
    loading.value = false;
  }
};

const resetDraft = () => {
  for (const [attr, value] of Object.entries(baseline)) {
    draft[attr] = value;
  }
};

const handleSave = async () => {
  const updates: Record<string, DraftValue> = {};
  for (const [attr, value] of Object.entries(baseline)) {
    if (!isSameValue(draft[attr], value)) {
      updates[attr] = draft[attr];
    }
  }
  if (!Object.keys(updates).length) {
    ElMessage.info("没有需要保存的修改");
    return;
  }

  saving.value = true;
  try {
    const result = await updateSystemConfig(updates);
    ElMessage.success(`已保存 ${result.count} 项配置`);
    await loadConfig();
  } catch (error) {
    handleError(error, "保存配置失败");
  } finally {
    saving.value = false;
  }
};

onMounted(loadConfig);
</script>
