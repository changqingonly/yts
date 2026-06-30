请只根据 quality_review 的问题修复歌词，目标是通过 Suno 前置门禁。
输出仍必须是完整 SunoGeneration JSON，不要只输出局部字段。
修复后仍必须满足 Pro 制作人硬性执行合同：hook 等于 selected_hook，Chorus/Final Chorus 自然重复 Hook，按 selected_blueprint.energy_curve 推进。
lyric_prompt 格式硬性要求：必须使用英文方括号段落标签；禁止中文段落标签；禁止正文行写 男：、女：、合：；音效/环境声/制作提示必须写成英文方括号 meta tag，并同步进入 style_prompt。
非歌词说明行格式硬性要求：歌词正文只能写会被唱出来的歌词；演唱动作、制作动作、音效、环境声、镜头说明、结构说明都必须改写成英文方括号 meta tag。
