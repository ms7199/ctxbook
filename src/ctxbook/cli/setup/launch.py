"""The command AI clients run to start ctxbook.

Always ``<absolute uvx> --managed-python --python 3.12 --from <source> ctxbook serve``:
- absolute path, because clients may start servers with a different PATH (CLAUDE.md section 10);
- uv-managed Python 3.12, because some Pythons cannot load SQLite extensions and Intel Macs
  have no embedding runtime for Python 3.14+ (decision D17);
- ``--from`` the same place this ctxbook was installed from (PyPI, git or a local folder).
"""

import json
import shlex
import subprocess
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, distribution
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from ctxbook.errors import CtxbookError

PACKAGE = "ctxbook"
SERVER_PYTHON = "3.12"


class UvNotFoundError(CtxbookError):
    """uvx is needed to start the server from AI clients."""


def detect_source(direct_url_json: str | None) -> str:
    """Turn PEP 610 ``direct_url.json`` into a ``uvx --from`` value."""
    if not direct_url_json:
        return PACKAGE
    info = json.loads(direct_url_json)
    url = str(info.get("url", ""))
    if "vcs_info" in info:
        vcs = info["vcs_info"].get("vcs", "git")
        return url if url.startswith(f"{vcs}+") else f"{vcs}+{url}"
    if "dir_info" in info and url.startswith("file:"):
        return url2pathname(unquote(urlparse(url).path))
    return url or PACKAGE


def current_source() -> str:
    try:
        return detect_source(distribution(PACKAGE).read_text("direct_url.json"))
    except PackageNotFoundError:
        return PACKAGE


def server_command(uvx: str, source: str, *, no_embeddings: bool) -> list[str]:
    command = [uvx, "--managed-python", "--python", SERVER_PYTHON, "--from", source]
    command += [PACKAGE, "serve"]
    if no_embeddings:
        command.append("--no-embeddings")
    return command


def find_uvx(which: Callable[[str], str | None]) -> str:
    path = which("uvx")
    if not path:
        raise UvNotFoundError(
            "uvx was not found. ctxbook's AI-client setup uses uv to start the server; install "
            "it from https://docs.astral.sh/uv/getting-started/installation/ and run init again."
        )
    return str(path)


def display(command: list[str], system: str) -> str:
    """A copy-pasteable form of ``command`` for this OS's shell."""
    if system == "Windows":
        return subprocess.list2cmdline(command)
    return shlex.join(command)
