/** 片头风格（与 backend job_info intro_category 一致） */
export const INTRO_CATEGORY_OPTIONS = [
  { value: "童趣日常", label: "童趣日常" },
  { value: "百科", label: "童趣百科" },
  { value: "历史悬案", label: "历史悬案" },
] as const;

export type IntroCategory = (typeof INTRO_CATEGORY_OPTIONS)[number]["value"];

const INTRO_CATEGORY_SET = new Set<string>(
  INTRO_CATEGORY_OPTIONS.map(option => option.value)
);

export function isIntroCategory(value: string): value is IntroCategory {
  return INTRO_CATEGORY_SET.has(value);
}
