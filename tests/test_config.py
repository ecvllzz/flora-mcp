import os
import subprocess
import sys
from pathlib import Path

import pytest

from flora_mcp import config


def test_no_appdata_fallback_or_implicit_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOCAL_CONFIG", tmp_path / "absent.toml")
    monkeypatch.delenv("FLORA_MCP_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "private-app"))
    with pytest.raises(ValueError, match="não configurada"):
        config.load_config()
    assert not (tmp_path / "private-app").exists()


def test_shared_file_is_independent_of_cwd_and_appdata(monkeypatch, tmp_path):
    local = tmp_path / "flora.local.toml"
    neutral = tmp_path / "shared"
    local.write_text("[flora]\ndata_dir = '" + str(neutral) + "'\n", encoding="utf-8")
    monkeypatch.setattr(config, "LOCAL_CONFIG", local)
    monkeypatch.delenv("FLORA_MCP_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path.parent)
    for app in ("claude", "codex"):
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / app))
        assert config.load_config().data_dir == neutral
    monkeypatch.setenv("FLORA_MCP_DATA_DIR", str(tmp_path / "env"))
    assert config.load_config().data_dir == tmp_path / "env"
    assert config.load_config(data_dir=str(tmp_path / "arg")).data_dir == tmp_path / "arg"
    with pytest.raises(ValueError, match="absoluto"):
        config.load_config(data_dir="relative")


@pytest.mark.parametrize("command", ["sync-stj", "sync-tjsc", "backup", "update"])
def test_collectors_and_backup_do_not_create_missing_base(tmp_path, command):
    missing = tmp_path / "must-not-exist"
    if command == "update":
        args = [str(Path(__file__).parents[1] / "scripts" / "update_once.py"), "--data-dir", str(missing)]
    else:
        args = ["-m", "flora_mcp.cli", "--data-dir", str(missing), command]
        if command == "sync-tjsc":
            args += ["--inicio", "2026-09-01", "--fim", "2026-09-01"]
        elif command == "backup":
            args += [str(tmp_path / "backup")]
    result = subprocess.run([sys.executable, *args], capture_output=True,
                            env={**os.environ, "PYTHONUTF8": "1"}, text=True)
    assert result.returncode == 2
    assert "Banco n" in result.stderr
    assert not missing.exists()
