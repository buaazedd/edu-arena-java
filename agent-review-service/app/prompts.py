from __future__ import annotations

from typing import Dict, List

from app.models import DimensionName


BASE_RUBRIC = {
    "theme": "主旨是否紧扣题意、中心是否明确。",
    "imagination": "想象是否丰富且合理，是否有新意。",
    "logic": "结构是否完整、论述是否连贯。",
    "language": "语言表达是否准确、流畅、得体。",
    "writing": "书写规范与格式（若仅文本输入则弱化该维）。",
}


DIMENSION_JSON_SCHEMA = (
    '{"winner":"A|B|tie","scoreA":0-10,"scoreB":0-10,'
    '"confidence":0-1,"reason":"...","evidenceA":["..."],"evidenceB":["..."]}'
)

AGGREGATE_JSON_SCHEMA = (
    '{"winner":"A|B|tie","confidence":0-1,"needsHuman":true,'
    '"summary":"...","panelConsensus":"high|medium|low"}'
)


def _format_retrieval_context(ctx: Dict) -> str:
    exemplars = "\n".join([f"- {x['text']}" for x in ctx.get("exemplars", [])])
    gold_cases = "\n".join([f"- {x['text']}" for x in ctx.get("gold_cases", [])])
    risks = "\n".join([f"- {x['text']}" for x in ctx.get("risk_patterns", [])])
    return (
        "【检索参考-范文片段】\n" + (exemplars or "- 无") + "\n\n"
        "【检索参考-历史高一致判例】\n" + (gold_cases or "- 无") + "\n\n"
        "【检索参考-常见风险模式】\n" + (risks or "- 无")
    )


def build_dimension_system_prompt(dimension: DimensionName, model_id: str) -> str:
    return (
        f"你是作文对战评审团成员之一，当前评委模型为 {model_id}。"
        f"你只负责维度 {dimension} 的评审。"
        "你必须只输出合法 JSON，不要输出 markdown、解释或额外文字。"
        f"输出格式必须严格为: {DIMENSION_JSON_SCHEMA}"
    )


def build_dimension_prompt(
    dimension: DimensionName,
    essay: str,
    output_a: str,
    output_b: str,
    retrieval_ctx: Dict,
    model_id: str,
) -> str:
    rubric = BASE_RUBRIC[dimension]
    retrieved = _format_retrieval_context(retrieval_ctx)
    return (
        "你是中学作文对战评审员。\n"
        f"当前评审团成员: {model_id}\n"
        f"维度: {dimension}\n"
        f"评分标准: {rubric}\n"
        "请比较 A 与 B 两份批改输出的质量，给出该维度的胜者、分数、置信度和证据。\n"
        "必须基于证据，不得空泛。检索内容仅作参考，最终必须回到 A/B 文本证据。\n"
        "若两者相近可判 tie，但 reason 必须说明原因。\n\n"
        f"{retrieved}\n\n"
        f"作文原文: {essay}\n\n"
        f"A输出: {output_a}\n\n"
        f"B输出: {output_b}"
    )


def build_aggregate_system_prompt(model_id: str) -> str:
    return (
        f"你是最终汇总裁决模型，当前模型为 {model_id}。"
        "你需要综合三个评审团成员在五个维度上的结果，只输出合法 JSON。"
        f"输出格式必须严格为: {AGGREGATE_JSON_SCHEMA}"
    )


def build_aggregate_prompt(results: List[dict], dimension_summaries: List[dict]) -> str:
    return (
        "你是终裁 Agent。请综合三位评审团成员在五个维度上的评审结果，输出最终汇总结论。\n"
        "如果五个维度整体分歧明显，或多数维度仅弱一致，则 needsHuman=true。\n"
        "优先参考各维度多数票，其次参考置信度和分差。\n\n"
        f"维度汇总: {dimension_summaries}\n\n"
        f"全部评审团原始结果: {results}"
    )
