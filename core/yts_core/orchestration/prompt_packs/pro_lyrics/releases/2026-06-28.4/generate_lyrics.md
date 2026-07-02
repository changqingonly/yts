请只基于 Input JSON.generation_context 生成完整 SunoGeneration JSON，不要读取或补造未给出的上游候选方案。
输出 JSON 字段只能包含：structure_mode、structure、title、style_prompt、lyric_prompt、hook、clip_suggestion、used_card_ids、constraint_check。
style_prompt 必须逐字复制 generation_context.style.style_prompt；不要改写、扩写或重新创作曲风提示。
hook 必须逐字等于 generation_context.hook.selected_hook；Chorus、repeat_sections 和 Final Chorus 中必须自然重复该 Hook。
structure 必须逐字等于 generation_context.structure.sections，且 lyric_prompt 必须为每一个 section 输出对应英文方括号标签和可唱中文歌词。
逐段执行 section_roles、line_budget、energy_curve、hook_placement 和 bridge_function；低能量段落克制铺陈，高能量段落增加旋律冲击、重复和情绪释放。
歌词正文只能写会被唱出来的中文歌词；不要裸露制作说明、镜头说明、结构说明或中文圆括号说明。
所有段落标签必须使用英文方括号 section 名称，例如 [Verse 1]、[Chorus]、[Final Chorus]；不要使用中文段落名。
当 constraints.duet_allowed 为 false 时，禁止出现 male vocal、female vocal、duet harmony、alternating vocals、male and female；只使用纯 section 标签。
只有 constraints.duet_allowed 为 true 时，才可以使用英文方括号声部 meta tag；仍然禁止正文行写 男：、女：、合：。
音效、环境声或收尾动作如确实需要，必须写成英文方括号 meta tag，并且不得作为中文正文行出现。
constraint_check 必须真实反映输出是否满足负面约束、Hook 重复、完整结构、情绪弧、具象画面和 Suno 可用性。
