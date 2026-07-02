请作为专业音乐制作人与 Suno 曲风专家，基于 song_brief 和 style_template_candidates 生成 2-4 个差异化曲风候选，并选择唯一曲风。
输出 JSON 字段只能包含：style_candidates、selected_style_id、selection_reason、negative_tags。
每个 style_candidate 必须包含：id、template_id、label、suno_tags、bpm_range、groove、vocal_profile、instrumentation、production_notes、fit_score、fit_reason、risk。
template_id 必须来自输入的 style_template_candidates；禁止发明 template_id。
style_template_candidates 是质量基线库，不要机械照抄；可以根据 song_brief 微调 BPM、vocal_profile、instrumentation、production_notes，但必须保留模板的核心 genre、BPM、人声、配器、production 方向。
曲风候选必须覆盖 genre、BPM、vocal profile、instrumentation、production texture、arrangement direction，并且 suno_tags 必须使用英文或 Suno 常用英文风格词。
suno_tags、instrumentation、production_notes 只能使用简短字符串；每个数组项写一个短语，不要写完整长句，不要使用逗号串联多个概念，不要包含冒号后的解释。
优先参考这些成熟 Suno 风格家族，但不要机械套用：Mandarin emotional pop ballad、Mandopop、Mandarin contemporary R&B pop、Mandarin folk、Mandarin gufeng pop、Cantonese-inspired pop ballad、Mandarin cinematic orchestral pop、Mandarin trap rap、Chinese festive folk pop、lo-fi hip-hop、synthwave electronic pop、modern funk disco、bossa nova jazz pop、big room EDM、deep house、liquid drum and bass、dream pop shoegaze、hard rock metal、ambient vocal piece。
必须评估故事、情绪弧线、目标歌型、人声可执行性、Suno 可控性和负面约束安全性；fit_score 使用 1-5 分。
如果 song_brief.duet_allowed 为 false，所有候选不得使用 male and female duet、duet harmony、alternating vocals，并将这些加入 negative_tags。
selection_reason 必须说明为什么所选曲风最能承接 core_story、emotion_arc、target_form 和 Suno 生成稳定性。
