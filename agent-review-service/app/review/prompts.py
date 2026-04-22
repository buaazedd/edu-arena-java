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
