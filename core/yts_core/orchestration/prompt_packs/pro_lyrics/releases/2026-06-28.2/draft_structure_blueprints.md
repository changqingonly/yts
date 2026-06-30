请生成 3 个差异明显的歌曲结构蓝图，不要写完整歌词。
输出 JSON 字段只能包含：blueprints。
每个 blueprint 必须包含：id、mode、sections、section_roles、line_budget、energy_curve、hook_placement、bridge_function、vocal_plan、clip_strategy、why_this_works、risk。
mode 只能是 classic_pop_full、hook_first_douyin、ballad_slow_build、rap_verse_hook、dance_drop、guofeng_narrative、minimal_loop、duet_dialogue 之一。
sections 必须使用英文段落名，且至少包含 Verse 和 Chorus。
sections 命名必须使用带空格的标准英文段落名：Verse 1、Verse 2、Pre-Chorus、Chorus、Chorus 2、Final Chorus、Bridge、Outro、Instrumental。禁止使用 Chorus1、Chorus2、Verse1、PreChorus1 这类紧凑写法。
同一 blueprint 的 sections 数组中禁止重复同一个段落名；重复副歌必须显式写成不同 section，例如第一次写 "Chorus"，第二次写 "Chorus 2"，最终高潮写 "Final Chorus"，不要写 ["Chorus", "Chorus"]。
energy_curve 必须是 object/map；key 必须完全来自 sections 中的段落名；value 必须是 1-5 的整数，其中 1=sparse/restrained、2=low、3=medium、4=high、5=peak；禁止使用数组、小数或 0-1 归一化分值。
vocal_plan.mode 默认 solo；没有显式对唱需求时 forbidden_meta_tags 必须包含 male vocal、female vocal、duet harmony。
结构要执行 song_brief、music_style_plan 和 hook_lab。
Input JSON.structure_contract 是硬性结构契约，优先级高于创作偏好；任何 blueprint 都必须满足其中的 section_label_format 和 hook_placement 规则。
hook_placement 必须使用以下三种形态之一：
- 英文 section 名字符串，例如 "Chorus"
- 英文 section 名数组，例如 ["Chorus", "Final Chorus"]
- 对象，且只能包含 first_appearance、repeat_sections、strategy、reason、notes；first_appearance 必须是 sections 中的英文段落名，repeat_sections 必须是 sections 中英文段落名数组，且 repeat_sections 必须引用互不重复的 sections。
hook_placement 中所有 section 引用必须 exact match sections：first_appearance 和 repeat_sections 中的每一项必须与 sections 数组中的某一项完全一致，大小写、空格、连字符都要一致。
repeat_sections 禁止包含 first_appearance；如果 first_appearance 是 "Chorus"，repeat_sections 不能包含 "Chorus"。
repeat_sections 只能列“重复出现”的后续段落，不要把 first_appearance 再写进去；例如 first_appearance 是 "Chorus" 时，repeat_sections 可以是 ["Chorus 2", "Final Chorus"]，不要写 ["Chorus", "Chorus 2"]。
不要把 Chorus 和 Chorus 2 同时写进 repeat_sections 来表达同一次重复；不要把 Chorus 2 和 Final Chorus 当作同一段落的别名混用。
clip_strategy 必须说明 15 秒 Suno 截取点。
