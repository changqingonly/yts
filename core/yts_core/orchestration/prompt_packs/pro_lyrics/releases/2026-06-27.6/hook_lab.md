请基于 Song Brief 和已选曲风设计 Hook Lab，不要写完整歌词。
输出 JSON 字段只能包含：candidates、selected_hook、hook_strategy、repetition_strategy、clip_strategy、risk_notes。
candidates 需要 5-8 个候选，每个候选包含 hook、score、reason；selected_hook 必须来自 candidates。
Hook 应短、能唱、能重复、有画面，避免空泛鸡汤和模板化 AI 句子。
Hook 需要适配 music_style_plan.selected_style_id：抒情歌重旋律记忆点，R&B 重口语律动，民谣重朴素叙事，国风重意象凝练，短视频风格重首屏抓耳。
