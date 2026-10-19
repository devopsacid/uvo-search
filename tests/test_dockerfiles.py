"""Every application image must declare a non-root USER.

Root-in-container removes the last containment layer: a container escape via
a runtime or kernel CVE lands as root on the Hetzner node.

The four Python images are targets of one multi-stage ``Dockerfile``; the GUI
image has its own.
"""

import re
from pathlib import Path

import pytest

PYTHON_TARGETS = ["mcp", "api", "workers", "pipeline"]
DOCKERFILES = ["Dockerfile", "src/uvo-gui-react/Dockerfile"]


def _stages(content: str) -> dict[str, list[str]]:
    """Map stage name -> its stripped lines (FROM line included)."""
    stages: dict[str, list[str]] = {}
    current = None
    for raw in content.splitlines():
        line = raw.strip()
        m = re.match(r"FROM\s+\S+\s+AS\s+(\S+)", line, re.IGNORECASE)
        if m:
            current = m.group(1)
            stages[current] = []
        if current is not None:
            stages[current].append(line)
    return stages


@pytest.mark.parametrize("name", DOCKERFILES)
def test_declares_non_root_user(name):
    content = Path(name).read_text(encoding="utf-8")
    user_lines = [ln.strip() for ln in content.splitlines() if ln.strip().startswith("USER ")]
    assert user_lines, f"{name} does not declare a USER; it runs as root"
    final_user = user_lines[-1].split(None, 1)[1].strip()
    assert final_user not in ("root", "0"), f"{name} ends as root"


@pytest.mark.parametrize("name", DOCKERFILES)
def test_user_is_last_privileged_step(name):
    """USER must come after package installs, or the build fails on permissions."""
    content = Path(name).read_text(encoding="utf-8")
    lines = [ln.strip() for ln in content.splitlines()]
    user_idx = max(i for i, ln in enumerate(lines) if ln.startswith("USER "))
    installs = [i for i, ln in enumerate(lines) if "uv sync" in ln or "apt-get install" in ln]
    assert all(i < user_idx for i in installs), (
        f"{name} installs packages after dropping privileges"
    )


@pytest.mark.parametrize("target", PYTHON_TARGETS)
def test_python_target_runs_as_uid_10001(target):
    stage = _stages(Path("Dockerfile").read_text(encoding="utf-8"))[target]
    users = [ln for ln in stage if ln.startswith("USER ")]
    assert users and users[-1].split()[1] == "10001", f"target {target} must end as uid 10001"


@pytest.mark.parametrize("target", PYTHON_TARGETS)
def test_python_target_has_second_sync_after_copy(target):
    """First-party packages only land in the venv if uv sync runs after COPY src/.

    See CLAUDE.md "CI & Docker image gotchas": a build that succeeds proves nothing
    about whether the app starts.
    """
    stage = _stages(Path("Dockerfile").read_text(encoding="utf-8"))[f"build-{target}"]
    copy_idx = max(i for i, ln in enumerate(stage) if ln.startswith("COPY src/"))
    sync_idx = [i for i, ln in enumerate(stage) if "uv sync --frozen --no-dev" in ln]
    assert sync_idx and sync_idx[-1] > copy_idx, f"build-{target} must uv sync after COPY src/"


def test_uv_image_is_pinned():
    content = Path("Dockerfile").read_text(encoding="utf-8")
    assert ":latest" not in content
    assert "ghcr.io/astral-sh/uv:${UV_VERSION}" in content
