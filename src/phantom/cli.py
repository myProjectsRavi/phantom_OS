"""PHANTOM CLI."""

from __future__ import annotations

import asyncio
import os
import platform
import shutil
import signal
import sys
from pathlib import Path

import click
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from phantom.control import DaemonUnavailable, send_command, socket_path

console = Console()


def _agent():
    """Create an interactive one-shot agent with an explicit approval prompt."""
    from phantom.agent import PhantomAgent

    agent = PhantomAgent.open()
    agent._safety._approval_callback = lambda request: click.confirm(
        f"Approve {request.type.value} from {request.source or 'cli'}?",
        default=False,
    )
    return agent


def _run(coro):
    return asyncio.run(coro)


def _daemon(command: str, **payload):
    try:
        response = send_command(command, **payload)
    except DaemonUnavailable as exc:
        raise click.ClickException(str(exc)) from exc
    if not response.get("ok", False):
        raise click.ClickException(str(response.get("error", "Daemon command failed")))
    return response


@click.group()
def main():
    """👻 PHANTOM — local-first desktop automation runtime."""


@main.command()
def init():
    """Initialize ~/.phantom/ with guided setup."""
    root = Path.home() / ".phantom"
    root.mkdir(mode=0o700, exist_ok=True)
    os.chmod(root, 0o700)
    for directory in (root / "recipes", root / "logs"):
        directory.mkdir(mode=0o700, exist_ok=True)
        os.chmod(directory, 0o700)
    config = root / "config.toml"
    if not config.exists():
        config.write_text(DEFAULT_CONFIG)
    os.chmod(config, 0o600)

    checks = [
        "[green]✓[/] Config created" if config.exists() else "[red]✗[/] Config failed",
        f"[green]✓[/] Recipes dir: {root / 'recipes'}",
    ]
    ollama_ok = False
    try:
        from phantom.llm.ollama import OllamaProvider

        provider = OllamaProvider()
        if provider.available():
            ollama_ok = True
            models = provider.list_models()
            checks.append(f"[green]✓[/] Ollama detected ({len(models)} models)")
        else:
            checks.append("[yellow]![/] Ollama not running (optional)")
    except Exception:
        checks.append("[yellow]![/] Ollama not detected (optional)")

    if not ollama_ok:
        hint = (
            "brew install ollama && ollama serve"
            if platform.system() == "Darwin"
            else "Install Ollama from its official package for your Linux distribution"
        )
        checks.append(f"[dim]  Optional LLM: {hint}[/]")

    console.print(
        Panel(
            "[bold green]✓ PHANTOM initialized[/]\n\n"
            + "\n".join(f"  {item}" for item in checks)
            + "\n\n  Next: phantom start",
            title="👻 PHANTOM",
            border_style="bright_magenta",
        )
    )


@main.command()
def start():
    """Start the PHANTOM daemon in the foreground."""
    try:
        send_command("status")
    except DaemonUnavailable:
        pass
    else:
        raise click.ClickException("PHANTOM daemon is already running")

    from phantom.daemon import PhantomDaemon

    console.print("[bold magenta]👻 PHANTOM daemon starting...[/]")
    PhantomDaemon().run()


@main.command()
def stop():
    """Stop the daemon identified by the live local control channel."""
    pid_file = Path.home() / ".phantom" / "phantom.pid"
    try:
        response = send_command("status")
    except DaemonUnavailable:
        pid_file.unlink(missing_ok=True)
        socket_path().unlink(missing_ok=True)
        console.print("[yellow]No live PHANTOM daemon found; cleaned stale local state[/]")
        return

    daemon_pid = response.get("pid")
    if not isinstance(daemon_pid, int) or daemon_pid <= 0:
        raise click.ClickException(
            "PHANTOM control socket returned an invalid process identity; refusing to signal"
        )

    # The live control channel is authoritative. Repair a stale/missing PID marker
    # rather than ever signalling an unrelated PID that merely happens to exist.
    pid_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    pid_file.write_text(str(daemon_pid))
    os.chmod(pid_file, 0o600)

    try:
        os.kill(daemon_pid, 0)
    except ProcessLookupError:
        pid_file.unlink(missing_ok=True)
        socket_path().unlink(missing_ok=True)
        raise click.ClickException(
            "PHANTOM control socket reported a process that no longer exists; cleaned stale state"
        )
    except PermissionError as exc:
        raise click.ClickException(
            f"Permission denied inspecting PHANTOM process {daemon_pid}"
        ) from exc

    try:
        os.kill(daemon_pid, signal.SIGTERM)
        console.print(f"[green]✓ Sent stop signal to PHANTOM daemon (pid={daemon_pid})[/]")
    except ProcessLookupError:
        pid_file.unlink(missing_ok=True)
        socket_path().unlink(missing_ok=True)
        console.print("[yellow]PHANTOM process exited before the stop signal was sent[/]")


@main.command()
def status():
    """Show state from the running PHANTOM daemon."""
    state = _daemon("status")["status"]
    table = Table(title="👻 PHANTOM Status", box=box.ROUNDED)
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="green")
    for key, value in state.items():
        if key != "stats":
            table.add_row(key, str(value))
    for key, value in state.get("stats", {}).items():
        table.add_row(f"  {key}", str(value))
    console.print(table)


@main.command()
def perceive():
    """Capture and show current perception through the running daemon."""
    frame = _daemon("perceive").get("frame")
    if not frame:
        console.print("[dim]No frame captured[/]")
        return
    console.print(
        Panel(
            f"  App: [bold cyan]{frame['app_name']}[/]\n"
            f"  Window: {frame['window_title']}\n"
            f"  Screen: [yellow]{frame['screen_type']}[/]\n"
            f"  Elements: {frame['elements']}\n"
            f"  Typing: {'✅' if frame['is_typing'] else '❌'}\n"
            f"  Idle: {frame['idle_seconds']:.1f}s",
            title="👁 Perception",
            border_style="cyan",
        )
    )


@main.command()
def intent():
    """Show current intent from the running daemon."""
    result = _daemon("intent").get("intent")
    if result:
        console.print(
            Panel(
                f"  Intent: [bold yellow]{result['intent']}[/]\n"
                f"  Confidence: {result['confidence']:.2f}\n"
                f"  App: {result['source_app']}",
                title="🧠 Intent",
                border_style="yellow",
            )
        )


@main.command()
def predictions():
    """Show behavioral predictions from the running daemon."""
    preds = _daemon("predictions").get("predictions", [])
    if not preds:
        console.print("[dim]No predictions available[/]")
        return
    table = Table(title="🔮 Predictions", box=box.ROUNDED)
    table.add_column("Action", style="cyan")
    table.add_column("Target App", style="yellow")
    table.add_column("Confidence", style="green")
    table.add_column("ETA", style="dim")
    table.add_column("Source")
    for item in preds:
        eta = item.get("expected_in_seconds", 0)
        table.add_row(
            item["action_type"],
            item.get("target_app", ""),
            f"{item.get('confidence', 0):.2f}",
            f"{eta:.0f}s" if eta else "—",
            item.get("source", ""),
        )
    console.print(table)


@main.command()
def patterns():
    """List learned patterns from a one-shot local agent."""
    agent = _agent()
    items = agent.learned_patterns()
    if not items:
        console.print("[dim]No patterns learned yet[/]")
        return
    table = Table(title="🔄 Learned Patterns", box=box.ROUNDED)
    table.add_column("ID", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Freq", style="yellow")
    table.add_column("Confidence", style="green")
    table.add_column("Approved")
    for item in items:
        table.add_row(
            item.id,
            item.name,
            str(item.frequency),
            f"{item.confidence:.2f}",
            "✅" if item.approved else "❌",
        )
    console.print(table)


@main.command("patterns-approve")
@click.argument("pattern_id")
def patterns_approve(pattern_id):
    """Approve a learned pattern in persisted local state."""
    agent = _agent()
    agent.approve_pattern(pattern_id)
    console.print(f"[green]✓ Pattern {pattern_id} approved[/]")


@main.group()
def recipes():
    """Manage automation recipes."""


@recipes.command("list")
def recipes_list():
    """List available recipes."""
    agent = _agent()
    table = Table(title="📋 Recipes", box=box.ROUNDED)
    table.add_column("Name", style="cyan")
    table.add_column("Source", style="green")
    table.add_column("Trigger", style="yellow")
    table.add_column("Runs", style="dim")
    table.add_column("Enabled")
    for recipe in agent.list_recipes():
        trigger = recipe.trigger.type if recipe.trigger else "manual"
        table.add_row(
            recipe.name,
            recipe.source,
            trigger,
            str(recipe.run_count),
            "✅" if recipe.enabled else "❌",
        )
    console.print(table)


@recipes.command("run")
@click.argument("name")
def recipes_run(name):
    """Run a recipe interactively with safety approval prompts."""
    agent = _agent()
    console.print(f"[magenta]👻 Running recipe: {name}[/]")
    result = _run(agent.run_recipe(name))
    if result.get("success"):
        console.print(f"[green]✓ Complete ({result['duration_ms']:.0f}ms)[/]")
    else:
        console.print(f"[red]✗ {result.get('error', 'Failed')}[/]")


@main.command()
@click.argument(
    "level",
    type=click.Choice(["suggest_only", "approve_each", "approve_new", "auto_execute"]),
)
def trust(level):
    """Set and persist the running daemon trust level."""
    _daemon("trust", level=level)
    console.print(f"[green]✓ Trust → {level}[/]")


@main.command("emergency-stop")
def emergency_stop_cmd():
    """Immediately stop all future actions in the running daemon."""
    _daemon("emergency_stop")
    console.print("[bold red]🛑 PHANTOM Emergency Stop activated[/]")


@main.command("resume-actions")
def resume_actions_cmd():
    """Resume actions after emergency stop or a tripped circuit breaker."""
    _daemon("resume")
    console.print("[green]✓ PHANTOM action execution resumed[/]")


@main.command()
def clipboard():
    """Show clipboard history owned by the running daemon."""
    history = _daemon("clipboard_history", limit=20).get("history", [])
    table = Table(title="📋 Clipboard History", box=box.ROUNDED)
    table.add_column("#", style="dim")
    table.add_column("Type", style="yellow")
    table.add_column("Content", max_width=60)
    for index, item in enumerate(reversed(history), 1):
        table.add_row(str(index), item.get("type", "?"), item.get("content", "")[:60])
    console.print(table)


@main.command()
def undo():
    """Undo the last reversible daemon action through normal safety policy."""
    result = _daemon("undo")
    if result.get("undone"):
        console.print("[green]✓ Action undone[/]")
    else:
        console.print("[yellow]No reversible action to undo[/]")


@main.command()
def stats():
    """Show statistics from the running daemon."""
    values = _daemon("stats")["stats"]
    console.print(
        Panel(
            f"  Frames: [bold]{values['frames_processed']}[/]\n"
            f"  Actions: [bold]{values['actions_executed']}[/]\n"
            f"  Patterns: [bold]{values['patterns_discovered']}[/]\n"
            f"  Recipes run: [bold]{values['recipes_run']}[/]\n"
            f"  Uptime: {values.get('uptime_seconds', 0):.0f}s",
            title="📊 Stats",
            border_style="green",
        )
    )


@main.command()
def doctor():
    """Verify local system, package configuration, dependencies, and LLM status."""
    table = Table(title="👻 PHANTOM Doctor", box=box.ROUNDED)
    table.add_column("Check", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Details", style="dim")

    py = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    table.add_row("Python", "[green]OK[/]" if sys.version_info >= (3, 10) else "[red]FAIL[/]", py)

    from phantom import __version__

    table.add_row("PHANTOM", "[green]OK[/]", f"v{__version__}")
    config_path = Path.home() / ".phantom" / "config.toml"
    table.add_row(
        "Config",
        "[green]OK[/]" if config_path.exists() else "[yellow]MISSING[/]",
        str(config_path),
    )
    try:
        send_command("status")
        table.add_row("Daemon", "[green]RUNNING[/]", str(socket_path()))
    except DaemonUnavailable:
        table.add_row("Daemon", "[dim]stopped[/]", str(socket_path()))

    for name, pkg in [("OCR", "pytesseract"), ("Input", "pynput"), ("Input2", "pyautogui")]:
        try:
            __import__(pkg)
            table.add_row(f"  {name}", "[green]installed[/]", pkg)
        except ImportError:
            table.add_row(f"  {name}", "[dim]optional[/]", f"pip install {pkg}")

    try:
        from phantom.config import PhantomConfig
        from phantom.llm import get_provider

        provider = get_provider(PhantomConfig.load())
        if provider.available():
            table.add_row("LLM Provider", "[green]OK[/]", provider.name)
        else:
            table.add_row(
                "LLM Provider",
                "[yellow]OFFLINE[/]",
                "Optional; rule-based mode remains available",
            )
    except Exception as exc:
        table.add_row("LLM Provider", "[red]ERROR[/]", str(exc)[:60])

    try:
        usage = shutil.disk_usage(Path.home())
        free_gb = usage.free / (1024**3)
        table.add_row(
            "Disk Space",
            "[green]OK[/]" if free_gb > 1 else "[yellow]LOW[/]",
            f"{free_gb:.1f} GB free",
        )
    except Exception:
        table.add_row("Disk Space", "[dim]unknown[/]", "")

    console.print(table)


@main.command()
def models():
    """List available local LLM models."""
    from phantom.config import PhantomConfig
    from phantom.llm import get_provider

    provider = get_provider(PhantomConfig.load())
    if not provider.available():
        console.print("[yellow]No LLM provider available.[/]")
        return
    model_list = provider.list_models()
    if not model_list:
        console.print(f"[yellow]{provider.name} is running but has no models.[/]")
        return
    table = Table(title=f"🤖 LLM Models ({provider.name})", box=box.ROUNDED)
    table.add_column("Model", style="cyan")
    table.add_column("Active", style="green")
    active = getattr(provider, "model", "")
    for model in model_list:
        table.add_row(model, "→" if model == active else "")
    console.print(table)


DEFAULT_CONFIG = '''[phantom]
trust_level = "approve_new"
capture_fps = 1.0
pattern_threshold = 3
max_actions_per_minute = 10
log_level = "info"

[perception]
ocr_enabled = true
element_detection = true

[privacy]
capture_retention = 0
log_retention_days = 30
excluded_apps = ["1Password", "Keychain Access"]
blocked_domains = ["bank", "medical"]

[llm]
provider = "auto"
ollama_host = "http://localhost:11434"
model = "auto"
temperature = 0.3
max_tokens = 1024
timeout = 30
base_url = ""
api_key = ""

[notifications]
style = "ghost"
'''
