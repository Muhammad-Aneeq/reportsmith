"""Settings. Everything env-overridable, everything with a working default.

The defaults are chosen so that a fresh clone runs the full product — assemble,
narrate, review, sign, archive — with **no API key and no configuration**. The LLM is
mocked unless `REPORTSMITH_LLM=live` is set explicitly (spec 13 §8; the brief's
"LLM mocked by default, live behind a marker").
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Both paths, repo root first. `env_file=".env"` alone resolves against the *current
    # working directory*, and `make dev` starts uvicorn from `backend/` — so the root `.env`
    # that `.env.example` tells you to create was silently never read, and the app stayed in
    # mock mode while insisting it had been configured. Listing both means it works whether
    # you run from the repo root or from `backend/`.
    model_config = SettingsConfigDict(
        env_prefix="REPORTSMITH_",
        env_file=(REPO_ROOT / ".env", ".env"),
        extra="ignore",
    )

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


def _export_provider_keys() -> None:
    """Put provider keys from the repo-root `.env` into the real environment.

    `Settings` has an ``env_prefix`` of ``REPORTSMITH_``, so it never sees ``OPENAI_API_KEY``
    — and the OpenAI SDK reads that variable from ``os.environ`` directly, not from any
    settings object. Without this bridge, a key written into `.env` exactly as
    `.env.example` instructs is loaded by nobody and the live path fails with an
    authentication error that points at the user rather than at the wiring.

    Never overwrites an already-exported variable: a key set in the shell for one command
    should win over a file, which is how every other tool behaves.
    """
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name, value = name.strip(), value.strip().strip("\"'")
        if name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY") and value and name not in os.environ:
            os.environ[name] = value


_export_provider_keys()
settings = Settings()
