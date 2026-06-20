import cosyvoiceVoicePreviews from "./cosyvoice-voice-previews.json";

export interface TtsVoiceOption {
  label: string;
  value: string;
  previewUrl?: string;
}

// cSpell: disable
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

export const TTS_VOICE_OPTIONS: TtsVoiceOption[] = TTS_VOICE_IDS.map(value => ({
  label: value,
  value,
  previewUrl: previewMap[value],
}));

export const getTtsVoicePreviewUrl = (voiceId: string): string | undefined => previewMap[voiceId];
