from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from collections.abc import Callable

from academic_agent_toolkit.config import DATA_DIR, DEFAULT_ENV_FILE, ToolkitConfig, save_config


SERVER_NAME = "paper-search-mcp"
MCP_COMMAND = ["uv", "run", "--with", "paper-search-mcp", "python", "-m", "paper_search_mcp.server"]
AGENTS_ROOT = Path.home() / ".agents"
AGENTS_GLOBAL_FILE = AGENTS_ROOT / "AGENTS.md"
CANONICAL_SKILL_DIR = AGENTS_ROOT / "skills" / "academic-research-suite"
CANONICAL_ARS_LINK = CANONICAL_SKILL_DIR / "ars"
CLAUDE_MCP_DIR = Path.home() / ".claude" / "mcp"
CLAUDE_MCP_PATH = CLAUDE_MCP_DIR / f"{SERVER_NAME}.json"
ARS_REPO_URL = "https://github.com/Imbad0202/academic-research-skills"
ARS_REF = "v3.10.0"
ARS_ARCHIVE_URL = f"{ARS_REPO_URL}/archive/refs/tags/{ARS_REF}.zip"
EXPERIMENT_AGENT_REPO_URL = "https://github.com/Imbad0202/experiment-agent"
EXPERIMENT_AGENT_REF = "v1.1.0"
EXPERIMENT_AGENT_ARCHIVE_URL = f"{EXPERIMENT_AGENT_REPO_URL}/archive/refs/tags/{EXPERIMENT_AGENT_REF}.zip"
MANAGED_ARS_VERSION = f"{ARS_REF}+experiment-agent-{EXPERIMENT_AGENT_REF}"
CORE_ARS_SKILLS = [
    "deep-research",
    "academic-paper",
    "academic-paper-reviewer",
    "academic-pipeline",
]
REQUIRED_ARS_SKILLS = [
    *CORE_ARS_SKILLS,
    "experiment-agent",
]

SKILL_TARGETS = {
    "claude": Path.home() / ".claude" / "skills" / "academic-research-suite",
    "opencode": Path.home() / ".config" / "opencode" / "skills" / "academic-research-suite",
    "cursor": Path.home() / ".cursor" / "skills" / "academic-research-suite",
    "copilot": Path.home() / ".copilot" / "skills" / "academic-research-suite",
    "codex": Path.home() / ".codex" / "skills" / "academic-research-suite",
    "zed": CANONICAL_SKILL_DIR,
}

JSON_TARGETS = {
    "opencode": (Path.home() / ".config" / "opencode" / "opencode.json", "mcp"),
    "cursor": (Path.home() / ".cursor" / "mcp.json", "mcpServers"),
    "vscode-user": (Path.home() / ".config" / "Code" / "User" / "mcp.json", "servers"),
    "vscode-global": (Path.home() / ".vscode" / "mcp.json", "servers"),
    "copilot": (Path.home() / ".copilot" / "mcp-config.json", "mcpServers"),
    "zed": (Path.home() / ".config" / "zed" / "settings.json", "context_servers"),
}

DISCOVERY_HINTS = {
    "claude": Path.home() / ".claude",
    "opencode": Path.home() / ".config" / "opencode",
    "cursor": Path.home() / ".cursor",
    "copilot": Path.home() / ".copilot",
    "codex": Path.home() / ".codex",
    "vscode-user": Path.home() / ".config" / "Code" / "User",
    "vscode-global": Path.home() / ".vscode",
    "zed": Path.home() / ".config" / "zed",
}

ARS_SOURCE_CANDIDATES = [
    CANONICAL_ARS_LINK,
    DATA_DIR / "ars" / MANAGED_ARS_VERSION / "source",
    Path.home() / ".codex" / "skills" / "academic-research-suite" / "ars",
    Path.home() / ".claude" / "skills" / "academic-research-suite" / "ars",
    Path.home() / ".config" / "opencode" / "skills" / "academic-research-suite" / "ars",
    Path.home() / ".cursor" / "skills" / "academic-research-suite" / "ars",
    Path.home() / ".copilot" / "skills" / "academic-research-suite" / "ars",
]

UNIVERSAL_SKILL_TEMPLATE = """---
name: academic-research-suite
description: >
  Academic research workflows: deep research, literature review, systematic
  review, manuscript drafting, paper review, citation checks, research-to-paper
  pipelines, and experiment planning. Use for research tasks, paper workflows,
  ARS aliases, and experiment design.
metadata:
  adapter_runtime: universal
  managed_by: academic-agent-toolkit
---

# Academic Research Suite

Use this skill as a router. Do not load the full suite by default. Read one workflow entrypoint from `ars/`, then load only the files needed for the current phase.

| Intent | Read first |
|---|---|
| Deep research, literature review, systematic review, meta-analysis, fact checking, research question refinement | `ars/deep-research/WORKFLOW.md` or `ars/deep-research/SKILL.md` |
| Paper writing, outline, abstract, revision, citation formatting, AI disclosure, format guidance | `ars/academic-paper/WORKFLOW.md` or `ars/academic-paper/SKILL.md` |
| Peer review simulation, editorial decision, review calibration | `ars/academic-paper-reviewer/WORKFLOW.md` or `ars/academic-paper-reviewer/SKILL.md` |
| End-to-end research-to-paper workflow | `ars/academic-pipeline/WORKFLOW.md` or `ars/academic-pipeline/SKILL.md` |
| Experiment planning, study protocol, statistical interpretation, reproducibility validation | `ars/experiment-agent/WORKFLOW.md` or `ars/experiment-agent/SKILL.md` |

If the user has only a broad paper topic or tentative title without a clear research question, route to the `ars/deep-research` entrypoint in Socratic mode first and ask 3-5 narrowing questions.

Alias routing: treat `/ars-*` and `ars-*` command names as prompt recipes under `ars/commands/`, then route to the matching workflow. If slash-prefixed input is reserved by the client, tell the user to use the plain alias form.

Runtime mapping: upstream ARS agent/team references are role prompts to execute inline unless the current client has native subagent delegation and the user explicitly asks for delegation or parallel agents. Use Paper Search MCP for current literature retrieval, DOI/PDF checks, and source verification.
"""

SKILL_TEMPLATES = {agent: UNIVERSAL_SKILL_TEMPLATE for agent in SKILL_TARGETS}

GLOBAL_AGENTS_TEMPLATE = f"""<!-- BEGIN academic-agent-toolkit -->
# Academic Agent Toolkit

Academic Research Suite is installed globally at `{CANONICAL_SKILL_DIR}`.

When the user asks for academic research, literature review, systematic review, manuscript drafting, peer review, citation checking, research-to-paper pipelines, or experiment planning, use the `academic-research-suite` skill if your runtime supports skills.

If your runtime does not support skills, read `{CANONICAL_SKILL_DIR / 'SKILL.md'}` as the router and load only the required workflow files under `{CANONICAL_ARS_LINK}`.

Use Paper Search MCP (`{SERVER_NAME}`) for current literature retrieval, DOI/PDF checks, and source verification.
<!-- END academic-agent-toolkit -->
"""


@dataclass
class AgentStatus:
    name: str
    detected: bool
    skill_supported: bool
    mcp_supported: bool
    note: str = ""


@dataclass
class ResolvedArsSource:
    path: Path
    mode: str
    version: str | None
    message: str


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    target = path.with_name(f"{path.name}.bak-{stamp}")
    shutil.copy2(path, target)
    return target


def managed_ars_source_path() -> Path:
    return DATA_DIR / "ars" / MANAGED_ARS_VERSION / "source"


def _validate_skill_source(path: Path, required_skills: list[str]) -> tuple[bool, str]:
    missing = [
        item
        for item in required_skills
        if not ((path / item / "WORKFLOW.md").exists() or (path / item / "SKILL.md").exists())
    ]
    if missing:
        return False, "missing entrypoint for " + ", ".join(missing)
    return True, "ARS workflow source is valid"


def validate_ars_source(path: Path) -> tuple[bool, str]:
    return _validate_skill_source(path, REQUIRED_ARS_SKILLS)


def validate_core_ars_source(path: Path) -> tuple[bool, str]:
    return _validate_skill_source(path, CORE_ARS_SKILLS)


def locate_ars_source(root: Path) -> Path | None:
    return locate_source(root, validate_ars_source)


def locate_core_ars_source(root: Path) -> Path | None:
    return locate_source(root, validate_core_ars_source)


def locate_source(root: Path, validator: Callable[[Path], tuple[bool, str]]) -> Path | None:
    candidates = [root]
    candidates.extend(item for item in root.iterdir() if item.is_dir())
    for candidate in candidates:
        ok, _ = validator(candidate)
        if ok:
            return candidate.resolve()
        nested = candidate / "ars"
        if nested.exists():
            ok, _ = validator(nested)
            if ok:
                return nested.resolve()
    return None


def locate_experiment_agent_source(root: Path) -> Path | None:
    candidates = [root]
    candidates.extend(item for item in root.iterdir() if item.is_dir())
    for candidate in candidates:
        if (candidate / "SKILL.md").exists() and (candidate / "agents").is_dir():
            return candidate.resolve()
    return None


def download_and_extract_archive(url: str, archive: Path, extract_dir: Path) -> None:
    try:
        urllib.request.urlretrieve(url, archive)
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not download archive from {url}: {exc}") from exc
    with zipfile.ZipFile(archive) as zip_file:
        zip_file.extractall(extract_dir)


def bootstrap_ars_source(*, dry_run: bool = False) -> ResolvedArsSource:
    target = managed_ars_source_path()
    ok, _ = validate_ars_source(target) if target.exists() else (False, "missing managed ARS source")
    if ok:
        return ResolvedArsSource(target.resolve(), "managed", MANAGED_ARS_VERSION, "using managed ARS source")
    if dry_run:
        return ResolvedArsSource(
            target.resolve(),
            "managed",
            MANAGED_ARS_VERSION,
            f"would download ARS {ARS_REF} and experiment-agent {EXPERIMENT_AGENT_REF}",
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="aat-ars-") as temp_dir:
        temp_path = Path(temp_dir)
        ars_extract = temp_path / "ars-extract"
        experiment_extract = temp_path / "experiment-extract"
        download_and_extract_archive(ARS_ARCHIVE_URL, temp_path / "ars.zip", ars_extract)
        download_and_extract_archive(EXPERIMENT_AGENT_ARCHIVE_URL, temp_path / "experiment-agent.zip", experiment_extract)

        source = locate_core_ars_source(ars_extract)
        if source is None:
            raise RuntimeError(f"Downloaded ARS archive did not contain required workflows: {ARS_ARCHIVE_URL}")
        experiment_source = locate_experiment_agent_source(experiment_extract)
        if experiment_source is None:
            raise RuntimeError(
                f"Downloaded experiment-agent archive did not contain a valid skill: {EXPERIMENT_AGENT_ARCHIVE_URL}"
            )
        staged_source = temp_path / "managed-source"
        shutil.copytree(source, staged_source, symlinks=True)
        shutil.copytree(experiment_source, staged_source / "experiment-agent", symlinks=True)
        ok, detail = validate_ars_source(staged_source)
        if not ok:
            raise RuntimeError(f"Composed ARS source is invalid: {detail}")
        if target.exists():
            backup_target = target.with_name(f"source.backup-{datetime.now().strftime('%Y%m%d%H%M%S')}")
            target.rename(backup_target)
        shutil.copytree(staged_source, target, symlinks=True)
    return ResolvedArsSource(
        target.resolve(),
        "managed",
        MANAGED_ARS_VERSION,
        f"downloaded ARS {ARS_REF} and experiment-agent {EXPERIMENT_AGENT_REF}",
    )


def discover_ars_source(config: ToolkitConfig | None = None) -> Path | None:
    if config and config.ars_source:
        candidate = Path(config.ars_source).expanduser().resolve()
        ok, _ = validate_ars_source(candidate) if candidate.exists() else (False, "missing")
        if ok:
            return candidate
    for candidate in ARS_SOURCE_CANDIDATES:
        ok, _ = validate_ars_source(candidate) if candidate.exists() else (False, "missing")
        if ok:
            return candidate.resolve()
    return None


def resolve_ars_source(
    *,
    explicit: str | None,
    config: ToolkitConfig,
    bootstrap: bool,
    dry_run: bool,
) -> ResolvedArsSource:
    if explicit:
        root = Path(explicit).expanduser().resolve()
        candidate = locate_ars_source(root) if root.exists() and root.is_dir() else None
        if candidate is None:
            raise RuntimeError(f"ARS source is invalid: {root}")
        return ResolvedArsSource(candidate, "explicit", None, "using explicit ARS source")

    if config.ars_source:
        configured = Path(config.ars_source).expanduser().resolve()
        ok, _ = validate_ars_source(configured) if configured.exists() else (False, "missing")
        if ok:
            return ResolvedArsSource(
                configured,
                config.ars_source_mode or "adopted",
                config.ars_version,
                "using saved ARS source",
            )

    for candidate in ARS_SOURCE_CANDIDATES:
        ok, _ = validate_ars_source(candidate) if candidate.exists() else (False, "missing")
        if ok:
            mode = "managed" if candidate == managed_ars_source_path() else "adopted"
            version = MANAGED_ARS_VERSION if mode == "managed" else None
            return ResolvedArsSource(candidate.resolve(), mode, version, f"{mode} existing ARS source")

    if bootstrap:
        return bootstrap_ars_source(dry_run=dry_run)
    raise RuntimeError("Could not find ARS locally and bootstrap is disabled. Pass --ars-source or remove --no-bootstrap.")


def detect_agents() -> list[AgentStatus]:
    return [
        AgentStatus("claude", DISCOVERY_HINTS["claude"].exists(), True, True, "symlinked global .agents skill + Claude MCP"),
        AgentStatus("opencode", DISCOVERY_HINTS["opencode"].exists(), True, True, "symlinked global .agents skill + opencode.json MCP"),
        AgentStatus("cursor", DISCOVERY_HINTS["cursor"].exists(), True, True, "symlinked global .agents skill + mcp.json MCP"),
        AgentStatus("copilot", DISCOVERY_HINTS["copilot"].exists(), True, True, "symlinked global .agents skill + mcp-config MCP; also loads ~/.agents/skills natively"),
        AgentStatus("codex", DISCOVERY_HINTS["codex"].exists(), True, True, "symlinked global .agents skill + Codex MCP"),
        AgentStatus("vscode-user", DISCOVERY_HINTS["vscode-user"].exists(), False, True, "VS Code MCP only"),
        AgentStatus("vscode-global", DISCOVERY_HINTS["vscode-global"].exists(), False, True, "VS Code MCP only"),
        AgentStatus("zed", DISCOVERY_HINTS["zed"].exists(), True, True, "native global skills from ~/.agents/skills + Zed MCP"),
    ]


def default_skill_agents() -> list[str]:
    return [status.name for status in detect_agents() if status.detected and status.skill_supported]


def default_mcp_agents() -> list[str]:
    return [status.name for status in detect_agents() if status.detected and status.mcp_supported]


def ensure_env_template(path: Path) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "# Paper Search MCP credentials",
                "# Run: aat setup-keys  for interactive guided configuration",
                "",
                "PAPER_SEARCH_MCP_UNPAYWALL_EMAIL=you@example.com",
                "PAPER_SEARCH_MCP_CORE_API_KEY=",
                "PAPER_SEARCH_MCP_SEMANTIC_SCHOLAR_API_KEY=",
                "PAPER_SEARCH_MCP_GOOGLE_SCHOLAR_PROXY_URL=",
                "PAPER_SEARCH_MCP_DOAJ_API_KEY=",
                "PAPER_SEARCH_MCP_ZENODO_ACCESS_TOKEN=",
                "PAPER_SEARCH_MCP_IEEE_API_KEY=",
                "PAPER_SEARCH_MCP_ACM_API_KEY=",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return True


def json_server(agent: str, env_file: Path) -> dict:
    env = {"PAPER_SEARCH_MCP_ENV_FILE": str(env_file)}
    if agent == "opencode":
        return {"type": "local", "enabled": True, "command": MCP_COMMAND, "environment": env}
    if agent in {"vscode-user", "vscode-global"}:
        return {"type": "stdio", "command": MCP_COMMAND[0], "args": MCP_COMMAND[1:], "env": env}
    if agent == "copilot":
        return {"type": "local", "command": MCP_COMMAND[0], "args": MCP_COMMAND[1:], "env": env}
    if agent == "zed":
        return {"source": "custom", "enabled": True, "command": MCP_COMMAND[0], "args": MCP_COMMAND[1:], "env": env}
    return {"command": MCP_COMMAND[0], "args": MCP_COMMAND[1:], "env": env}


def claude_command(env_file: Path) -> str:
    config = json.dumps(json_server("claude", env_file), separators=(",", ":"))
    return f"claude mcp add-json {SERVER_NAME} --scope user '{config}'"


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def strip_jsonc(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    lines: list[str] = []
    for line in text.splitlines():
        in_string = False
        escaped = False
        cut = len(line)
        for index, char in enumerate(line):
            if escaped:
                escaped = False
                continue
            if char == "\\" and in_string:
                escaped = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if not in_string and line[index : index + 2] == "//":
                cut = index
                break
        lines.append(line[:cut])
    return re.sub(r",\s*([}\]])", r"\1", "\n".join(lines))


def load_json_or_jsonc(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(strip_jsonc(text))


def ensure_agents_home(ars_source: Path, dry_run: bool, replace: bool) -> str:
    desired_skill = UNIVERSAL_SKILL_TEMPLATE.strip() + "\n"
    desired_agents = GLOBAL_AGENTS_TEMPLATE.strip() + "\n"
    if dry_run:
        return f"would create global skill at {CANONICAL_SKILL_DIR}"
    if CANONICAL_SKILL_DIR.exists() and not is_canonical_skill_ready()[0]:
        if not replace:
            raise RuntimeError(
                f"Existing non-managed skill found at {CANONICAL_SKILL_DIR}. Rerun with --replace-skills to back it up and replace it."
            )
        backup_target = CANONICAL_SKILL_DIR.with_name(
            f"{CANONICAL_SKILL_DIR.name}.backup-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        )
        CANONICAL_SKILL_DIR.rename(backup_target)
    CANONICAL_SKILL_DIR.mkdir(parents=True, exist_ok=True)
    (CANONICAL_SKILL_DIR / "SKILL.md").write_text(desired_skill, encoding="utf-8")
    if CANONICAL_ARS_LINK.exists() or CANONICAL_ARS_LINK.is_symlink():
        CANONICAL_ARS_LINK.unlink()
    CANONICAL_ARS_LINK.symlink_to(ars_source, target_is_directory=True)
    AGENTS_GLOBAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    current_agents = AGENTS_GLOBAL_FILE.read_text(encoding="utf-8") if AGENTS_GLOBAL_FILE.exists() else ""
    begin = "<!-- BEGIN academic-agent-toolkit -->"
    end = "<!-- END academic-agent-toolkit -->"
    if begin in current_agents and end in current_agents:
        before, rest = current_agents.split(begin, 1)
        _, after = rest.split(end, 1)
        next_agents = before.rstrip() + "\n\n" + desired_agents + after.lstrip("\n")
    else:
        next_agents = current_agents.rstrip() + "\n\n" + desired_agents if current_agents.strip() else desired_agents
    AGENTS_GLOBAL_FILE.write_text(next_agents, encoding="utf-8")
    return f"installed global .agents skill at {CANONICAL_SKILL_DIR}"


def is_canonical_skill_ready(ars_source: Path | None = None) -> tuple[bool, str]:
    skill_file = CANONICAL_SKILL_DIR / "SKILL.md"
    if not skill_file.exists() or not CANONICAL_ARS_LINK.is_symlink():
        return False, "missing ~/.agents skill, SKILL.md, or ars symlink"
    expected = UNIVERSAL_SKILL_TEMPLATE.strip() + "\n"
    if skill_file.read_text(encoding="utf-8") != expected:
        return False, "global .agents skill is not AAT-managed"
    if ars_source and CANONICAL_ARS_LINK.resolve() != ars_source:
        return False, f"global ars symlink points to {CANONICAL_ARS_LINK.resolve()} instead of {ars_source}"
    return True, "global .agents skill installed"


def install_skill(agent: str, ars_source: Path, replace: bool, dry_run: bool) -> str:
    target = SKILL_TARGETS[agent]
    if agent == "zed":
        ok, detail = is_canonical_skill_ready(ars_source)
        return detail if ok else f"Zed will load the global .agents skill at {CANONICAL_SKILL_DIR}"
    if agent == "codex" and target.exists() and str(ars_source).startswith(str(target.resolve())):
        raise RuntimeError(
            "Refusing to replace Codex skill because the ARS source lives inside the same Codex target path. Use --ars-source with a separate checkout first."
        )
    if dry_run:
        return f"would symlink {target} to {CANONICAL_SKILL_DIR}"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        if target.is_symlink() and target.resolve() == CANONICAL_SKILL_DIR:
            return f"skill symlink already installed for {agent}"
        if not replace and not is_managed_skill(agent):
            return f"skipped existing skill for {agent}; rerun with --replace-skills"
        if target.is_symlink() or target.is_file():
            target.unlink()
        else:
            backup_target = target.with_name(f"{target.name}.backup-{datetime.now().strftime('%Y%m%d%H%M%S')}")
            target.rename(backup_target)
    target.symlink_to(CANONICAL_SKILL_DIR, target_is_directory=True)
    return f"symlinked skill adapter for {agent} to global .agents skill"


def merge_json_config(agent: str, env_file: Path, dry_run: bool, replace: bool) -> str:
    path, top_key = JSON_TARGETS[agent]
    try:
        data = load_json(path)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in {path}: {exc}") from exc
    desired = json_server(agent, env_file)
    servers = data.setdefault(top_key, {})
    existing = servers.get(SERVER_NAME)
    if existing is not None and existing != desired and not replace:
        return f"adopted existing MCP config for {agent}; rerun with --replace-mcp to manage it"
    if dry_run:
        return f"would merge MCP config for {agent} into {path}"
    servers[SERVER_NAME] = desired
    if path.exists():
        backup(path)
    write_json(path, data)
    return f"merged MCP config for {agent}"


def find_json_object_span(text: str, key: str) -> tuple[int, int] | None:
    match = re.search(rf'"{re.escape(key)}"\s*:', text)
    if not match:
        return None
    start = text.find("{", match.end())
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_string:
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return start, index + 1
    return None


def insert_json_object_property(text: str, object_span: tuple[int, int], key: str, value: dict) -> str:
    start, end = object_span
    body = text[start + 1 : end - 1]
    indent_match = re.search(r"\n([ \t]*)\S", body)
    indent = indent_match.group(1) if indent_match else "    "
    entry = json.dumps({key: value}, indent=2)[1:-1]
    entry = "\n".join(indent + line if line.strip() else line for line in entry.splitlines())
    separator = ",\n" if body.strip() else "\n"
    return text[: end - 1] + separator + entry + "\n" + text[end - 1 :]


def remove_json_object_property(text: str, object_span: tuple[int, int], key: str) -> str | None:
    start, end = object_span
    match = re.search(rf'"{re.escape(key)}"\s*:', text[start:end])
    if not match:
        return None
    key_start = start + match.start()
    value_start = text.find("{", start + match.end())
    if value_start == -1 or value_start >= end:
        return None
    value_span = find_json_object_span(text[key_start:end], key)
    if value_span is None:
        return None
    value_end = key_start + value_span[1]
    previous_comma = text.rfind(",", start, key_start)
    previous_newline = text.rfind("\n", start, key_start)
    if previous_comma > previous_newline:
        remove_start = previous_comma
        remove_end = value_end
    else:
        remove_start = previous_newline + 1 if previous_newline != -1 else key_start
        next_comma = text.find(",", value_end, end)
        remove_end = next_comma + 1 if next_comma != -1 else value_end
    return text[:remove_start] + text[remove_end:]


def merge_zed_config(env_file: Path, dry_run: bool, replace: bool) -> str:
    path, top_key = JSON_TARGETS["zed"]
    desired = json_server("zed", env_file)
    if not path.exists():
        if dry_run:
            return f"would merge MCP config for zed into {path}"
        write_json(path, {top_key: {SERVER_NAME: desired}})
        return "merged MCP config for zed"
    text = path.read_text(encoding="utf-8")
    if SERVER_NAME in text and not replace:
        return "adopted existing MCP config for zed; rerun with --replace-mcp to manage it"
    span = find_json_object_span(text, top_key)
    if span is None:
        next_text = text.rstrip()[:-1].rstrip() + f',\n  "{top_key}": {{\n  }}\n}}\n' if text.strip().endswith("}") else text
        span = find_json_object_span(next_text, top_key)
        if span is None:
            raise RuntimeError(f"Could not safely locate or create {top_key} in {path}")
    else:
        next_text = text
    if SERVER_NAME in next_text and replace:
        removed = remove_json_object_property(next_text, span, SERVER_NAME)
        if removed is not None:
            next_text = removed
            span = find_json_object_span(next_text, top_key)
    if dry_run:
        return f"would merge MCP config for zed into {path}"
    next_text = insert_json_object_property(next_text, span, SERVER_NAME, desired)
    backup(path)
    path.write_text(next_text, encoding="utf-8")
    return "merged MCP config for zed"


def remove_zed_config(env_file: Path, dry_run: bool) -> str:
    path, top_key = JSON_TARGETS["zed"]
    if not path.exists():
        return "MCP config for zed was not installed"
    text = path.read_text(encoding="utf-8")
    if SERVER_NAME not in text:
        return "MCP config for zed was not installed"
    managed_markers = [
        str(env_file),
        "PAPER_SEARCH_MCP_ENV_FILE",
        "paper_search_mcp.server",
    ]
    if not all(marker in text for marker in managed_markers):
        return "skipped non-managed MCP config for zed"
    span = find_json_object_span(text, top_key)
    if span is None:
        return "skipped non-managed MCP config for zed"
    next_text = remove_json_object_property(text, span, SERVER_NAME)
    if next_text is None:
        return "skipped non-managed MCP config for zed"
    if dry_run:
        return f"would remove MCP config for zed from {path}"
    backup(path)
    path.write_text(next_text, encoding="utf-8")
    return "removed MCP config for zed"


def merge_claude_config(env_file: Path, dry_run: bool, replace: bool) -> str:
    desired = json_server("claude", env_file)
    if CLAUDE_MCP_PATH.exists():
        try:
            existing = json.loads(CLAUDE_MCP_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = None
        if existing == desired:
            return "Claude MCP already configured"
        if not replace:
            return "adopted existing Claude MCP config; rerun with --replace-mcp to manage it"
    if dry_run:
        return f"would write Claude MCP config to {CLAUDE_MCP_PATH}"
    CLAUDE_MCP_DIR.mkdir(parents=True, exist_ok=True)
    if CLAUDE_MCP_PATH.exists():
        backup(CLAUDE_MCP_PATH)
    CLAUDE_MCP_PATH.write_text(json.dumps(desired, indent=2) + "\n", encoding="utf-8")
    return "merged MCP config for claude"


def codex_block(env_file: Path) -> str:
    return f"""# BEGIN academic-agent-toolkit:{SERVER_NAME}
[mcp_servers.{SERVER_NAME}]
command = \"{MCP_COMMAND[0]}\"
args = {json.dumps(MCP_COMMAND[1:])}

[mcp_servers.{SERVER_NAME}.env]
PAPER_SEARCH_MCP_ENV_FILE = \"{env_file}\"
# END academic-agent-toolkit:{SERVER_NAME}
"""


def merge_codex_config(env_file: Path, dry_run: bool, replace: bool) -> str:
    path = Path.home() / ".codex" / "config.toml"
    begin = f"# BEGIN academic-agent-toolkit:{SERVER_NAME}"
    end = f"# END academic-agent-toolkit:{SERVER_NAME}"
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    block = codex_block(env_file)
    if begin in current and end in current:
        before, rest = current.split(begin, 1)
        _, after = rest.split(end, 1)
        next_text = before.rstrip() + "\n\n" + block + after.lstrip("\n")
    elif SERVER_NAME in current:
        # Inline config exists (without our markers). Replace it with managed block.
        next_text = _replace_inline_codex_config(current, SERVER_NAME, block)
    else:
        next_text = current.rstrip() + "\n\n" + block
    if dry_run:
        return f"would merge MCP config for codex into {path}"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup(path)
    path.write_text(next_text, encoding="utf-8")
    return "merged MCP config for codex"


def _replace_inline_codex_config(text: str, server_name: str, block: str) -> str:
    """Replace an inline [mcp_servers.{server_name}] section with our managed block."""
    section_header = f"[mcp_servers.{server_name}]"
    lines = text.split("\n")
    start_idx = None
    end_idx = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == section_header:
            start_idx = i
        elif start_idx is not None and stripped.startswith("[") and not stripped.startswith(f"[mcp_servers.{server_name}."):
            end_idx = i
            break

    if start_idx is None:
        # Section header not found as exact match; append block
        return text.rstrip() + "\n\n" + block

    if end_idx is None:
        end_idx = len(lines)

    # Remove any comment markers that might precede the section
    while start_idx > 0 and lines[start_idx - 1].strip().startswith("#"):
        start_idx -= 1

    # Remove trailing blank lines before the next section
    while end_idx > start_idx and lines[end_idx - 1].strip() == "":
        end_idx -= 1

    before = "\n".join(lines[:start_idx]).rstrip()
    after = "\n".join(lines[end_idx:]).lstrip("\n")
    return before + "\n\n" + block + after


def install_all(
    *,
    ars_source: Path,
    env_file: Path,
    skill_agents: list[str],
    mcp_agents: list[str],
    replace_skills: bool,
    replace_mcp: bool,
    dry_run: bool,
    ars_source_mode: str | None = None,
    ars_version: str | None = None,
) -> list[str]:
    results: list[str] = []
    if dry_run:
        if not env_file.exists():
            results.append(f"would create env template at {env_file}")
    elif ensure_env_template(env_file):
        results.append(f"created env template at {env_file}")
    if skill_agents:
        results.append(ensure_agents_home(ars_source, dry_run, replace_skills))
    for agent in skill_agents:
        results.append(install_skill(agent, ars_source, replace_skills, dry_run))
    for agent in mcp_agents:
        if agent == "claude":
            results.append(merge_claude_config(env_file, dry_run, replace_mcp))
        elif agent == "codex":
            results.append(merge_codex_config(env_file, dry_run, replace_mcp))
        elif agent == "zed":
            results.append(merge_zed_config(env_file, dry_run, replace_mcp))
        else:
            results.append(merge_json_config(agent, env_file, dry_run, replace_mcp))
    if not dry_run:
        save_config(
            ToolkitConfig(
                ars_source=str(ars_source),
                ars_source_mode=ars_source_mode,
                ars_version=ars_version,
                env_file=str(env_file),
                installed_skill_agents=skill_agents,
                installed_mcp_agents=mcp_agents,
            )
        )
    return results


def verify_skill(agent: str, ars_source: Path | None) -> tuple[bool, str]:
    if agent == "zed":
        return is_canonical_skill_ready(ars_source)
    target = SKILL_TARGETS[agent]
    if not target.is_symlink():
        return False, f"missing skill symlink at {target}"
    if target.resolve() != CANONICAL_SKILL_DIR:
        return False, f"skill symlink points to {target.resolve()} instead of {CANONICAL_SKILL_DIR}"
    ok, detail = is_canonical_skill_ready(ars_source)
    return (ok, f"skill symlink installed; {detail}")


def verify_mcp(agent: str) -> tuple[bool, str]:
    if agent == "claude":
        if not CLAUDE_MCP_PATH.exists():
            return False, f"missing {CLAUDE_MCP_PATH}"
        try:
            json.loads(CLAUDE_MCP_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return False, "invalid JSON"
        return True, "Claude MCP config present"
    if agent == "codex":
        path = Path.home() / ".codex" / "config.toml"
        if not path.exists():
            return False, "missing ~/.codex/config.toml"
        text = path.read_text(encoding="utf-8")
        return (SERVER_NAME in text, "managed Codex block present" if SERVER_NAME in text else "managed Codex block missing")
    path, top_key = JSON_TARGETS[agent]
    if not path.exists():
        return False, f"missing {path}"
    if agent == "zed":
        text = path.read_text(encoding="utf-8")
        return (SERVER_NAME in text, "paper-search-mcp entry found in JSONC" if SERVER_NAME in text else "paper-search-mcp entry missing")
    try:
        data = load_json(path)
    except json.JSONDecodeError as exc:
        return False, f"invalid JSON: {exc}"
    return (SERVER_NAME in data.get(top_key, {}), f"{SERVER_NAME} found" if SERVER_NAME in data.get(top_key, {}) else f"{SERVER_NAME} missing")


def is_managed_skill(agent: str) -> bool:
    target = SKILL_TARGETS[agent]
    if agent == "zed":
        return is_canonical_skill_ready()[0]
    if target.is_symlink():
        return target.resolve() == CANONICAL_SKILL_DIR
    skill_file = target / "SKILL.md"
    if agent not in SKILL_TEMPLATES or not skill_file.exists():
        return False
    expected = SKILL_TEMPLATES[agent].strip() + "\n"
    try:
        return skill_file.read_text(encoding="utf-8") == expected
    except OSError:
        return False


def uninstall_skill(agent: str, dry_run: bool) -> str:
    target = SKILL_TARGETS[agent]
    if agent == "zed":
        return "Zed uses the shared global .agents skill; it is removed after agent symlinks"
    if not target.exists() and not target.is_symlink():
        return f"skill adapter for {agent} was not installed"
    if not is_managed_skill(agent):
        return f"skipped non-managed skill for {agent}"
    if dry_run:
        return f"would remove skill adapter for {agent} from {target}"
    if target.is_symlink() or target.is_file():
        target.unlink()
    else:
        shutil.rmtree(target)
    return f"removed skill adapter for {agent}"


def remove_agents_home(dry_run: bool) -> str:
    if not CANONICAL_SKILL_DIR.exists() and not CANONICAL_SKILL_DIR.is_symlink():
        return "global .agents skill was not installed"
    if not is_canonical_skill_ready()[0]:
        return f"skipped non-managed global .agents skill at {CANONICAL_SKILL_DIR}"
    if dry_run:
        return f"would remove global .agents skill at {CANONICAL_SKILL_DIR}"
    shutil.rmtree(CANONICAL_SKILL_DIR)
    if AGENTS_GLOBAL_FILE.exists():
        begin = "<!-- BEGIN academic-agent-toolkit -->"
        end = "<!-- END academic-agent-toolkit -->"
        current = AGENTS_GLOBAL_FILE.read_text(encoding="utf-8")
        if begin in current and end in current:
            before, rest = current.split(begin, 1)
            _, after = rest.split(end, 1)
            next_text = (before.rstrip() + "\n\n" + after.lstrip("\n")).strip() + "\n"
            if next_text.strip():
                AGENTS_GLOBAL_FILE.write_text(next_text, encoding="utf-8")
            else:
                AGENTS_GLOBAL_FILE.unlink()
    return f"removed global .agents skill at {CANONICAL_SKILL_DIR}"


def remove_json_config(agent: str, env_file: Path, dry_run: bool) -> str:
    path, top_key = JSON_TARGETS[agent]
    if not path.exists():
        return f"MCP config for {agent} was not installed"
    try:
        data = load_json_or_jsonc(path) if agent == "zed" else load_json(path)
    except json.JSONDecodeError as exc:
        return f"MCP config for {agent} was not installed"
    servers = data.get(top_key, {})
    if SERVER_NAME not in servers:
        return f"MCP config for {agent} was not installed"
    if servers[SERVER_NAME] != json_server(agent, env_file):
        return f"skipped non-managed MCP config for {agent}"
    if dry_run:
        return f"would remove MCP config for {agent} from {path}"
    del servers[SERVER_NAME]
    backup(path)
    write_json(path, data)
    return f"removed MCP config for {agent}"


def remove_codex_config(dry_run: bool) -> str:
    path = Path.home() / ".codex" / "config.toml"
    begin = f"# BEGIN academic-agent-toolkit:{SERVER_NAME}"
    end = f"# END academic-agent-toolkit:{SERVER_NAME}"
    if not path.exists():
        return "MCP config for codex was not installed"
    current = path.read_text(encoding="utf-8")
    if begin not in current or end not in current:
        return "skipped non-managed MCP config for codex"
    before, rest = current.split(begin, 1)
    _, after = rest.split(end, 1)
    next_text = before.rstrip() + "\n" + after.lstrip("\n")
    if dry_run:
        return f"would remove MCP config for codex from {path}"
    backup(path)
    path.write_text(next_text, encoding="utf-8")
    return "removed MCP config for codex"


def uninstall_all(
    *,
    config: ToolkitConfig,
    dry_run: bool,
    remove_env: bool,
    remove_managed_ars: bool,
) -> list[str]:
    results: list[str] = []
    skill_agents = config.installed_skill_agents or list(SKILL_TARGETS)
    mcp_agents = config.installed_mcp_agents or ["claude", "codex", *JSON_TARGETS]
    env_file = config.env_file_path or DEFAULT_ENV_FILE
    for agent in skill_agents:
        if agent in SKILL_TARGETS:
            results.append(uninstall_skill(agent, dry_run))
    results.append(remove_agents_home(dry_run))
    for agent in mcp_agents:
        if agent == "claude":
            if CLAUDE_MCP_PATH.exists():
                if dry_run:
                    results.append(f"would remove Claude MCP config from {CLAUDE_MCP_PATH}")
                else:
                    backup(CLAUDE_MCP_PATH)
                    CLAUDE_MCP_PATH.unlink()
                    results.append(f"removed Claude MCP config")
            else:
                results.append("Claude MCP config was not installed")
        elif agent == "codex":
            results.append(remove_codex_config(dry_run))
        elif agent == "zed":
            results.append(remove_zed_config(env_file, dry_run))
        elif agent in JSON_TARGETS:
            results.append(remove_json_config(agent, env_file, dry_run))
    if remove_env and env_file.exists():
        if dry_run:
            results.append(f"would remove env file at {env_file}")
        else:
            env_file.unlink()
            results.append(f"removed env file at {env_file}")
    if remove_managed_ars:
        managed = managed_ars_source_path()
        if managed.exists():
            if dry_run:
                results.append(f"would remove managed ARS source at {managed}")
            else:
                shutil.rmtree(managed)
                results.append(f"removed managed ARS source at {managed}")
    if not dry_run:
        save_config(ToolkitConfig(env_file=str(env_file) if env_file.exists() else None))
    return results


def self_check(config: ToolkitConfig | None = None) -> list[CheckResult]:
    current = config or ToolkitConfig()
    results = [
        CheckResult(
            "Python",
            sys.version_info >= (3, 11),
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        ),
        CheckResult("uv", shutil.which("uv") is not None, shutil.which("uv") or "not found in PATH"),
    ]
    source = discover_ars_source(current)
    if source:
        ok, detail = validate_ars_source(source)
        results.append(CheckResult("ARS source", ok, f"{source} ({detail})"))
    else:
        results.append(CheckResult("ARS source", True, f"not installed yet; AAT can bootstrap {MANAGED_ARS_VERSION}"))
    env_file = current.env_file_path or DEFAULT_ENV_FILE
    if env_file.exists():
        text = env_file.read_text(encoding="utf-8", errors="ignore")
        configured = "you@example.com" not in text
        results.append(CheckResult("Paper Search env", configured, f"{env_file}" + ("" if configured else " contains starter placeholders")))
    else:
        results.append(CheckResult("Paper Search env", False, f"missing {env_file}; install will create a template"))
    detected = [agent.name for agent in detect_agents() if agent.detected]
    results.append(CheckResult("Agent detection", bool(detected), ", ".join(detected) if detected else "no supported agent config dirs found"))
    return results


def doctor_summary(config: ToolkitConfig | None = None) -> dict:
    current = config or ToolkitConfig()
    ars_source = discover_ars_source(current)
    ars_valid = validate_ars_source(ars_source)[0] if ars_source else False
    env_file = current.env_file_path or DEFAULT_ENV_FILE
    managed_ars_source = managed_ars_source_path()
    return {
        "ars_source": ars_source,
        "ars_valid": ars_valid,
        "managed_ars_source": managed_ars_source,
        "managed_ars_exists": managed_ars_source.exists(),
        "ars_ref": MANAGED_ARS_VERSION,
        "env_file": env_file,
        "env_exists": env_file.exists(),
        "agents": detect_agents(),
    }
