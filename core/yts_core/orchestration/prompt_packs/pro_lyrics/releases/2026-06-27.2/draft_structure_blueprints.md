请生成 3 个差异明显的歌曲结构蓝图，不要写完整歌词。
输出 JSON 字段只能包含：blueprints。
每个 blueprint 必须包含：id、mode、sections、section_roles、line_budget、energy_curve、hook_placement、bridge_function、vocal_plan、clip_strategy、why_this_works、risk。
mode 只能是 classic_pop_full、hook_first_douyin、ballad_slow_build、rap_verse_hook、dance_drop、guofeng_narrative、minimal_loop、duet_dialogue 之一。
sections 必须使用英文段落名，且至少包含 Verse 和 Chorus。
energy_curve 必须是 object/map；key 必须完全来自 sections 中的段落名；value 必须是 1-5 的整数，其中 1=sparse/restrained、2=low、3=medium、4=high、5=peak；禁止使用数组、小数或 0-1 归一化分值。
vocal_plan.mode 默认 solo；没有显式对唱需求时 forbidden_meta_tags 必须包含 male vocal、female vocal、duet harmony。
结构要执行 song_brief、music_style_plan 和 hook_lab。
hook_placement 必须使用以下三种形态之一：
- 英文 section 名字符串，例如 "Chorus"
- 英文 section 名数组，例如 ["Chorus", "Final Chorus"]
- 对象，且只能包含 first_appearance、repeat_sections、strategy、reason、notes；first_appearance 必须是 sections 中的英文段落名，repeat_sections 必须是 sections 中英文段落名数组，且 repeat_sections 必须引用互不重复的 sections。
repeat_sections 不要同时使用同一段落的不同别名；例如同一 blueprint 中如果 sections 使用 "Chorus2"，repeat_sections 只能写 "Chorus2"，不要再写 "Chorus 2" 或 "Final Chorus" 来表达同一个段落。
clip_strategy 必须说明 15 秒 Suno 截取点。
