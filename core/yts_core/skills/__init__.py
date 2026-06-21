"""自定义 skill 注册。自定义 skill 仅在 local profile(桌面)启用;
云端因多租户安全/审核/App Store 风险只允许内置 skill。
"""
from .registry import SkillRegistry, builtin_registry

__all__ = ["SkillRegistry", "builtin_registry"]
