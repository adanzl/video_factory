import cosyvoiceVoicePreviews from "./cosyvoice-voice-previews.json";

export interface TtsVoiceOption {
  label: string;
  value: string;
  previewUrl?: string;
}

// cSpell: disable
export const DEFAULT_TTS_VOICE ="cosyvoice-v3.5-flash-leo-40c4359c732f4b459a40f3408e1186ed";
export const TTS_VOICE_ZHAO = "cosyvoice-v3.5-flash-leo-f9d115bfdf2346edbeb9d21ecd4f9ce9";
export const TTS_VOICE_CAN = DEFAULT_TTS_VOICE;
export const TTS_VOICE_MOM = "longwan_v3";

const CLONED_VOICES: TtsVoiceOption[] = [
  {
    label: "人声复刻 (灿灿)",
    value: TTS_VOICE_CAN,
  },
  {
    label: "人声复刻 (昭昭)",
    value: TTS_VOICE_ZHAO,
  },
];

const TTS_VOICE_IDS = [
  "longwan_v3",
  "longyingjing_v3",
  "longanhuan_v3",
  "longanhuan",
  "longhuhu_v3",
  "longhuhu",
  "longniuniu_v3",
  "longniuniu",
  "longxian_v3",
  "longjielidou_v3",
  "longwan_v2",
  "longcheng_v2",
  "longhua_v2",
  "longshu_v2",
  "loongbella_v2",
  "longxiaochun_v2",
  "longxiaoxia_v2",
] as const;
// cSpell: enable

const previewMap = cosyvoiceVoicePreviews as Record<string, string>;

const systemVoiceOptions: TtsVoiceOption[] = TTS_VOICE_IDS.map(value => ({
  label: value,
  value,
  previewUrl: previewMap[value],
}));

export const TTS_VOICE_OPTIONS: TtsVoiceOption[] = [...CLONED_VOICES, ...systemVoiceOptions];

export const getTtsVoicePreviewUrl = (voiceId: string): string | undefined => previewMap[voiceId];
