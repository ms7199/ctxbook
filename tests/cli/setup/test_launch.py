import json

import pytest

from ctxbook.cli.setup.launch import (
    UvNotFoundError,
    detect_source,
    display,
    find_uvx,
    server_command,
)


@pytest.mark.parametrize(
    ("direct_url", "expected"),
    [
        (None, "ctxbook"),  # installed from PyPI: no direct_url.json
        ({"url": "file:///Users/me/ctxbook", "dir_info": {"editable": True}}, "/Users/me/ctxbook"),
        (
            {"url": "https://github.com/ms7199/ctxbook", "vcs_info": {"vcs": "git"}},
            "git+https://github.com/ms7199/ctxbook",
        ),
        (
            {"url": "git+https://github.com/ms7199/ctxbook", "vcs_info": {"vcs": "git"}},
            "git+https://github.com/ms7199/ctxbook",
        ),
        (
            {"url": "https://example.com/ctxbook-0.1.0.tar.gz", "archive_info": {}},
            "https://example.com/ctxbook-0.1.0.tar.gz",
        ),
    ],
)
def test_detect_source(direct_url: dict[str, object] | None, expected: str) -> None:
    assert detect_source(json.dumps(direct_url) if direct_url else None) == expected


def test_server_command_uses_managed_python_312() -> None:
    assert server_command("/bin/uvx", "ctxbook", no_embeddings=False) == [
        "/bin/uvx",
        "--managed-python",
        "--python",
        "3.12",
        "--from",
        "ctxbook",
        "ctxbook",
        "serve",
    ]
    assert server_command("/bin/uvx", "ctxbook", no_embeddings=True)[-1] == "--no-embeddings"


def test_missing_uvx_is_explained() -> None:
    with pytest.raises(UvNotFoundError, match=r"docs\.astral\.sh/uv"):
        find_uvx(lambda _name: None)


def test_display_quotes_paths_with_spaces() -> None:
    command = ["/Users/a b/uvx", "serve"]
    assert display(command, "Darwin") == "'/Users/a b/uvx' serve"
    assert display(command, "Windows") == '"/Users/a b/uvx" serve'
