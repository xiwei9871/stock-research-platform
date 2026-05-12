import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


def load_watchdog_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "finance_ingest_watchdog.py"
    spec = importlib.util.spec_from_file_location("finance_ingest_watchdog", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_process_exists_treats_zombie_as_missing(monkeypatch):
    watchdog = load_watchdog_module()
    monkeypatch.setattr(watchdog.os, "kill", lambda pid, signal: None)

    def fake_run(command, check, capture_output, text):
        assert command == ["ps", "-p", "123", "-o", "stat="]
        assert check is False
        assert capture_output is True
        assert text is True
        return SimpleNamespace(returncode=0, stdout="Z\n")

    monkeypatch.setattr(watchdog.subprocess, "run", fake_run)

    assert watchdog.process_exists(123) is False
