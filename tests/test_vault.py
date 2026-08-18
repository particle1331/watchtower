"""Tests for the OS-keyring-backed secrets vault."""

import json
from unittest.mock import Mock

import keyring.errors
from typer.testing import CliRunner

from watchtower import cli, vault

runner = CliRunner()


def test_delete_secret_removes_keyring_secret_and_index(tmp_path, monkeypatch):
    keys_file = tmp_path / "vault_keys.json"
    keys_file.write_text(json.dumps(["API_KEY", "OTHER_KEY"]))
    monkeypatch.setattr(vault, "KEYS_FILE", keys_file)
    monkeypatch.setattr(vault, "VAULT_DIR", tmp_path)

    deleted = []
    monkeypatch.setattr(
        vault.keyring,
        "delete_password",
        lambda service, key: deleted.append((service, key)),
    )

    assert vault.delete_secret("API_KEY") is True
    assert deleted == [(vault.SERVICE, "API_KEY")]
    assert vault.list_keys() == ["OTHER_KEY"]


def test_delete_secret_cleans_stale_index_entry(tmp_path, monkeypatch):
    keys_file = tmp_path / "vault_keys.json"
    keys_file.write_text(json.dumps(["API_KEY"]))
    monkeypatch.setattr(vault, "KEYS_FILE", keys_file)
    monkeypatch.setattr(vault, "VAULT_DIR", tmp_path)
    monkeypatch.setattr(
        vault.keyring,
        "delete_password",
        lambda service, key: (_ for _ in ()).throw(keyring.errors.PasswordDeleteError()),
    )

    assert vault.delete_secret("API_KEY") is False
    assert vault.list_keys() == []


def test_cli_vault_delete_reports_success(monkeypatch):
    delete_secret = Mock(return_value=True)
    monkeypatch.setattr(vault, "delete_secret", delete_secret)

    result = runner.invoke(cli.app, ["vault", "delete", "API_KEY"])

    assert result.exit_code == 0
    assert "deleted API_KEY." in result.output
    delete_secret.assert_called_once_with("API_KEY")
