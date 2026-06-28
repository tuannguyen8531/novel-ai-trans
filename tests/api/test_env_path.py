"""Verify the settings persist endpoint writes to the project root, not a stray src/.env."""

from __future__ import annotations

from pathlib import Path

from src.api.routes.system import DEFAULT_ENV_PATH


def test_default_env_path_is_project_root():
    project_root = Path(__file__).resolve().parents[2]
    expected = project_root / ".env"
    # The API must point at the project-root .env, never at e.g. src/.env.
    assert expected == DEFAULT_ENV_PATH
    assert "src" not in DEFAULT_ENV_PATH.parts, (
        f"DEFAULT_ENV_PATH ({DEFAULT_ENV_PATH}) is under src/; the API would create a new src/.env file when persisting settings."
    )
