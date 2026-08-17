"""Release-gate coverage for CLI operational and diagnostic paths."""

from __future__ import annotations

import builtins
import shutil
from types import ModuleType, SimpleNamespace

import pytest
from click.testing import CliRunner

import phantom.cli as cli
import phantom.llm as llm_package
import phantom.llm.ollama as ollama_module
from phantom.config import PhantomConfig


def test_agent_factory_installs_interactive_approval(monkeypatch):
    request_seen = []
    safety = SimpleNamespace(_approval_callback=None)
    fake_agent = SimpleNamespace(_safety=safety)
    monkeypatch.setattr("phantom.agent.PhantomAgent.open", lambda: fake_agent)
    monkeypatch.setattr(
        cli.click,
        "confirm",
        lambda prompt, default=False: request_seen.append((prompt, default)) or True,
    )

    agent = cli._agent()
    request = SimpleNamespace(type=SimpleNamespace(value="wait"), source="unit")

    assert agent is fake_agent
    assert safety._approval_callback(request) is True
    assert request_seen == [("Approve wait from unit?", False)]


def test_daemon_helper_success_and_failures(monkeypatch):
    monkeypatch.setattr(
        cli, "send_command", lambda command, **payload: {"ok": True, "command": command, **payload}
    )
    assert cli._daemon("status")["command"] == "status"

    monkeypatch.setattr(
        cli, "send_command", lambda *_args, **_kwargs: {"ok": False, "error": "bad"}
    )
    with pytest.raises(cli.click.ClickException, match="bad"):
        cli._daemon("status")

    def unavailable(*_args, **_kwargs):
        raise cli.DaemonUnavailable("gone")

    monkeypatch.setattr(cli, "send_command", unavailable)
    with pytest.raises(cli.click.ClickException, match="gone"):
        cli._daemon("status")


def test_init_reports_available_and_unavailable_ollama(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(cli.Path, "home", lambda: tmp_path)

    class _Available:
        def available(self):
            return True

        def list_models(self):
            return ["a", "b"]

    monkeypatch.setattr(ollama_module, "OllamaProvider", _Available)
    result = runner.invoke(cli.main, ["init"])
    assert result.exit_code == 0
    assert "Ollama detected" in result.output

    class _Broken:
        def __init__(self):
            raise RuntimeError("no ollama")

    monkeypatch.setattr(ollama_module, "OllamaProvider", _Broken)
    result = runner.invoke(cli.main, ["init"])
    assert result.exit_code == 0
    assert "Ollama not detected" in result.output


def test_start_rejects_running_daemon(monkeypatch):
    monkeypatch.setattr(cli, "send_command", lambda *_args, **_kwargs: {"ok": True})
    result = CliRunner().invoke(cli.main, ["start"])
    assert result.exit_code != 0
    assert "already running" in result.output


def test_stop_process_disappears_before_inspection(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.Path, "home", lambda: tmp_path)
    socket = tmp_path / ".phantom" / "phantom.sock"
    socket.parent.mkdir(parents=True)
    socket.write_text("")
    monkeypatch.setattr(cli, "socket_path", lambda: socket)
    monkeypatch.setattr(cli, "send_command", lambda _command: {"ok": True, "pid": 123})
    monkeypatch.setattr(cli.os, "kill", lambda *_args: (_ for _ in ()).throw(ProcessLookupError()))

    result = CliRunner().invoke(cli.main, ["stop"])

    assert result.exit_code != 0
    assert "no longer exists" in result.output
    assert not socket.exists()
    assert not (tmp_path / ".phantom" / "phantom.pid").exists()


def test_stop_permission_error_and_exit_race(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(cli.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(cli, "send_command", lambda _command: {"ok": True, "pid": 321})

    def denied(_pid, sig):
        if sig == 0:
            raise PermissionError()

    monkeypatch.setattr(cli.os, "kill", denied)
    result = runner.invoke(cli.main, ["stop"])
    assert result.exit_code != 0
    assert "Permission denied" in result.output

    calls = []

    def exits(_pid, sig):
        calls.append(sig)
        if sig != 0:
            raise ProcessLookupError()

    monkeypatch.setattr(cli.os, "kill", exits)
    result = runner.invoke(cli.main, ["stop"])
    assert result.exit_code == 0
    assert "exited before" in result.output
    assert calls == [0, cli.signal.SIGTERM]


def test_recipe_run_failure_output(monkeypatch):
    class _Agent:
        async def run_recipe(self, _name):
            return {"success": False, "error": "recipe failed"}

    monkeypatch.setattr(cli, "_agent", lambda: _Agent())
    result = CliRunner().invoke(cli.main, ["recipes", "run", "demo"])
    assert result.exit_code == 0
    assert "recipe failed" in result.output


def test_doctor_covers_daemon_llm_disk_and_optional_dependency_states(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.Path, "home", lambda: tmp_path)
    (tmp_path / ".phantom").mkdir()
    (tmp_path / ".phantom" / "config.toml").write_text("[phantom]\n")
    monkeypatch.setattr(cli, "send_command", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(cli, "socket_path", lambda: tmp_path / ".phantom" / "phantom.sock")
    monkeypatch.setattr(
        shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=5 * 1024**3),
    )
    monkeypatch.setattr(PhantomConfig, "load", classmethod(lambda cls, _path=None: PhantomConfig()))

    provider = SimpleNamespace(available=lambda: True, name="mock")
    monkeypatch.setattr(llm_package, "get_provider", lambda _config: provider)

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name in {"pytesseract", "pynput"}:
            return ModuleType(name)
        if name == "pyautogui":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    result = CliRunner().invoke(cli.main, ["doctor"])

    assert result.exit_code == 0
    assert "RUNNING" in result.output
    assert "mock" in result.output
    assert "5.0 GB free" in result.output
    assert "optional" in result.output


def test_doctor_offline_error_and_disk_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.Path, "home", lambda: tmp_path)

    def unavailable(*_args, **_kwargs):
        raise cli.DaemonUnavailable("stopped")

    monkeypatch.setattr(cli, "send_command", unavailable)
    monkeypatch.setattr(
        cli.shutil,
        "disk_usage",
        lambda _path: (_ for _ in ()).throw(OSError("disk unavailable")),
    )
    monkeypatch.setattr(
        llm_package,
        "get_provider",
        lambda _config: (_ for _ in ()).throw(RuntimeError("provider failed")),
    )
    result = CliRunner().invoke(cli.main, ["doctor"])

    assert result.exit_code == 0
    assert "stopped" in result.output
    assert "ERROR" in result.output
    assert "unknown" in result.output


def test_models_unavailable_empty_and_populated(monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(PhantomConfig, "load", classmethod(lambda cls, _path=None: PhantomConfig()))

    unavailable = SimpleNamespace(available=lambda: False, name="none")
    monkeypatch.setattr(llm_package, "get_provider", lambda _config: unavailable)
    result = runner.invoke(cli.main, ["models"])
    assert result.exit_code == 0
    assert "No LLM provider available" in result.output

    empty = SimpleNamespace(available=lambda: True, name="mock", list_models=lambda: [])
    monkeypatch.setattr(llm_package, "get_provider", lambda _config: empty)
    result = runner.invoke(cli.main, ["models"])
    assert result.exit_code == 0
    assert "has no models" in result.output

    populated = SimpleNamespace(
        available=lambda: True,
        name="mock",
        model="b",
        list_models=lambda: ["a", "b"],
    )
    monkeypatch.setattr(llm_package, "get_provider", lambda _config: populated)
    result = runner.invoke(cli.main, ["models"])
    assert result.exit_code == 0
    assert "a" in result.output and "b" in result.output


def test_run_helper_executes_coroutine():
    async def value():
        return 42

    assert cli._run(value()) == 42
