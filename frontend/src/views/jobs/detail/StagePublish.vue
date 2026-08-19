<template>
  <div :class="STAGE_ROOT_CLASS">
    <StageActionBar
      :loading="submitting"
      :disabled="actionDisabled"
      :disabled-reason="actionDisabledReason"
      primary-label="生成"
      :show-to-end="false"
      @primary="handleRun"
    />
    <div :class="STAGE_BODY_CLASS">
    <div class="space-y-4">
      <!-- 投稿信息：标题 / 视频介绍 / 推荐标签 -->
      <section :class="STAGE_PANEL_CLASS">
        <div :class="STAGE_PANEL_HEADER_CLASS">
          <div class="flex items-center gap-2">
            <div :class="STAGE_PANEL_TITLE_TEXT_CLASS">投稿信息</div>
            <el-tag v-if="biliSessionUser" size="small" type="success" effect="plain">
              {{ biliSessionUser }}
            </el-tag>
          </div>
          <div class="flex items-center gap-2">
            <el-button
              size="small"
              :loading="qrLoading"
              @click="handleOpenQrLogin"
            >
              {{ biliSessionUser ? "重新扫码" : "扫码登录" }}
            </el-button>
            <el-button
              v-if="publishTitle"
              size="small"
              @click="openUploadPage"
            >
              B站上传
            </el-button>
          </div>
        </div>
        <el-alert
          v-if="biliSessionError"
          type="error"
          :closable="false"
          show-icon
          class="mb-3"
          :title="biliSessionError"
        />
        <div
          v-else-if="biliSessionUser"
          class="mb-3 flex flex-wrap items-center justify-between gap-3 rounded border border-blue-100 bg-blue-50/60 px-3 py-1"
        >
          <span class="text-sm text-gray-700">{{ biliLoginHint }}</span>
          <div class="flex flex-wrap items-center gap-2">
            <el-checkbox v-model="scheduleEnabled">定时发布</el-checkbox>
            <el-time-picker
              v-if="scheduleEnabled"
              v-model="scheduleTime"
              format="HH:mm"
              value-format="HH:mm"
              placeholder="选择时分"
              :clearable="false"
              size="small"
              class="w-40!"
            />
            <span v-if="scheduleEnabled && schedulePreview" class="text-sm text-gray-500">
              将于 {{ schedulePreview }} 发布
            </span>
            <el-button
              type="primary"
              size="small"
              :loading="publishing"
              :disabled="publishActionDisabled"
              @click="handleSubmit"
            >
              投稿
            </el-button>
          </div>
        </div>
        <el-alert
          v-else-if="biliLoginHint"
          type="info"
          :closable="false"
          show-icon
          class="mb-3"
          :title="biliLoginHint"
        />
        <el-table
          :data="publishMetaRows"
          border
          class="publish-meta-table w-full"
          :show-header="false"
        >
          <el-table-column label="字段" prop="label" width="96" align="center" />
          <el-table-column label="内容" min-width="240">
            <template #default="{ row }">
              <template v-if="row.key === 'title'">
                <span
                  v-if="publishTitle"
                  class="block text-base leading-relaxed wrap-break-word"
                >
                  {{ publishTitle }}
                </span>
                <span v-else class="text-sm text-gray-400">暂无标题</span>
              </template>
              <template v-else-if="row.key === 'description'">
                <span
                  v-if="videoDescription"
                  class="block leading-relaxed wrap-break-word whitespace-pre-wrap"
                >
                  {{ videoDescription }}
                </span>
                <span v-else class="text-sm text-gray-400">
                  暂无视频介绍
                  <span v-if="canRegenerateDescription">，可点击「生成」</span>
                </span>
              </template>
              <template v-else-if="row.key === 'tags'">
                <div v-if="publishTags.length" class="flex flex-wrap gap-2">
                  <el-tag
                    v-for="tag in publishTags"
                    :key="tag.name"
                    :type="tag.type"
                    effect="plain"
                  >
                    {{ tag.name }}
                    <span v-if="tag.hint" class="ml-1 text-xs opacity-70">{{ tag.hint }}</span>
                  </el-tag>
                </div>
                <span v-else class="text-sm text-gray-400">
                  暂无标签
                  <span v-if="canRegenerateTags">，可点击「生成」</span>
                </span>
              </template>
              <template v-else-if="row.key === 'dynamic'">
                <span
                  v-if="fanDynamic"
                  class="block leading-relaxed wrap-break-word whitespace-pre-wrap"
                >
                  {{ fanDynamic }}
                </span>
                <span v-else class="text-sm text-gray-400">暂无粉丝动态</span>
              </template>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="220" align="right">
            <template #default="{ row }">
              <div class="flex flex-wrap justify-end gap-1">
                <template v-if="row.key === 'title'">
                  <el-button
                    v-if="publishTitle"
                    size="small"
                    type="primary"
                    plain
                    :icon="DocumentCopy"
                    @click="copyPublishTitle"
                  />
                </template>
                <template v-else-if="row.key === 'description'">
                  <el-button
                    v-if="canRegenerateDescription"
                    type="primary"
                    plain
                    size="small"
                    :loading="regeneratingDescription"
                    :disabled="actionDisabled"
                    @click="handleRegenerateDescription"
                  >
                    生成
                  </el-button>
                  <el-button
                    v-if="videoDescription"
                    size="small"
                    type="primary"
                    plain
                    :icon="DocumentCopy"
                    @click="copyVideoDescription"
                  />
                </template>
                <template v-else-if="row.key === 'tags'">
                  <el-button
                    v-if="canRegenerateTags"
                    type="primary"
                    plain
                    size="small"
                    :loading="regeneratingTags"
                    :disabled="actionDisabled"
                    @click="handleRegenerateTags"
                  >
                    生成
                  </el-button>
                  <el-button
                    v-if="publishTags.length"
                    size="small"
                    type="primary"
                    plain
                    :icon="DocumentCopy"
                    @click="copyTags"
                  />
                </template>
                <template v-else-if="row.key === 'dynamic'">
                  <el-button
                    v-if="fanDynamic"
                    size="small"
                    type="primary"
                    plain
                    :icon="DocumentCopy"
                    @click="copyFanDynamic"
                  />
                </template>
              </div>
            </template>
          </el-table-column>
        </el-table>
        <el-alert
          v-if="publishResult"
          class="mt-3"
          :type="publishResultAlertType"
          :closable="false"
          show-icon
        >
          <template #title>
            <span>{{ publishResultTitle }}</span>
            <a
              v-if="publishResult.url"
              :href="publishResult.url"
              target="_blank"
              rel="noopener noreferrer"
              class="ml-2 text-blue-600 underline"
            >
              {{ publishResult.bvid || "打开稿件" }}
            </a>
          </template>
        </el-alert>
        <el-alert
          v-else-if="job.skip_publish"
          class="mt-3"
          type="info"
          :closable="false"
          show-icon
          title="当前任务勾选了跳过投稿，「投稿」按钮不可用；可先「生成」补齐简介。"
        />
      </section>

      <!-- 封面 / 成片 -->
      <div :class="STAGE_TWO_COL_CLASS">
        <div class="min-w-70 max-w-full shrink-0 basis-130">
          <section :class="STAGE_PANEL_CLASS">
            <div :class="STAGE_PANEL_HEADER_CLASS">
              <div class="flex items-center gap-2">
                <div :class="STAGE_PANEL_TITLE_TEXT_CLASS">封面</div>
                <el-button
                  v-if="coverUrl"
                  size="small"
                  :type="showCover43Guide ? 'primary' : 'default'"
                  @click="showCover43Guide = !showCover43Guide"
                >
                  4:3
                </el-button>
              </div>
              <el-button
                v-if="coverPath"
                size="small"
                :loading="downloadingCover"
                @click="handleDownloadCover"
              >
                下载
              </el-button>
            </div>
            <div v-if="coverUrl" class="flex justify-center">
              <div
                class="relative flex items-center justify-center overflow-hidden rounded-lg border border-gray-200 bg-gray-50"
                :style="coverBoxStyle"
              >
                <el-image
                  :key="coverUrl"
                  :src="lazyCoverUrl"
                  :preview-src-list="lazyCoverPreviewList"
                  :crossorigin="MEDIA_CROSS_ORIGIN"
                  fit="contain"
                  class="block h-full w-full [&_.el-image__inner]:block [&_.el-image__inner]:h-full [&_.el-image__inner]:w-full [&_.el-image__inner]:object-contain"
                  @load="onCoverLoad"
                  @error="coverLoadError = true"
                >
                  <template #error>
                    <div class="flex size-full items-center justify-center text-sm text-gray-400">
                      封面加载失败
                    </div>
                  </template>
                </el-image>
                <div v-if="showCover43Guide" class="pointer-events-none absolute inset-0 z-10">
                  <template v-if="cover43Guide.mode === 'horizontal'">
                    <div
                      class="absolute inset-x-0 border-t-2 border-amber-400/90"
                      :style="{ top: `${cover43Guide.startPct}%` }"
                    />
                    <div
                      class="absolute inset-x-0 border-t-2 border-amber-400/90"
                      :style="{ top: `${cover43Guide.startPct + cover43Guide.spanPct}%` }"
                    />
                  </template>
                  <template v-else>
                    <div
                      class="absolute inset-y-0 border-l-2 border-amber-400/90"
                      :style="{ left: `${cover43Guide.startPct}%` }"
                    />
                    <div
                      class="absolute inset-y-0 border-l-2 border-amber-400/90"
                      :style="{ left: `${cover43Guide.startPct + cover43Guide.spanPct}%` }"
                    />
                  </template>
                </div>
              </div>
            </div>
            <div v-else :class="STAGE_EMPTY_CLASS">暂无封面，请先在「封面」阶段生成</div>
            <el-alert
              v-if="coverLoadError && coverPath"
              type="warning"
              title="封面加载失败"
              :closable="false"
              class="mt-2"
            />
          </section>
        </div>

        <div :class="STAGE_COL_RIGHT_CLASS">
          <section :class="STAGE_PANEL_CLASS">
            <div :class="STAGE_PANEL_HEADER_CLASS">
              <div :class="STAGE_PANEL_TITLE_TEXT_CLASS">成片</div>
              <el-button
                v-if="finalFilePath"
                size="small"
                :loading="downloadingFinal"
                @click="handleDownloadFinal"
              >
                下载
              </el-button>
            </div>
            <div v-if="videoUrl" class="flex justify-center">
              <div
                class="overflow-hidden rounded-lg border border-gray-200 bg-black"
                :style="previewBoxStyle"
              >
                <video
                  :key="videoUrl"
                  class="block h-full w-full bg-black object-contain"
                  :src="lazyVideoUrl"
                  :crossorigin="MEDIA_CROSS_ORIGIN"
                  controls
                  playsinline
                  preload="metadata"
                  @error="finalLoadError = true"
                  @loadedmetadata="onVideoMetadata"
                />
              </div>
            </div>
            <div v-else :class="STAGE_EMPTY_CLASS">暂无成片，请先在「合成」阶段生成</div>
            <el-alert
              v-if="finalLoadError && finalFilePath"
              type="warning"
              title="成片加载失败"
              :closable="false"
              class="mt-2"
            />
          </section>
        </div>
      </div>
    </div>

    <StageLogsSection :logs="logs" />

    <el-dialog
      v-model="qrDialogVisible"
      title="B站扫码登录"
      width="360px"
      destroy-on-close
    >
      <div class="space-y-3">
        <el-alert
          type="warning"
          :closable="false"
          show-icon
          title="扫码后若手机端继续要求短信验证码或安全确认，请在手机上完成；未完成前不会判定为已登录。"
        />
        <div v-if="qrSvg" class="flex justify-center">
          <img :src="qrSvg" alt="B站扫码登录二维码" class="h-60 w-60 rounded border border-gray-200" />
        </div>
        <div v-else class="text-center text-sm text-gray-500">二维码生成中...</div>
        <div class="text-center text-sm text-gray-600">{{ qrStatusMessage }}</div>
      </div>
      <template #footer>
        <div class="flex justify-end gap-2">
          <el-button @click="qrDialogVisible = false">关闭</el-button>
          <el-button type="primary" :loading="qrLoading" @click="handleOpenQrLogin">
            刷新二维码
          </el-button>
        </div>
      </template>
    </el-dialog>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { DocumentCopy } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  generatePublishMeta,
  generateVideoDescription,
  generateTags,
  submitBiliPublish,
} from "@/api/api-jobs";
import { createBiliLoginQr, getBiliSession, pollBiliLoginQr } from "@/api/api-publish";
import { getDailyStory } from "@/api/api-daily-story";
import { downloadMediaFile, getMediaFileUrl, getMediaPicViewUrl } from "@/api/api-media";
import type { JobDetail, JobLog } from "@/types/jobs";
import type { ScriptJson } from "@/types/jobs/script";
import {
  buildMediaPreviewBoxStyle,
  computeCentered43GuideLines,
  guessIntroPreviewAspectRatio,
  lazyMediaSrc,
  parseAspectRatio,
  resolveFinalPath,
  MEDIA_CROSS_ORIGIN,
} from "@/utils/media";
import { useErrorHandler } from "@/composables/useErrorHandler";
import { copyText } from "@/utils/utils";
import StageActionBar from "./StageActionBar.vue";
import StageLogsSection from "./StageLogsSection.vue";
import {
  STAGE_BODY_CLASS,
  STAGE_COL_RIGHT_CLASS,
  STAGE_EMPTY_CLASS,
  STAGE_PANEL_CLASS,
  STAGE_PANEL_HEADER_CLASS,
  STAGE_PANEL_TITLE_TEXT_CLASS,
  STAGE_ROOT_CLASS,
  STAGE_TWO_COL_CLASS,
} from "./stageLayout";

const CHAT_FIXED_TAGS = [
  "姐弟日常",
  "生活记录",
  "亲子日常",
  "搞笑对话",
  "育儿",
  "家庭搞笑",
  "儿童对话",
] as const;

const CHAT_ACTIVITY_TAG = "闪闪发光的家庭日";

const props = defineProps<{
  job: JobDetail;
  logs: JobLog[];
  stageActive?: boolean;
}>();

const emit = defineEmits<{
  refresh: [];
}>();

const { handleError } = useErrorHandler();

const submitting = ref(false);
const publishing = ref(false);
const regeneratingDescription = ref(false);
const regeneratingTags = ref(false);
const downloadingCover = ref(false);
const downloadingFinal = ref(false);
const coverLoadError = ref(false);
const finalLoadError = ref(false);
const showCover43Guide = ref(false);
const biliSessionError = ref("");
const biliSessionUser = ref("");
const biliLoginHint = ref("");
const qrDialogVisible = ref(false);
const qrLoading = ref(false);
const qrSvg = ref("");
const qrSessionId = ref("");
const qrStatusMessage = ref("请使用哔哩哔哩 App 扫码");
const scheduleEnabled = ref(true);
const scheduleTime = ref("07:00");
const dailyStoryKey = ref("");
let qrPollTimer: ReturnType<typeof setInterval> | null = null;

const COVER_PREVIEW_OPTIONS = {
  maxWidthPx: 560,
  maxViewportRatio: 0.9,
} as const;

const PUBLISH_PREVIEW_OPTIONS = {
  maxWidthPx: 560,
  maxViewportRatio: 0.85,
} as const;

const actionDisabled = computed(() => props.job.status === "running");
const actionDisabledReason = computed(() =>
  props.job.status === "running" ? "任务运行中，请稍后再试" : ""
);

const stopQrPolling = () => {
  if (qrPollTimer) {
    clearInterval(qrPollTimer);
    qrPollTimer = null;
  }
};

const refreshBiliSession = async () => {
  try {
    const session = await getBiliSession();
    biliSessionError.value = "";
    biliSessionUser.value = session.uname || "";
    biliLoginHint.value = biliSessionUser.value ? `当前远程登录账号：${biliSessionUser.value}` : "";
  } catch (error) {
    const axiosError = error as { response?: { data?: { error?: string } } };
    biliSessionError.value =
      axiosError.response?.data?.error ||
      "B 站 Cookie 已过期或未登录，请在本页重新扫码登录";
    biliSessionUser.value = "";
    biliLoginHint.value = "";
  }
};

const refreshDailyStoryKey = async () => {
  if (!isChatPipeline.value) {
    dailyStoryKey.value = "";
    return;
  }
  const storyId = props.job.info?.daily_story_id ?? props.job.material_id;
  if (!storyId) {
    dailyStoryKey.value = "";
    return;
  }
  try {
    const story = await getDailyStory(Number(storyId));
    dailyStoryKey.value =
      story.key?.trim() || story.story?.key?.trim() || "";
  } catch {
    dailyStoryKey.value = "";
  }
};

onMounted(() => {
  void refreshBiliSession();
  void refreshDailyStoryKey();
  const saved = props.job.info?.publish_schedule;
  if (saved) {
    scheduleEnabled.value = Boolean(saved.enabled);
    if (saved.time) {
      scheduleTime.value = saved.time;
    }
  }
});
onBeforeUnmount(stopQrPolling);
watch(qrDialogVisible, visible => {
  if (!visible) {
    stopQrPolling();
  }
});

const pollQrStatus = async () => {
  if (!qrSessionId.value) {
    return;
  }
  try {
    const result = await pollBiliLoginQr(qrSessionId.value);
    qrStatusMessage.value = result.message;
    if (result.status === "confirmed") {
      ElMessage.success("B站扫码登录成功");
      stopQrPolling();
      qrDialogVisible.value = false;
      await refreshBiliSession();
      return;
    }
    if (result.status === "need_verify") {
      qrStatusMessage.value =
        result.message || "扫码后还需要短信/验证码，请在手机端完成后再刷新二维码";
    }
  } catch (error) {
    const axiosError = error as { response?: { data?: { error?: string; code?: string } } };
    const code = axiosError.response?.data?.code || "";
    const message = axiosError.response?.data?.error || "查询扫码状态失败";
    qrStatusMessage.value = message;
    if (code === "bili_qrcode_expired") {
      stopQrPolling();
    }
  }
};

const handleOpenQrLogin = async () => {
  qrLoading.value = true;
  stopQrPolling();
  try {
    const result = await createBiliLoginQr();
    qrDialogVisible.value = true;
    qrSvg.value = result.qrcode_svg;
    qrSessionId.value = result.session_id;
    qrStatusMessage.value = "请使用哔哩哔哩 App 扫码；若手机端继续要求短信验证码或安全确认，也请在手机端完成";
    qrPollTimer = setInterval(() => {
      void pollQrStatus();
    }, 2000);
    await pollQrStatus();
  } catch (error) {
    handleError(error, "生成扫码二维码失败");
  } finally {
    qrLoading.value = false;
  }
};

const script = computed(() => {
  const value = props.job.script_json;
  if (!value || typeof value !== "object") {
    return null;
  }
  return value as ScriptJson;
});

const publishTitle = computed(() => props.job.title?.trim() || script.value?.title?.trim() || "");

const isChatPipeline = computed(() => props.job.pipeline === "chat");

const videoDescription = computed(() => script.value?.video_description?.trim() || "");

const fanDynamic = computed(() => {
  const title = publishTitle.value;
  if (isChatPipeline.value) {
    return title
      ? `《${title}》｜姐弟日常小剧场，昭昭灿灿又整活了。`
      : "姐弟日常小剧场更新啦，昭昭灿灿的日常对话。";
  }
  return title ? `${title}｜新视频已发布，欢迎收看。` : "";
});

type PublishTagItem = {
  name: string;
  type?: "success" | "warning" | "info" | "danger";
  hint?: string;
};

const publishTags = computed((): PublishTagItem[] => {
  if (isChatPipeline.value) {
    const items: PublishTagItem[] = CHAT_FIXED_TAGS.map(name => ({
      name,
      type: "warning",
    }));
    if (dailyStoryKey.value) {
      items.push({ name: dailyStoryKey.value, type: "success", hint: "主题" });
    } else {
      items.push({ name: "待取故事 key", type: "info", hint: "主题" });
    }
    items.push({ name: CHAT_ACTIVITY_TAG, type: "danger", hint: "活动" });
    return items;
  }
  return (script.value?.tags || []).map(raw => ({
    name: String(raw).replace(/^#/, "").trim(),
    type: "warning" as const,
  }));
});

const publishResult = computed(() => props.job.info?.publish_result ?? null);

const publishResultAlertType = computed(() => {
  const status = publishResult.value?.status;
  if (status === "success") return "success";
  if (status === "failed") return "error";
  return "info";
});

const publishResultTitle = computed(() => {
  const result = publishResult.value;
  if (!result) return "";
  const parts = [
    result.status === "success"
      ? "已投稿 B 站"
      : result.status === "skipped"
        ? "已跳过上传"
        : "投稿未完成",
    result.message,
  ].filter(Boolean);
  return parts.join("：");
});

const publishMetaRows = [
  { key: "title", label: "标题" },
  { key: "description", label: "视频介绍" },
  { key: "tags", label: "标签" },
  { key: "dynamic", label: "粉丝动态" },
] as const;

const canRegenerateDescription = computed(() => Boolean(script.value?.narration?.trim()));

const canRegenerateTags = computed(
  () => !isChatPipeline.value && Boolean(script.value?.narration?.trim())
);

const schedulePreview = computed(() => {
  if (!scheduleEnabled.value || !scheduleTime.value) {
    return "";
  }
  const [hourText, minuteText] = scheduleTime.value.split(":");
  const hour = Number(hourText);
  const minute = Number(minuteText);
  if (Number.isNaN(hour) || Number.isNaN(minute)) {
    return "";
  }
  const now = new Date();
  const candidate = new Date(now);
  candidate.setHours(hour, minute, 0, 0);
  if (candidate <= now) {
    candidate.setDate(candidate.getDate() + 1);
  }
  const month = candidate.getMonth() + 1;
  const day = candidate.getDate();
  const hh = String(candidate.getHours()).padStart(2, "0");
  const mm = String(candidate.getMinutes()).padStart(2, "0");
  return `${month}月${day}日 ${hh}:${mm}`;
});

const coverPath = computed(() => props.job.cover_path?.trim() || "");
const coverUrl = computed(() => {
  const base = getMediaPicViewUrl(coverPath.value, 640);
  if (!base) return "";
  const ver = props.job.version;
  return ver !== undefined && ver !== null ? `${base}&v=${ver}` : base;
});

const finalFilePath = computed(() => resolveFinalPath(props.job.final_path));

const publishActionDisabled = computed(
  () =>
    actionDisabled.value ||
    Boolean(props.job.skip_publish) ||
    !finalFilePath.value ||
    Boolean(biliSessionError.value) ||
    !biliSessionUser.value
);

const publishActionDisabledReason = computed(() => {
  if (props.job.skip_publish) return "任务已勾选跳过投稿";
  if (!finalFilePath.value) return "请先在「合成」阶段生成成片";
  if (biliSessionError.value || !biliSessionUser.value) return "请先扫码登录 B 站";
  if (props.job.status === "running") return "任务运行中，请稍后再试";
  return "";
});

const videoUrl = computed(() =>
  getMediaFileUrl(finalFilePath.value, props.job.version)
);
const lazyCoverUrl = computed(() => lazyMediaSrc(coverUrl.value, props.stageActive));
const lazyCoverPreviewList = computed(() => {
  if (!coverPath.value) return [];
  const fullUrl = getMediaFileUrl(coverPath.value, props.job.version);
  const lazyUrl = lazyMediaSrc(fullUrl, props.stageActive);
  return lazyUrl ? [lazyUrl] : [];
});
const lazyVideoUrl = computed(() => lazyMediaSrc(videoUrl.value, props.stageActive));

const publishOrientation = computed((): "auto" | "portrait" | "landscape" => {
  const saved = props.job.info?.orientation;
  if (saved === "auto" || saved === "portrait" || saved === "landscape") {
    return saved;
  }
  return props.job.pipeline === "material" ? "auto" : "portrait";
});

const publishPreviewAspectRatio = computed(() =>
  guessIntroPreviewAspectRatio(publishOrientation.value, props.job.pipeline)
);

const previewBoxStyle = computed(() =>
  buildMediaPreviewBoxStyle(
    undefined,
    undefined,
    publishPreviewAspectRatio.value,
    PUBLISH_PREVIEW_OPTIONS
  )
);

const coverBoxStyle = computed(() =>
  buildMediaPreviewBoxStyle(
    undefined,
    undefined,
    publishPreviewAspectRatio.value,
    COVER_PREVIEW_OPTIONS
  )
);

const cover43Guide = computed(() =>
  computeCentered43GuideLines(
    undefined,
    undefined,
    parseAspectRatio(publishPreviewAspectRatio.value)
  )
);

function pathExtension(path: string, fallback: string): string {
  const name = path.replace(/\\/g, "/").split("/").pop() || "";
  const dot = name.lastIndexOf(".");
  if (dot <= 0) return fallback;
  return name.slice(dot);
}

function sanitizeDownloadBase(name: string): string {
  const cleaned = name
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, "_")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/[. ]+$/g, "");
  return cleaned || `job-${props.job.id}`;
}

const downloadBaseName = computed(() =>
  sanitizeDownloadBase(publishTitle.value || props.job.title || "")
);

const coverDownloadName = computed(
  () => `${downloadBaseName.value}${pathExtension(coverPath.value, ".jpg")}`
);

const finalDownloadName = computed(
  () => `${downloadBaseName.value}${pathExtension(finalFilePath.value, ".mp4")}`
);

const onCoverLoad = () => {
  coverLoadError.value = false;
};

const onVideoMetadata = () => {
  finalLoadError.value = false;
};

const copyPublishTitle = async () => {
  if (!publishTitle.value) {
    return;
  }
  try {
    await copyText(publishTitle.value);
    ElMessage.success("已复制标题");
  } catch (error) {
    handleError(error, "复制失败");
  }
};

const openUploadPage = () => {
  window.open("https://member.bilibili.com/platform/upload/video/frame", "_blank");
};

const copyVideoDescription = async () => {
  if (!videoDescription.value) {
    return;
  }
  try {
    await copyText(videoDescription.value);
    ElMessage.success("已复制视频介绍");
  } catch (error) {
    handleError(error, "复制失败");
  }
};

const copyTags = async () => {
  const text = publishTags.value.map(tag => tag.name).join(" ");
  if (!text) {
    return;
  }
  try {
    await copyText(text);
    ElMessage.success("已复制标签");
  } catch (error) {
    handleError(error, "复制失败");
  }
};

const copyFanDynamic = async () => {
  if (!fanDynamic.value) {
    return;
  }
  try {
    await copyText(fanDynamic.value);
    ElMessage.success("已复制粉丝动态");
  } catch (error) {
    handleError(error, "复制失败");
  }
};

const handleRun = async () => {
  try {
    await ElMessageBox.confirm(
      "确定生成投稿信息？将补齐缺失的视频介绍（chat 流水线标签为固定规则，无需生成）。",
      "确认生成",
      {
        type: "warning",
        confirmButtonText: "生成",
        cancelButtonText: "取消",
      }
    );
  } catch {
    return;
  }

  submitting.value = true;
  try {
    await generatePublishMeta(props.job.id);
    ElMessage.success("投稿信息已生成");
    emit("refresh");
  } catch (error) {
    handleError(error, "生成失败");
  } finally {
    submitting.value = false;
  }
};

const handleSubmit = async () => {
  if (publishActionDisabled.value) {
    ElMessage.warning(publishActionDisabledReason.value || "当前无法投稿");
    return;
  }
  const scheduleHint = scheduleEnabled.value
    ? `，定时于 ${schedulePreview.value || scheduleTime.value} 发布`
    : "，立即发布";
  try {
    await ElMessageBox.confirm(
      `确定投稿到 B 站？将上传成片与封面，并使用当前登录账号提交（公开浏览${scheduleHint}）。失败只记日志，任务不会标失败。`,
      "确认投稿",
      {
        type: "warning",
        confirmButtonText: "投稿",
        cancelButtonText: "取消",
      }
    );
  } catch {
    return;
  }

  publishing.value = true;
  try {
    await submitBiliPublish(props.job.id, {
      publish_schedule: {
        enabled: scheduleEnabled.value,
        time: scheduleEnabled.value ? scheduleTime.value : null,
      },
    });
    ElMessage.success("已提交 B 站投稿，任务已开始执行");
    emit("refresh");
  } catch (error) {
    handleError(error, "投稿失败");
  } finally {
    publishing.value = false;
  }
};

const handleRegenerateDescription = async () => {
  regeneratingDescription.value = true;
  try {
    await generateVideoDescription(props.job.id);
    ElMessage.success("视频介绍已重新生成");
    emit("refresh");
  } catch (error) {
    handleError(error, "重新生成视频介绍失败");
  } finally {
    regeneratingDescription.value = false;
  }
};

const handleRegenerateTags = async () => {
  regeneratingTags.value = true;
  try {
    await generateTags(props.job.id);
    ElMessage.success("推荐标签已生成");
    emit("refresh");
  } catch (error) {
    handleError(error, "生成推荐标签失败");
  } finally {
    regeneratingTags.value = false;
  }
};

const handleDownloadCover = async () => {
  if (!coverPath.value) {
    return;
  }
  downloadingCover.value = true;
  try {
    await downloadMediaFile(coverPath.value, coverDownloadName.value);
    ElMessage.success("已开始下载封面");
  } catch (error) {
    handleError(error, "下载封面失败");
  } finally {
    downloadingCover.value = false;
  }
};

const handleDownloadFinal = async () => {
  if (!finalFilePath.value) {
    return;
  }
  downloadingFinal.value = true;
  try {
    await downloadMediaFile(finalFilePath.value, finalDownloadName.value);
    ElMessage.success("已开始下载成片");
  } catch (error) {
    handleError(error, "下载成片失败");
  } finally {
    downloadingFinal.value = false;
  }
};

watch(
  () => [props.job.info?.daily_story_id, props.job.material_id, props.job.pipeline],
  () => {
    void refreshDailyStoryKey();
  }
);

watch(
  () => props.job.info?.publish_schedule,
  saved => {
    if (!saved) {
      return;
    }
    scheduleEnabled.value = Boolean(saved.enabled);
    if (saved.time) {
      scheduleTime.value = saved.time;
    }
  }
);

watch(coverPath, () => {
  coverLoadError.value = false;
  showCover43Guide.value = false;
});

watch(finalFilePath, () => {
  finalLoadError.value = false;
});
</script>
