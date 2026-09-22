"""Settings. Everything env-overridable, everything with a working default.

The defaults are chosen so that a fresh clone runs the full product — assemble,
narrate, review, sign, archive — with **no API key and no configuration**. The LLM is
mocked unless `REPORTSMITH_LLM=live` is set explicitly (spec 13 §8; the brief's
"LLM mocked by default, live behind a marker").
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REPORTSMITH_", env_file=".env", extra="ignore")

    database_url: str = f"sqlite:///{REPO_ROOT / 'backend' / 'reportsmith.db'}"

    # "mock" | "live". Mock is deterministic and free; live needs OPENAI_API_KEY.
    llm: str = "mock"
    model: str = "gpt-4o-mini"
    temperature: float = 0.3

    # Where issued packs land. Append-only by construction (app/issue/archive.py).
    archive_dir: Path = REPO_ROOT / "archive"
    fixtures_dir: Path = REPO_ROOT / "fixtures"

    # The generated world the adapters read.
    profile: str = "squeeze"
    seed: int = 42

    signer_name: str = "A. Controller"

    @property
    def live_llm(self) -> bool:
        return self.llm.lower() == "live"


settings = Settings()
