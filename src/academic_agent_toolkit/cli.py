from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel

from academic_agent_toolkit import __version__
from academic_agent_toolkit.branding import APP_NAME, SHORT_NAME
from academic_agent_toolkit.config import DEFAULT_ENV_FILE, load_config
from academic_agent_toolkit.theme import Colors
from academic_agent_toolkit.installer import (
    ARS_REF,
    EXPERIMENT_AGENT_REF,
    SKILL_TARGETS,
    default_mcp_agents,
    default_skill_agents,
    detect_agents,
    discover_ars_source,
    doctor_summary,
    install_all,
    resolve_ars_source,
    self_check,
    uninstall_all,
    verify_mcp,
    verify_skill,
)
from academic_agent_toolkit.setup_keys import register_key_command
from academic_agent_toolkit.ui import console, make_table, show_banner, status_label


app = typer.Typer(
    name=SHORT_NAME.lower(),
    help="Plug-and-play setup for Academic Research Suite skills and Paper Search MCP across your AI agents.",
    no_args_is_help=False,
    rich_markup_mode="rich",
    pretty_exceptions_show_locals=False,
)

state = {"show_banner": True}


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"[bold {Colors.PRIMARY}]{SHORT_NAME}[/bold {Colors.PRIMARY}] [{Colors.TEXT}]v{__version__}[/]  —  {APP_NAME}")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: Annotated[bool | None, typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version and exit")] = None,
    no_banner: Annotated[bool, typer.Option("--no-banner", help="Disable the startup banner")] = False,
) -> None:
    state["show_banner"] = not no_banner


def _show_banner_once() -> None:
    if state["show_banner"]:
        show_banner()
        state["show_banner"] = False


def _selected_skill_agents() -> list[str]:
    return default_skill_agents()


@app.command()
def doctor() -> None:
    """Show environment readiness before installation."""
    _show_banner_once()
    config = load_config()
    summary = doctor_summary(config)
    console.print(Panel.fit(f"[bold {Colors.TEXT}]Doctor report[/bold {Colors.TEXT}]", border_style=Colors.BORDER_ACTIVE))

    env_status = status_label(summary["env_exists"])
    ars_status = status_label(summary["ars_valid"])
    ars_detail = summary["ars_source"] or f"not installed; can bootstrap {summary['ars_ref']}"
    console.print(f"  ARS source: {ars_status} {ars_detail}")
    console.print(f"  Managed ARS: {status_label(summary['managed_ars_exists'])} {summary['managed_ars_source']}")
    console.print(f"  Env file:   {env_status} {summary['env_file']}")

    table = make_table(title="Agent Detection", columns=["Agent", "Detected", "Skills", "MCP", "Notes"])
    for agent in summary["agents"]:
        table.add_row(
            agent.name,
            status_label(agent.detected),
            "yes" if agent.skill_supported else "no",
            "yes" if agent.mcp_supported else "no",
            agent.note,
        )
    console.print()
    console.print(table)


@app.command()
def uninstall(
    dry_run: Annotated[bool, typer.Option(help="Preview uninstall actions")] = False,
    remove_env: Annotated[bool, typer.Option(help="Also remove the Paper Search MCP env file")] = False,
    remove_managed_ars: Annotated[bool, typer.Option(help="Also remove AAT's downloaded ARS source")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip confirmation prompts")] = False,
) -> None:
    """Remove AAT-managed adapters and MCP registrations safely."""
    _show_banner_once()
    config = load_config()
    console.print(
        Panel.fit(
            f"[bold {Colors.TEXT}]Uninstall only removes AAT-managed files.[/bold {Colors.TEXT}]\nExisting user skills or hand-written MCP entries are adopted/skipped, not destroyed.",
            border_style=Colors.WARNING,
        )
    )
    if not yes and not dry_run:
        typer.confirm("Remove AAT-managed installation?", abort=True)
    results = uninstall_all(
        config=config,
        dry_run=dry_run,
        remove_env=remove_env,
        remove_managed_ars=remove_managed_ars,
    )
    table = make_table(title="Uninstall Results", columns=["Status", "Message"])
    for message in results:
        table.add_row("done", message)
    console.print(table)


@app.command("bootstrap-source", hidden=True)
def bootstrap_source(
    ars_source: Annotated[str, typer.Option(help="Persist the ARS source path for future installs")],
) -> None:
    """Persist a preferred ARS source path."""
    path = Path(ars_source).expanduser().resolve()
    if not path.exists():
        console.print(f"[{Colors.ERROR}]ARS source does not exist: {path}[/{Colors.ERROR}]")
        raise typer.Exit(code=1)
    config = load_config()
    config.ars_source = str(path)
    config.ars_source_mode = "explicit"
    config.ars_version = None
    from academic_agent_toolkit.config import save_config

    save_config(config)
    console.print(f"[{Colors.SUCCESS}]Saved ARS source:[/{Colors.SUCCESS}] {path}")


@app.command()
def install(
    ars_source: Annotated[str | None, typer.Option(help="Path to an existing ARS source tree")] = None,
    env_file: Annotated[str, typer.Option(help="Path to the Paper Search MCP .env file")] = str(DEFAULT_ENV_FILE),
    no_bootstrap: Annotated[bool, typer.Option(help="Skip automatic ARS download")] = False,
    replace_skills: Annotated[bool, typer.Option(help="Back up and replace existing skill directories")] = False,
    replace_mcp: Annotated[bool, typer.Option(help="Back up and replace existing MCP entries")] = False,
    dry_run: Annotated[bool, typer.Option(help="Preview the full plan without writing files")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip confirmation prompts")] = False,
) -> None:
    """Install skill adapters and MCP configs with a guided plan."""
    _show_banner_once()

    config = load_config()
    env_path = Path(env_file).expanduser().resolve()

    try:
        resolved = resolve_ars_source(
            explicit=ars_source,
            config=config,
            bootstrap=not no_bootstrap,
            dry_run=dry_run,
        )
    except RuntimeError as exc:
        console.print(f"[{Colors.ERROR}]Error:[/{Colors.ERROR}] {exc}")
        raise typer.Exit(code=1)

    skill_agents = _selected_skill_agents()
    mcp_agents = default_mcp_agents()

    console.print(Panel.fit(f"[bold {Colors.TEXT}]Installation plan[/bold {Colors.TEXT}]", border_style=Colors.BORDER_ACTIVE))
    console.print(f"  ARS source:  [{Colors.SUCCESS}]{resolved.path}[/{Colors.SUCCESS}] ({resolved.mode})")
    console.print(f"  Env file:    [{Colors.SUCCESS}]{env_path}[/{Colors.SUCCESS}]")
    console.print(f"  Skill agents: {', '.join(skill_agents) if skill_agents else f'[dim {Colors.TEXT_SECONDARY}]none[/]'}")

    mcp_display = [a for a in mcp_agents if a == "claude"] + [a for a in mcp_agents if a != "claude"]
    console.print(f"  MCP agents:   {', '.join(mcp_display) if mcp_display else f'[dim {Colors.TEXT_SECONDARY}]none[/]'}")

    if dry_run:
        console.print(f"\n[{Colors.WARNING}]Dry-run mode — no files will be written.[/]\n")

    if not yes and not dry_run:
        typer.confirm("\nProceed with installation?", abort=True)

    results = install_all(
        ars_source=resolved.path,
        env_file=env_path,
        skill_agents=skill_agents,
        mcp_agents=mcp_agents,
        replace_skills=replace_skills,
        replace_mcp=replace_mcp,
        dry_run=dry_run,
        ars_source_mode=resolved.mode,
        ars_version=resolved.version,
    )

    table = make_table(title="Install Results", columns=["Status", "Message"])
    for message in results:
        table.add_row("done", message)
    console.print(table)
    if any("run manually" in msg for msg in results):
        console.print(f"\n[bold {Colors.WARNING}]Manual step required:[/bold {Colors.WARNING}] run the claude command shown above.")
    console.print(f"\n[bold {Colors.SUCCESS}]Installation complete.[/bold {Colors.SUCCESS}] Next: [{Colors.TEXT}]aat setup-keys[/] then [{Colors.TEXT}]aat verify[/]")


@app.command()
def verify(
    ars_source: Annotated[str | None, typer.Option(help="Path to the installed ARS source tree")] = None,
) -> None:
    """Confirm skills and MCP are in place."""
    _show_banner_once()
    config = load_config()
    source = Path(ars_source).expanduser().resolve() if ars_source else discover_ars_source(config)
    skill_agents = config.installed_skill_agents or default_skill_agents()
    mcp_agents = config.installed_mcp_agents or default_mcp_agents()

    console.print(Panel.fit(f"[bold {Colors.TEXT}]Verification report[/bold {Colors.TEXT}]", border_style=Colors.BORDER_ACTIVE))

    skill_table = make_table(title="Skill Adapters", columns=["Agent", "Status", "Detail"])
    for agent in skill_agents:
        if agent not in SKILL_TARGETS:
            continue
        ok, detail = verify_skill(agent, source)
        skill_table.add_row(agent, status_label(ok), detail)
    console.print(skill_table)

    mcp_table = make_table(title="MCP Configurations", columns=["Agent", "Status", "Detail"])
    for agent in mcp_agents:
        ok, detail = verify_mcp(agent)
        mcp_table.add_row(agent, status_label(ok), detail)
    console.print(mcp_table)


@app.command("self-check")
def self_check_command() -> None:
    """Validate runtime prerequisites (Python, uv, ARS source, env file)."""
    _show_banner_once()
    config = load_config()
    results = self_check(config)

    console.print(Panel.fit(f"[bold {Colors.TEXT}]Self-check report[/bold {Colors.TEXT}]", border_style=Colors.BORDER_ACTIVE))
    table = make_table(title="Checks", columns=["Check", "Status", "Detail"])
    for item in results:
        table.add_row(item.name, status_label(item.ok), item.detail)
    console.print(table)


@app.command()
def repair(
    dry_run: Annotated[bool, typer.Option(help="Preview repair actions without writing")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip confirmation prompts")] = False,
) -> None:
    """Re-apply the last saved installation."""
    _show_banner_once()
    config = load_config()

    if not config.ars_source:
        console.print(f"[{Colors.ERROR}]No previous installation found. Run [{Colors.TEXT}]aat install[/] first.[/{Colors.ERROR}]")
        raise typer.Exit(code=1)

    ars_path = config.ars_source_path
    env_path = config.env_file_path or DEFAULT_ENV_FILE

    skill_agents = config.installed_skill_agents or default_skill_agents()
    mcp_agents = config.installed_mcp_agents or default_mcp_agents()

    console.print(Panel.fit(f"[bold {Colors.TEXT}]Repair plan (re-applying last installation)[/bold {Colors.TEXT}]", border_style=Colors.BORDER_ACTIVE))
    console.print(f"  ARS source:  [{Colors.SUCCESS}]{ars_path}[/{Colors.SUCCESS}]")
    console.print(f"  Env file:    [{Colors.SUCCESS}]{env_path}[/{Colors.SUCCESS}]")
    console.print(f"  Skill agents: {', '.join(skill_agents) if skill_agents else f'[dim {Colors.TEXT_SECONDARY}]none[/]'}")
    console.print(f"  MCP agents:   {', '.join(mcp_agents) if mcp_agents else f'[dim {Colors.TEXT_SECONDARY}]none[/]'}")

    if dry_run:
        console.print(f"\n[{Colors.WARNING}]Dry-run mode — no files will be written.[/]\n")

    if not yes and not dry_run:
        typer.confirm("\nProceed with repair?", abort=True)

    results = install_all(
        ars_source=ars_path,
        env_file=env_path,
        skill_agents=skill_agents,
        mcp_agents=mcp_agents,
        replace_skills=True,
        replace_mcp=True,
        dry_run=dry_run,
        ars_source_mode=config.ars_source_mode,
        ars_version=config.ars_version,
    )

    table = make_table(title="Repair Results", columns=["Status", "Message"])
    for message in results:
        table.add_row("done", message)
    console.print(table)
    if any("run manually" in msg for msg in results):
        console.print(f"\n[bold {Colors.WARNING}]Manual step required:[/bold {Colors.WARNING}] run the claude command shown above.")


def _latest_version() -> tuple[str, str]:
    import json
    import urllib.request

    try:
        resp = urllib.request.urlopen("https://pypi.org/pypi/academic-agent-toolkit/json", timeout=5)
        data = json.loads(resp.read())
        return data["info"]["version"], __version__
    except Exception:
        return "unknown", __version__


def _detect_install_method() -> str | None:
    import shutil

    if shutil.which("uv") and "academic-agent-toolkit" in _run_quiet(["uv", "tool", "list"]):
        return "uv"
    if shutil.which("pip") and "academic-agent-toolkit" in _run_quiet(["pip", "list"]):
        return "pip"
    return None


def _run_quiet(cmd: list[str]) -> str:
    import subprocess

    try:
        return subprocess.run(cmd, capture_output=True, text=True).stdout
    except Exception:
        return ""


@app.command()
def update(
    check: Annotated[bool, typer.Option(help="Only check for updates, do not apply")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip confirmation prompts")] = False,
) -> None:
    """Check for and apply AAT updates."""
    _show_banner_once()
    latest, current = _latest_version()

    console.print(Panel.fit(f"[bold {Colors.TEXT}]Update check[/bold {Colors.TEXT}]", border_style=Colors.BORDER_ACTIVE))
    console.print(f"  Installed: [bold]{current}[/bold]")
    console.print(f"  Latest:    [bold]{'[' + Colors.SUCCESS + ']' + latest + '[/' + Colors.SUCCESS + ']' if latest != 'unknown' else '[dim ' + Colors.TEXT_SECONDARY + ']unknown[/]'}[/]")

    if latest == "unknown":
        console.print(f"\n[{Colors.WARNING}]Could not reach PyPI to check for updates.[/]")
        raise typer.Exit(code=1)

    if latest == current:
        console.print(f"\n[bold {Colors.SUCCESS}]Already up-to-date[/bold {Colors.SUCCESS}] (v{current})")
        return

    console.print(f"\n[bold {Colors.WARNING}]New version available: [{Colors.TEXT}]v{latest}[/] (current: v{current})[/bold {Colors.WARNING}]")

    if check:
        console.print(f"\n[{Colors.WARNING}]Check mode — run without [{Colors.TEXT}]--check[/] to apply the update.[/]")
        return

    method = _detect_install_method()

    if method == "uv":
        upgrade_cmd = f"uv tool install --reinstall academic-agent-toolkit"
    elif method == "pip":
        upgrade_cmd = f"pip install --upgrade academic-agent-toolkit"
    else:
        console.print(f"[{Colors.WARNING}]Could not detect installation method. Upgrade manually with pip or uv.[/]")
        raise typer.Exit(code=1)

    console.print(f"\nWill run: [{Colors.TEXT}]{upgrade_cmd}[/]")

    if not yes:
        typer.confirm("Proceed with upgrade?", abort=True)

    import subprocess

    result = subprocess.run(upgrade_cmd.split(), capture_output=False)
    if result.returncode != 0:
        console.print(f"[{Colors.ERROR}]Upgrade failed.[/]")
        raise typer.Exit(code=1)

    console.print(f"[{Colors.SUCCESS}]Upgraded to v{latest}.[/]")

    config = load_config()
    if config.ars_source:
        if yes or typer.confirm("\nPrevious installation detected. Re-apply skills and MCP configs now?"):
            console.print()
            ars_path = config.ars_source_path
            env_path = config.env_file_path or DEFAULT_ENV_FILE
            skill_agents = config.installed_skill_agents or default_skill_agents()
            mcp_agents = config.installed_mcp_agents or default_mcp_agents()
            results = install_all(
                ars_source=ars_path,
                env_file=env_path,
                skill_agents=skill_agents,
                mcp_agents=mcp_agents,
                replace_skills=True,
                replace_mcp=True,
                dry_run=False,
                ars_source_mode=config.ars_source_mode,
                ars_version=config.ars_version,
            )
            table = make_table(title="Repair Results", columns=["Status", "Message"])
            for message in results:
                table.add_row("done", message)
            console.print(table)
            console.print(f"[bold {Colors.SUCCESS}]Update complete. Everything is in sync.[/bold {Colors.SUCCESS}]")


register_key_command(app)


def main() -> int:
    if len(sys.argv) <= 1:
        from academic_agent_toolkit.tui import run_tui

        return run_tui()
    app()
    return 0
