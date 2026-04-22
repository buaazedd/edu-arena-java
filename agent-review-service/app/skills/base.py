"""Skill 抽象基类与单例注册表。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Generic, List, Optional, Type, TypeVar

from pydantic import BaseModel

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


class BaseSkill(ABC, Generic[InputT, OutputT]):
    """所有 Skill 的抽象基类。

    子类需声明：
    - `name`  : 全局唯一名
    - `desc`  : 面向 Agent 的能力描述
    - `InputModel`  / `OutputModel` : Pydantic 输入输出模型
    - `run(inp)`    : 纯函数实现
    """

    name: str = ""
    desc: str = ""
    InputModel: Type[BaseModel] = BaseModel
    OutputModel: Type[BaseModel] = BaseModel

    @abstractmethod
    def run(self, inp: InputT) -> OutputT:  # pragma: no cover
        ...

    def schema(self) -> dict:
        return {
            "name": self.name,
            "desc": self.desc,
            "input_schema": self.InputModel.model_json_schema(),
            "output_schema": self.OutputModel.model_json_schema(),
        }


class SkillRegistry:
    """全局 Skill 注册表（单例）。"""

    def __init__(self) -> None:
        self._skills: Dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        if not skill.name:
            raise ValueError("Skill must define 'name'")
        if skill.name in self._skills:
            raise ValueError(f"duplicate skill: {skill.name}")
        self._skills[skill.name] = skill

    def get(self, name: str) -> BaseSkill:
        if name not in self._skills:
            raise KeyError(f"skill not found: {name}")
        return self._skills[name]

    def list(self) -> List[str]:
        return sorted(self._skills.keys())

    def describe_all(self) -> List[dict]:
        return [self._skills[n].schema() for n in self.list()]


# 全局单例（由 app.skills 包顶层统一注册）
registry = SkillRegistry()


__all__ = ["BaseSkill", "SkillRegistry", "registry"]
