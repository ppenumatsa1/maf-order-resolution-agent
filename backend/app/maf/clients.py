from __future__ import annotations

import os


def has_llm_configuration() -> bool:
    return any(
        os.getenv(name)
        for name in (
            "OPENAI_API_KEY",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_API_KEY",
            "FOUNDRY_PROJECT_ENDPOINT",
        )
    )
