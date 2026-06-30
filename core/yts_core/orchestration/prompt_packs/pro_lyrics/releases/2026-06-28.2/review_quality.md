请只基于 Input JSON.review_context 评估歌词是否适合进入 Suno 音频生成队列，不要读取或补造未给出的上游候选方案。
必须逐项检查 expected.selected_hook、expected.structure.sections、line_budget、hook_placement、constraints、emotion_arc、style_prompt 是否被 generation 严格执行。
scores 六个维度必须都是 0-5 数字：hook_match、structure_match、constraint_safety、emotion_arc、singability、suno_format。
decision 只能是 pass、repair 或 block：pass 必须 submit_suno=true 且 violations/repair_targets 为空；repair 必须 submit_suno=false 且 repair_targets 非空；block 必须 submit_suno=false 且 violations 非空。
repair_targets 只写可由 repair_lyrics 节点修复的具体歌词/结构问题；不可修复或安全/版权/明确违约问题写入 violations。
输出 JSON 字段只能包含：decision、bucket、submit_suno、safety、overall_score、scores、violations、repair_targets、main_issues、suggestions、rationale。
