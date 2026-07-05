# LLM 调用配置

## DeepSeek 配置

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | 模型名称 |
| `DEEPSEEK_MAX_TOKENS` | `32768` | 单次最大 token |
| `DEEPSEEK_THINKING` | `true` | 全局深度思考开关 |

## Thinking 模式配置

| 方法 | thinking | 控制方式 | 理由 |
|---|---|---|---|
| `_generate_narration_only` | ✅ 开启 | 走配置 | 口播长文，不开思考只出 300 字 |
| `generate_material_script` | ✅ 开启 | 走配置 | 素材口播，同为 narration 类 |
| `optimize_script_title` | ✅ 开启 | 走配置 | 标题优化需理解全文 |
| `generate_topics` | ✅ 开启 | 走配置 | 选题生成需深度推理 |
| `fill_image_prompts` | ❌ 关闭 | 代码硬关 | 短结构化输出（每段 ~150 字） |
| `shrink_segment_texts` | ❌ 关闭 | 代码硬关 | 输入输出都很短 |
| `generate_video_description` | ❌ 关闭 | 代码硬关 | 短文案（~200 字） |
| `_fill_visual_briefs` | ❌ 关闭 | 代码硬关 | 短结构化输出 |
| `_expand_narration_if_needed` | ❌ 关闭 | 代码硬关 | 扩写已有文本 |
| `rewrite_pixabay_query` | ❌ 关闭 | 代码硬关 | 极短输出（几个词） |
| `prepare_sd15_image_prompt` | ❌ 关闭 | 代码硬关 | 短翻译（~50-100 词） |

## 配置说明

- 全局默认开启思考（`DEEPSEEK_THINKING=true`），4 个需要思考的方法走配置即可
- 7 个不需要思考的方法代码中硬编码 `thinking_enabled=False`，不受环境变量影响
- 想全局关闭思考设 `DEEPSEEK_THINKING=false`，此时 4 个方法也会受影响（长文会变短）
