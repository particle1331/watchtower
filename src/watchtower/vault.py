"""Secrets vault backed by the OS keyring.

Actual secret values live in the OS keychain (service: "watchtower").
A gitignored index at `.watchtower/vault_keys.json` tracks which keys are
stored — no values ever touch disk.

Projects read secrets via `watchtower.vault.get_secret`.
"""

from __future__ import annotations

import json
from pathlib import Path

import keyring

SERVICE = "watchtower"
VAULT_DIR = Path(".watchtower")
KEYS_FILE = VAULT_DIR / "vault_keys.json"


def _load_keys() -> set[str]:
    if not KEYS_FILE.exists():
        return set()
    return set(json.loads(KEYS_FILE.read_text()))


def _save_keys(keys: set[str]) -> None:
    VAULT_DIR.mkdir(exist_ok=True)
    KEYS_FILE.write_text(json.dumps(sorted(keys), indent=2))


def set_secret(key: str, value: str) -> None:
    keyring.set_password(SERVICE, key, value)
    keys = _load_keys()
    keys.add(key)
    _save_keys(keys)


def get_secret(key: str) -> str | None:
    return keyring.get_password(SERVICE, key)


def list_keys() -> list[str]:
    return sorted(_load_keys())


def all_secrets() -> dict[str, str]:
    return {k: v for k in list_keys() if (v := get_secret(k)) is not None}