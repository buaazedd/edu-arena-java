from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.config import settings


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
            return json.loads(text)
        except Exception:
            return fallback
