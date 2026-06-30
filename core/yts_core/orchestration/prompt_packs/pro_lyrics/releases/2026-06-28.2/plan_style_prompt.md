请根据已选择的曲风、Pro 结构蓝图、Hook 与用户风格线索生成 Suno style prompt 约束。
输出 JSON 字段只能包含：style_family、style_prompt_draft、style_components、lyric_guidance、negative_terms、source_signals。
style_prompt_draft 必须使用英文，描述 genre、BPM、vocal profile、instrumentation、production、arrangement，不要出现艺人名、歌曲名或版权引用。
style_components 必须逐项列出 style_prompt_draft 中的核心组件。
lyric_guidance 必须包含 language、required_sections、hook_policy、mood_arc、line_length_hint。
必须沿用 music_style_plan.selected_style_id；style_family.id 必须等于 selected_style_id，不能漂移到未选候选。
style_family 必须包含 id、label、template_id 三个字段；style_family.template_id 必须原样保留所选 music_style_plan.selected_style.template_id，不能为空，不能改写，不能省略。
style_prompt_draft 必须继承该模板的核心 genre、BPM、人声、配器和 production 方向。
Input JSON.style_prompt_contract 是硬性风格契约，优先级高于风格联想；style_prompt_draft 不得包含 style_prompt_contract.forbidden_positive_terms 中的任何词组。
style_prompt_contract.forbidden_positive_terms 是禁用正向标签，只能原样或归纳写入 negative_terms，不得写入 style_prompt_draft、style_components 或 source_signals。
如果 forbidden_positive_terms 包含 heavy distorted electric guitar，style_prompt_draft 不能出现 heavy distorted electric guitar、distorted electric guitar、heavy guitar 等同义正向描述。
negative_terms 用于记录规避项；不要把 negative_terms 当作 Suno 正向 style prompt 的一部分。
如果 selected blueprint 有 energy_curve、vocal_plan、clip_strategy，要把它们转成可执行的 arrangement/production 描述，而不是写进歌词正文。
