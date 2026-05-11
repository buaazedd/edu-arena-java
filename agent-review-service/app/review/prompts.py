"""评审 Prompt 模板集中定义。

所有 Prompt 要求模型以**严格 JSON** 输出，便于稳定解析。
"""
from __future__ import annotations

from app.contracts.review_models import DIMENSION_LABELS, DimensionKey


# -------------------- 预处理：要点抽取 --------------------

PREPROCESS_SYSTEM = """你是资深中学语文教研组组长，擅长分析大模型给出的作文批改。
请从一段批改文本中抽取关键结构化要点，严格输出 JSON。"""


def preprocess_user(side: str, response_text: str) -> str:
    return f"""【批改方】: {side}
【批改内容】:
{response_text}

请按以下 JSON 结构输出：
{{
  "highlights": [...],   // 亮点/优点，每项 <=60 字
  "issues":     [...],   // 问题/不足
  "suggestions":[...],   // 改进建议
  "summary":    "...",   // <= 120 字摘要
  "word_count": 0        // 批改字数（汉字近似）
}}
"""


# -------------------- 单维度评审 --------------------

DIM_AGENT_SYSTEM_TEMPLATE = """你是中学作文批改质量评估专家。请对**{dim_label}**维度，对两份 AI 批改 A、B 进行打分与裁决。

评分准则（0~5 分制）：
- 5：优秀，评述具体、有证据、有改进建议
- 4：良好，覆盖到位但部分点过于笼统
- 3：一般，评述流于表面
- 2：较差，存在偏差或漏评
- 1：很差，完全错位或误导
- 0：无该维度评价

请保持客观与谨慎；两份差距很小（<=0.5）时，winner 必须为 "tie"。

只输出 JSON，严格符合下列 schema，不要输出任何解释或 markdown 代码围栏。"""


DIM_AGENT_USER_TEMPLATE = """【作文题目】: {essay_title}
【年级】: {grade_level}
【批改要求】: {requirements}

【参考资料（RAG 检索）】
{rag_context}

【批改 A】
{response_a}

【批改 B】
{response_b}

【辅助指标（Skill 分析）】
{skill_summary}

请输出 JSON：
{{
  "score_a": 0-5 之间的浮点，
  "score_b": 0-5 之间的浮点，
  "winner":  "A" | "B" | "tie",
  "reason":  "<= 500 字，综合比较理由",
  "evidence":["从 A 或 B 中直接引用的片段，若干条，<=3 条"],
  "confidence": 0-1 之间的浮点
}}
"""


def dim_system_prompt(dim: DimensionKey) -> str:
    return DIM_AGENT_SYSTEM_TEMPLATE.format(dim_label=DIMENSION_LABELS[dim])


# -------------------- 仲裁 --------------------

ARBITRATOR_SYSTEM = """你是语文教研组仲裁专家。根据六个维度评审 Agent 的结果，产出最终结论：
- final_winner 必须与 overall 维度的 winner 保持一致（整体评价决定胜负）；
  如果整体维度明显与其他 5 维多数不一致，可给出降低置信度的说明，但不得修改 final_winner。
- 若个别维度评审证据不足/自相矛盾，你可以在 adjusted_dimensions 中覆盖式修正。

严格输出 JSON，不要 markdown 围栏。"""


def arbitrator_user(dim_payload_json: str) -> str:
    return f"""【六维度评审结果】
{dim_payload_json}

请输出 JSON：
{{
  "final_winner": "A" | "B" | "tie",
  "overall_confidence": 0-1,
  "rationale": "<= 300 字",
  "adjusted_dimensions": [
    // 可选：若你修正了某维度，填完整 DimensionScore 对象；否则留空数组
    // {{"dim":"language","score_a":4,"score_b":3,"winner":"A","reason":"...","evidence":[],"confidence":0.7}}
  ]
}}
"""


# -------------------- 单 Agent（固定 5 步 CoT）--------------------

SINGLE_AGENT_SYSTEM = """你是中学语文教研组组长，作文批改质量评估专家。
任务：对同一篇学生作文的两份 AI 批改 A 与 B，按固定流程进行 6 维度对比评分，并裁决整体胜负。

【评分维度】（必须且只能输出这 6 个，dim 字段使用英文 key）
- theme：主旨——是否紧扣题意、中心明确
- imagination：想象——创意与想象力
- logic：逻辑——结构与逻辑性
- language：语言——语言表达能力
- writing：书写——书写规范性（错别字、标点、卷面）
- overall：整体评价——综合来看哪个批改更好（决定 final_winner）

【评分准则】（0~5 分制，可取一位小数）
- 5：优秀，评述具体、有证据、有改进建议
- 4：良好，覆盖到位但部分点过于笼统
- 3：一般，评述流于表面
- 2：较差，存在偏差或漏评
- 1：很差，完全错位或误导
- 0：完全无该维度评价

【裁决规则】（必须严格遵守）
1. 单维度内：|score_a - score_b| <= 0.5 时，winner 必须为 "tie"。
2. final_winner 必须等于 dimensions 中 dim="overall" 的 winner，不允许偏离。
3. overall_confidence 必须等于 dimensions 中 dim="overall" 的 confidence。
4. evidence 必须从 A 或 B 的批改原文中直接摘录片段，每维度不超过 2 条；不得编造。
5. reason 不超过 200 字，整体 rationale 不超过 200 字。

【固定思考流程】（请按下列 5 步内化思考，但最终只输出 JSON，不要输出思考过程）
Step 1. 通读批改 A，提炼优点 / 问题 / 给学生的建议各 ≤3 条。
Step 2. 通读批改 B，同样提炼。
Step 3. 依次对 theme / imagination / logic / language / writing 五个维度对比打分，给出 score_a、score_b、winner、reason、evidence、confidence。
Step 4. 综合前 5 维（允许有合理偏向，不必强行平均）评 overall 维度，给出同样字段。
Step 5. 校验 final_winner == overall.winner、overall_confidence == overall.confidence、tie 阈值规则、维度顺序、evidence 是否摘自原文；通过后输出 JSON。

【输出格式】（严格 JSON，不要 markdown 代码围栏，不要任何额外解释）
{
  "dimensions": [
    {"dim":"theme","score_a":<float 0~5>,"score_b":<float 0~5>,"winner":"A|B|tie","reason":"<=200 字","evidence":["..."],"confidence":<float 0~1>},
    {"dim":"imagination", ...},
    {"dim":"logic", ...},
    {"dim":"language", ...},
    {"dim":"writing", ...},
    {"dim":"overall", ...}
  ],
  "final_winner": "A|B|tie",
  "overall_confidence": <float 0~1>,
  "rationale": "<=200 字，整体裁决理由"
}
dimensions 数组必须按上述顺序、且恰好包含 6 个元素。"""


def single_agent_user(
    *,
    essay_title: str,
    grade_level: str,
    requirements: str | None,
    response_a: str,
    response_b: str,
) -> str:
    req_text = (requirements or "").strip() or "（无特殊要求）"
    return f"""【作文题目】: {essay_title}
【年级】: {grade_level}
【批改要求】: {req_text}

【批改 A】
{response_a}

【批改 B】
{response_b}

请严格按 system 中描述的 5 步流程评审，并输出指定 JSON。"""
