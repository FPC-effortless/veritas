from investigation_world.operational.cli import app
from investigation_world.operational.env_cli import env_app


def test_veritas_root_registers_environment_command_group() -> None:
    group_names = {group.name for group in app.registered_groups}
    command_names = {command.name for command in env_app.registered_commands}

    assert "env" in group_names
    assert {"compile", "validate", "export", "conformance", "reverify"}.issubset(command_names)
