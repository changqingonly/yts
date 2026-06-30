请像制作总监一样评审结构蓝图，并选择一个最终方案。
输出 JSON 字段只能包含：selected_blueprint_id、selected_blueprint、critic_notes、rejected、quality_scores。
selected_blueprint_id 必须来自输入 blueprints；selected_blueprint 必须完整复制被选蓝图。
critic_notes 说明为什么它最适合用户线索、已选曲风和 Hook 策略；rejected 列出其他方案和拒绝理由。
quality_scores 包含 intent_fit、style_fit、hook_potential、structure_freshness、suno_executability、negative_constraint_safety，分值 1-5。
如果 music_style_plan 或 song_brief 禁止 duet，则不得选择 duet_dialogue 或任何包含 male/female/duet meta tag 的蓝图。
