"""Every application image must declare a non-root USER.

Root-in-container removes the last containment layer: a container escape via
a runtime or kernel CVE lands as root on the Hetzner node.
"""

from pathlib import Path

import pytest

DOCKERFILES = [
    "Dockerfile.mcp",
    "Dockerfile.api",
    "Dockerfile.workers",
    "Dockerfile.pipeline",
    "src/uvo-gui-react/Dockerfile",
]


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
