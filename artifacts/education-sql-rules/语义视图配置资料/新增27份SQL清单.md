# 新增27份SQL草案清单

原有16份保留，V17–V43已补齐。下面的假设已经写进SQL开头注释、配置卡和表单数据。业务仍需确认，未修改Studio或执行真实业务库查询。

| 编号 | 业务视图 | SQL文件 | 草案假设 |
|---|---|---|---|
| V17 | 学校三门四门六门总均分<br>`v_school_exam_total_summary` | [打开SQL](./SQL草案/V17_v_school_exam_total_summary.sql) | 不默认合并在籍和市报，student_status作为输出分组<br>总分非空且包括真实0分<br>三门总均分不除以3，六门直接读zf6m |
| V18 | 再选科赋分等级分布<br>`v_assigned_grade_distribution` | [打开SQL](./SQL草案/V18_v_assigned_grade_distribution.sql) | 按xkkm明确选科者为分母，已选科真实0不排除<br>缺等级单列未分档，不重新赋分<br>student_status独立分组；未知选科不猜测 |
| V19 | 总分十分段及累计人数<br>`v_total_ten_point_band` | [打开SQL](./SQL草案/V19_v_total_ten_point_band.sql) | 小数先FLOOR再按1–10、11–20分箱<br>真实0分单独0–0段，负分不参与<br>区县×校类×学生性质保留为独立切片；不把各切片累计率相加 |
| V20 | 学科五分段及累计人数<br>`v_subject_five_point_band` | [打开SQL](./SQL草案/V20_v_subject_five_point_band.sql) | 化生政地使用转换分，其他使用原始分<br>xkkm确认选科，真实0单独成段；缺分不补0<br>小数先FLOOR，学生性质分开统计 |
| V21 | 学校各科全市排名与强弱<br>`v_school_subject_city_rank` | [打开SQL](./SQL草案/V21_v_school_subject_city_rank.sql) | 仅在籍生，保留已选科真实0分<br>各科独立全市学校池、不设最低学校样本门槛；RANK按未舍入均分<br>化生政地转换分；前25%优势/后50%薄弱为旧默认；目标校在外层筛选 |
| V22 | 班级单科全市排名<br>`v_class_subject_city_rank` | [打开SQL](./SQL草案/V22_v_class_subject_city_rank.sql) | 在籍、排除其他及未知校类，整班>=10、该科>=3<br>化生政地转换分，已选科0分保留<br>视图保留全市池；目标校、班级和名次窗口在查询外层筛选 |
| V23 | 班级六门双口径排名<br>`v_class_total_city_rank` | [打开SQL](./SQL草案/V23_v_class_total_city_rank.sql) | 整班>=10，在籍、排除其他及未知校类，方向内有效总分>=3<br>同时输出全部方向和所有合格方向，is_majority_track标多数；并列多数均保留<br>默认展示all或is_majority_track=1；排名先在完整方向池完成 |
| V24 | 位次前N分数阈值及人数<br>`v_top_n_score_bucket` | [打开SQL](./SQL草案/V24_v_top_n_score_bucket.sql) | 在籍、总分非空且保留0<br>按第N个排序位置分数切线，所有同分均纳入<br>N大于池人数时取全体最低分作为切线，并返回pool_count |
| V25 | 班级和组合达线<br>`v_class_combo_line_reach` | [打开SQL](./SQL草案/V25_v_class_combo_line_reach.sql) | 有效六门总分作分母，NULL总分只进recorded_count不进candidate_count<br>所有实际组合保留，包括历史组合；六种物理组合可在外层筛<br>学生性质单独分组；每批次预测线必须唯一 |
| V26 | 线上线下分数带学生<br>`v_student_cutoff_distance` | [打开SQL](./SQL草案/V26_v_student_cutoff_distance.sql) | 仅输出非空总分，真实0保留<br>distance=总分−分数线；线上/线下N的开闭区间留查询层<br>每个学生每条线一行，跨线求人数需要按学生去重 |
| V27 | 达线较上场变化<br>`v_line_reach_change` | [打开SQL](./SQL草案/V27_v_line_reach_change.sql) | 前场按同届+考试类型+归属学校内时间排序，相同日期按ID稳定排序<br>某校没参加该前场时留NULL，不自动跳到更早一次<br>缺届次/日期不比较；阈值变化返回提示 |
| V28 | 切线学生各科贡献分<br>`v_cutoff_subject_contribution` | [打开SQL](./SQL草案/V28_v_cutoff_subject_contribution.sql) | 现算贡献分，不读取可能过期的tb_score_contribution<br>在籍、按方向、所有有效线种；无恰好切线者取末位达线一人，同分按学生ID/记录ID稳定选择<br>化生政地转换分，真实已选科0保留；样本数独立返回 |
| V29 | 题型平均得分率<br>`v_question_type_mean_rate` | [打开SQL](./SQL草案/V29_v_question_type_mean_rate.sql) | 同时输出每题等权平均与分值/观测人数加权的两种得分率<br>仅已记录非空题成绩，缺行不补零；满分非正排除<br>不同班级独立输出，合并时回到底表重算 |
| V30 | 题目区分度与难度曲线<br>`v_item_discrimination_curve` | [打开SQL](./SQL草案/V30_v_item_discrimination_curve.sql) | 以有非空科目成绩的学生×本卷全部题目为底，缺小题行/NULL暂按0，须业务确认<br>高低27%按整科成绩顺序切组，同分按学生ID稳定；至少4人算区分度<br>discrimination以题满分为分母，legacy_discrimination同时保留旧个人总分分母；不可混称 |
| V31 | 能力层级知识点画像<br>`v_ability_knowledge_profile` | [打开SQL](./SQL草案/V31_v_ability_knowledge_profile.sql) | 班级内独立汇总；等权知识点平均与分值加权能力率分开输出<br>知识掌握按V16成对非空记录口径，缺行不补零<br>薄弱60为源码默认，unknown层级保留 |
| V32 | 后十名与中位组知识点差距<br>`v_knowledge_cohort_gap` | [打开SQL](./SQL草案/V32_v_knowledge_cohort_gap.sql) | 每份试卷同校同班排序，真实0保留，后10和中位名次±2<br>顺序分组不扩同分；允许小班重叠并输出overlap_count<br>仅已有非空小题记录成对计算，不对缺行补0 |
| V33 | 同校班际薄弱学科<br>`v_class_peer_weak_subject` | [打开SQL](./SQL草案/V33_v_class_peer_weak_subject.sql) | 同校同年级同科、每班>=3个非空成绩；未识别年级不混排<br>对照各班均分等权且含本班；DENSE_RANK<br>逐卷满分60%及格、85%优秀，真实0保留；5分/后30%/后3名为待确认默认 |
| V34 | 群体特征与干预优先级<br>`v_group_intervention_profile` | [打开SQL](./SQL草案/V34_v_group_intervention_profile.sql) | 同校同年级科目，基准为学生加权；班级>=3<br>分数差只和分数标准差比，率差用百分点阈值，修正旧单位混比<br>±3分、1.15倍、落后5分/5pp、60%和优先级加权为待确认默认；小题仅已有非空记录 |
| V35 | 教研整体、分卷和拖后腿小题<br>`v_subject_research_comparison` | [打开SQL](./SQL草案/V35_v_subject_research_comparison.sql) | 仅在籍，排市报学校；OV学生批次键唯一是前提<br>校区按学校名前字母+两数字编码合并，无编码用school_id；混合校类需先修复<br>row_type分overall/section/item；原始整卷均分、分卷、小题在不同粒度，禁止混合SUM<br>有整科成绩的学生×试卷题目作底，缺小题暂补0；卷1/2题型沿用旧前缀，拖后腿2/3名门槛 |
| V36 | 尖子生与压线薄弱学生<br>`v_research_focus_students` | [打开SQL](./SQL草案/V36_v_research_focus_students.sql) | 只输出匿名学生ID，三类名单独立list_type，跨名单不能直接相加人数<br>尖子生仅引领校、物理前100/历史前30含并列；尖子班按实际名单<br>压线保留旧科目特殊比较J12，但改用选科标识保留真实0，必须逐项确认<br>同一学生命中多条关注线时均保留线种，不沿用旧首条break；这是一项明确草案差异 |
| V37 | 学生历次成绩及进退步<br>`v_student_score_trend` | [打开SQL](./SQL草案/V37_v_student_score_trend.sql) | 按同届+考试类型+归属学校的全局相邻批次，不按学生缺考后任意回溯<br>同一学生同科且满分相同才算原始分差；缺分、缺满分或跨满分留NULL并输出状态<br>只实现原始科目趋势，不冒充六门总分趋势；另给得分率差作为不同量纲<br>±5为本草案稳定带，学生±3/班均±0.5须作为其他指标另行定义 |
| V38 | 水平分层、偏科与相关性<br>`v_student_multisubject_profile` | [打开SQL](./SQL草案/V38_v_student_multisubject_profile.sql) | performance_band按单科实际满分判ABCD，不猜六门总满分<br>偏科度按同班各科顺序名次总体标准差，至少两科；不同选科参与集合影响解释<br>原始分差>=20且有不及格科只作legacy证据；不同满分不宣称已标准化<br>Pearson使用同学生成对非空记录；样本不足/零方差为NULL，不将相关性当因果 |
| V39 | 临界生与退步预警证据<br>`v_student_risk_evidence` | [打开SQL](./SQL草案/V39_v_student_risk_evidence.sql) | 临界[及格线−5,及格线+5)，退步<=−10，分差型偏科>=20为草案默认<br>仅同满分可比前后成绩触发退步，不补缺考<br>偏科事件按科目逐行输出，统计偏科学生须DISTINCT student_id<br>版本字段显式为draft，不读取原系统运行配置；通知/确认/连续次数仍由应用实现 |
| V40 | 优秀良好低分率与互斥水平分层<br>`v_subject_performance_rates` | [打开SQL](./SQL草案/V40_v_subject_performance_rates.sql) | 85%优秀、70%良好、40%低分为源码默认，含等于优秀/良好、不含等于低分边界<br>每学校科目一行：优秀良好为累计率，ABCD互斥档通过a_count/b_count/c_count/d_count另列，不按档分组改变率分母<br>真实0保留，缺成绩/缺满分为unclassified，不把缺分当D |
| V41 | 学校类别达线比较<br>`v_tier_line_reach` | [打开SQL](./SQL草案/V41_v_tier_line_reach.sql) | 精确按COALESCE(s_name,name)匹配，名称不唯一不任取一所学校<br>匹配失败/歧义保留独立mapping_status，不丢候选人数、不扩行<br>使用当前学校类别，历史类别需后续快照维度；各线种独立汇总 |
| V42 | 绝对薄弱与相对薄弱知识点清单<br>`v_weak_knowledge_evidence` | [打开SQL](./SQL草案/V42_v_weak_knowledge_evidence.sql) | 弱知识点60%、相对回退软上限75为旧默认<br>有绝对薄弱只列绝对薄弱；没有时列<75的相对项，TopN放查询层<br>未关联知识点不编造正式知识点名，主视图V16仍保留该组；按知识点ID稳定排序 |
| V43 | 班级总览同校年级指标排名<br>`v_class_local_metric_rank` | [打开SQL](./SQL草案/V43_v_class_local_metric_rank.sql) | 均分/及格率/优秀率独立顺序编号，同分用班名稳定排序，不冒充RANK并列<br>对照为各班指标等权且含本班，至少2班才给名次；年级不识别不混排<br>优秀85%是待确认草案默认，及格60%、真实0保留 |

## 使用说明

在原始tb_*草稿中新增语义视图：名称和业务说明从配置卡复制，SQL文件完整粘贴到只读语义SQL。各文件只有独立SELECT/CTE，不需要先建立其他新增视图。

43条视图的views数组片段不是完整MDL文件，不能直接作为完整模型导入。

## 验证范围

- 全部43份：当前Wren对PostgreSQL、DuckDB目标规划通过，虚构数据执行通过。
- 新增27份：另用两学校、两班、每班12人、两场同届考试及多种异常样本进行非空执行与边界检查。
- 检查了赋分缺档、0分分段、参赛班数、多口径排名、前场选择、切线样本、分组重叠、混合满分、相关性零方差、学校名称歧义等。
- PostgreSQL真实数据库执行、运行时配置同步及实际数据对账仍待业务验收。
- 全部43视图放在同一离线MDL中，原生Wren整包验证通过。
