from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Skill:
    id: str
    builtin: bool = True
    handler: Callable | None = None  # TODO: skill 执行约定


@dataclass
class SkillRegistry:
    allow_custom: bool = False  # 仅 local 置 True
    _skills: dict[str, Skill] = field(default_factory=dict)

    def register_builtin(self, skill: Skill) -> None:
        skill.builtin = True
        self._skills[skill.id] = skill

    def register_custom(self, skill: Skill) -> None:
        if not self.allow_custom:
            raise PermissionError("custom skills are local-only (云端禁用,见 wiki Arch-V3-1)")
        skill.builtin = False
        self._skills[skill.id] = skill

    def get(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)


builtin_registry = SkillRegistry(allow_custom=False)
