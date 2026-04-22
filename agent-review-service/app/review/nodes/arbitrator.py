"""仲裁节点：综合 6 维度评分，生成最终结论。"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from app.common.logger import logger
from app.contracts.review_models import ArbitrationResult, DimensionKey, DimensionScore
from app.settings import get_settings

from ..llm import get_llm
from ..prompts import ARBITRATOR_SYSTEM, arbitrator_user


def _index_by_dim(scores: List[DimensionScore]) -> Dict[DimensionKey, DimensionScore]:
    return {s.dim: s for s in scores}


def _heuristic_final(dims: Dict[DimensionKey, DimensionScore]) -> tuple[str, float]:
    """启发式：以 OVERALL 为准，综合其他维度 confidence 平均作为总置信度。"""
    overall = dims.get(DimensionKey.OVERALL)
    final = overall.winner if overall else "tie"
    confs = [d.confidence for d in dims.values()]
    avg_conf = sum(confs) / len(confs) if confs else 0.5
    return final, round(avg_conf, 3)


async def arbitrator_node(state) -> Dict[str, Any]:
    scores: List[DimensionScore] = state.get("dimension_scores") or []
    if len(scores) < 6:
        logger.warning(f"[arbitrator] 收到维度评分不足 6 个: got {len(scores)}")

    dim_map = _index_by_dim(scores)
    h_final, h_conf = _heuristic_final(dim_map)

    # 若 OVERALL 置信度偏低，调用 LLM 仲裁复核；否则直接采信
    overall = dim_map.get(DimensionKey.OVERALL)
    needs_llm = (overall is None) or (overall.confidence < 0.6)

    arbitration: ArbitrationResult
    if not needs_llm:
        arbitration = ArbitrationResult(
            final_winner=h_final,  # type: ignore[arg-type]
            overall_confidence=h_conf,
            rationale="启发式：OVERALL 维度置信度充足，直接采信。",
            adjusted_dimensions=[],
        )
    else:
        llm = get_llm()
        s = get_settings()
        payload_json = json.dumps(
            [sc.model_dump() for sc in scores], ensure_ascii=False, indent=2
        )
        try:
            data = await llm.achat_json(
                system=ARBITRATOR_SYSTEM,
                user=arbitrator_user(payload_json),
                model=s.ai_arbitrator_model,
                temperature=0.1,
            )
            # 强约束：final_winner 必须与 OVERALL 维度一致
            overall_winner = (overall.winner if overall else "tie")
            final_winner = str(data.get("final_winner", overall_winner))
            if final_winner != overall_winner:
                logger.warning(
                    f"[arbitrator] LLM 给出 final_winner={final_winner} 但 OVERALL={overall_winner}，强制回退到 OVERALL。"
                )
                final_winner = overall_winner
            adj_raw = data.get("adjusted_dimensions") or []
            adjusted: List[DimensionScore] = []
            for item in adj_raw:
                try:
                    adjusted.append(DimensionScore.model_validate(item))
                except Exception as e:
                    logger.warning(f"[arbitrator] 解析 adjusted_dimensions 失败: {e}")
            arbitration = ArbitrationResult(
                final_winner=final_winner,  # type: ignore[arg-type]
                overall_confidence=float(data.get("overall_confidence", h_conf)),
                rationale=str(data.get("rationale", ""))[:400],
                adjusted_dimensions=adjusted,
            )
        except Exception as e:
            logger.warning(f"[arbitrator] LLM 仲裁失败，走启发式: {e}")
            arbitration = ArbitrationResult(
                final_winner=h_final,  # type: ignore[arg-type]
                overall_confidence=h_conf,
                rationale=f"LLM 仲裁失败，使用启发式。原因: {e}",
                adjusted_dimensions=[],
            )

    logger.info(
        f"[arbitrator] final={arbitration.final_winner} conf={arbitration.overall_confidence}"
    )
    return {"arbitration": arbitration}
