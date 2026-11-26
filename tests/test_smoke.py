from typer.testing import CliRunner

import ctxbook
from ctxbook.cli.main import app


def test_version_flag_prints_package_version() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == f"ctxbook {ctxbook.__version__}"
