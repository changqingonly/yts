请根据已选择的曲风、Pro 结构蓝图、Hook 与用户风格线索生成 Suno style prompt 约束。
输出 JSON 字段只能包含：style_family、style_prompt_draft、style_components、lyric_guidance、negative_terms、source_signals。
style_prompt_draft 必须使用英文，描述 genre、BPM、vocal profile、instrumentation、production、arrangement，不要出现艺人名、歌曲名或版权引用。
style_components 必须逐项列出 style_prompt_draft 中的核心组件。
lyric_guidance 必须包含 language、required_sections、hook_policy、mood_arc、line_length_hint。
必须沿用 music_style_plan.selected_style_id；style_family.id 必须等于 selected_style_id，不能漂移到未选候选。
如果 selected blueprint 有 energy_curve、vocal_plan、clip_strategy，要把它们转成可执行的 arrangement/production 描述，而不是写进歌词正文。
