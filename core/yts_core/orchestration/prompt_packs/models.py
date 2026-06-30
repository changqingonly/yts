from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class PromptPack:
    pack_id: str
    version: str
    contract_version: str
    sha256: str
    system_template: str
    stage_system_templates: Mapping[str, str]
    stage_templates: Mapping[str, str]

    def to_state(self) -> dict[str, str]:
        return {
            "pack_id": self.pack_id,
            "version": self.version,
            "contract_version": self.contract_version,
            "sha256": self.sha256,
        }
