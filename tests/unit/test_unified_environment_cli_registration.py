from typer.testing import CliRunner

from investigation_world.operational.cli import app


runner = CliRunner()


def test_veritas_root_registers_environment_command_group() -> None:
    result = runner.invoke(app, ["env", "--help"])

    assert result.exit_code == 0
    assert "compile" in result.stdout
    assert "validate" in result.stdout
    assert "export" in result.stdout
    assert "conformance" in result.stdout
    assert "reverify" in result.stdout
