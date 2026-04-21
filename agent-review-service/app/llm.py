from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.config import settings


logger = logging.getLogger(__name__)


_JSON_CODEBLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL)


@dataclass
class LLMService:
    model: ChatOpenAI
    model_id: str

    @classmethod
    def create(cls, model_name: str | None = None) -> "LLMService":
        target_model = model_name or settings.llm_model
        model = ChatOpenAI(
            model=target_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            temperature=0,
        )
        return cls(model=model, model_id=target_model)

    def invoke_json(self, prompt: str, fallback: Dict[str, Any], system_prompt: str) -> Dict[str, Any]:
        template = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", "{prompt}"),
        ])
        chain = template | self.model
        try:
            resp = chain.invoke({"prompt": prompt})
            text = resp.content if hasattr(resp, "content") else str(resp)
            if isinstance(text, list):
                text = "".join(
                    item.get("text", str(item)) if isinstance(item, dict) else str(item)
                    for item in text
                )

            text = text.strip()
            logger.info("LLM raw response: model=%s chars=%s snippet=%s", self.model_id, len(text), text[:800])

            parsed = self._parse_json(text)
            if parsed is None:
                raise ValueError("model output is not valid JSON after normalization")
            return parsed
        except Exception as ex:
            logger.exception("LLM invoke_json fallback: model=%s err=%s", self.model_id, ex)
            return fallback

    @staticmethod
    def _parse_json(text: str) -> Dict[str, Any] | None:
        if not text:
            return None

        candidates: list[str] = []

        # 1) 原始文本直接尝试
        candidates.append(text)

        # 2) 提取 ```json ... ``` 代码块
        for m in _JSON_CODEBLOCK_RE.finditer(text):
            candidates.append(m.group(1).strip())

        # 3) 尝试截取第一个 { 到最后一个 }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidates.append(text[start:end + 1].strip())

        # 4) 去掉常见前后缀说明
        cleaned = text
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()
        candidates.append(cleaned)

        seen: set[str] = set()
        for cand in candidates:
            cand = cand.strip()
            if not cand or cand in seen:
                continue
            seen.add(cand)
            try:
                obj = json.loads(cand)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                continue
        return None

