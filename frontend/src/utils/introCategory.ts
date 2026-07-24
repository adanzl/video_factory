import {
  type IntroCategory,
  isIntroCategory,
} from "@/constants/introCategory";
import type { JobDetail } from "@/types/jobs";

/** 与 backend default_intro_category_for_content_style / intro_category_from_job 对齐 */
export function defaultIntroCategoryFromJob(job: JobDetail): IntroCategory {
  const saved = job.info?.intro_category;
  if (typeof saved === "string" && isIntroCategory(saved)) {
    return saved;
  }
  const style = job.info?.content_style;
  if (style === "history_mystery") {
    return "历史悬案";
  }
  if (style === "daily_story" || job.info?.daily_story_id != null) {
    return "童趣日常";
  }
  return "百科";
}
