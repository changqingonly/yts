用户需求、意图、结构规划、风格规格和 Pro 制作人计划已经给出。请生成完整 SunoGeneration JSON。
生成要求：输出严格 JSON，副歌重复 Hook 3-5 次，避开用户否定约束。
Pro 制作人硬性执行合同：
1. hook 字段必须严格等于 Pro Hook Lab 的 selected_hook。
2. lyric_prompt 的 Chorus 和 Final Chorus 必须自然重复该 selected_hook；不要另起一个新的 Hook。
3. 必须按 selected_blueprint.energy_curve 安排段落能量推进；energy_curve 使用 1-5 整数档位，1=sparse/restrained、2=low、3=medium、4=high、5=peak；低能量段落克制铺陈，高能量段落增加旋律冲击、重复和情绪释放。
4. 必须执行 selected_blueprint.section_roles、line_budget、hook_placement、bridge_function；如果字段为空则保持结构规划 JSON 的段落顺序。
5. 返回 JSON 的 hook、clip_suggestion、lyric_prompt 三者必须围绕同一个 selected_hook。
当前是男女对唱模式时：允许使用 [Verse 1 | male vocal]、[Verse 2 | female vocal]、[Chorus | duet harmony] 等英文方括号声部 meta tag；仍然禁止在正文行写 男：歌词、女：歌词、合：歌词。
当前不是男女对唱模式时：lyric_prompt 禁止出现 male vocal、female vocal、duet harmony、alternating vocals、male and female；只能使用 [Verse 1]、[Verse 2]、[Chorus] 这类纯段落标签；远方的你 / 故人 / 回忆我们 / 甜蜜往事 只是抒情对象或关系记忆，不代表双人演唱。
lyric_prompt 格式硬性要求：
1. 必须使用 structure 数组中的英文方括号段落标签，且每个 structure section 都要在 lyric_prompt 中出现一次：如 [Verse 1]、[Verse 2]、[Pre-Chorus]、[Chorus]、[Bridge]、[Final Chorus]、[Outro]。
2. 禁止中文段落标签，禁止输出 主歌/副歌/预副歌/桥段/尾声，禁止输出 （主歌1-男声）、（副歌-合唱）、（最终副歌-合唱升调） 这类括号标题。
3. 男女对唱声部必须写进英文方括号 meta tag，示例：
[Verse 1 | male vocal]
行李箱轮子碾过候机厅的光
[Verse 2 | female vocal]
你低头看机票我假装看航班
[Chorus | duet harmony]
等某天等某个机场再相见。
4. 禁止在正文行写中文声部前缀，例如“男冒号、女冒号、合冒号”；这些文字可能被 Suno 当成歌词唱出来，服务端最终也会拦截。
5. 音效和环境声不能写成中文圆括号正文，例如“（飞机划过天际的轰鸣声渐远）”。如确实需要音效，使用英文方括号 meta tag：
[Instrumental Outro | distant airplane flyover | airport ambience | engine rumble fades out]
[Fade Out]，并在 style_prompt 中加入对应英文 sound design。
6. structure 字段必须与推荐结构使用同一套英文 section 名称；不要把 structure 写成中文。
非歌词说明行格式硬性要求：
1. 歌词正文只能写会被唱出来的歌词；不要把制作说明、表演说明、镜头说明或结构说明裸露成正文行。
2. 演唱/人声动作、制作/编曲动作、音效/环境声、舞台/镜头/情绪说明、结构说明，必须改写成英文方括号 meta tag。
3. 禁止裸露中文说明行，例如：哼唱渐远、和声渐弱、人声淡出、钢琴淡出、弦乐铺底、雨声渐远、风声响起、画面拉远、灯光熄灭、重复副歌、进入桥段。
4. [Instrumental Outro] 后面禁止出现普通正文行；如果需要器乐/音效/人声动作，写在同一个英文 meta tag 中。
5. 合法示例：
[Outro | soft humming fades out]
[Instrumental Outro | piano fades out]
[Instrumental Outro | rain ambience fades out]
[Visual Direction | camera pulls away]
[Arrangement | repeat chorus]
