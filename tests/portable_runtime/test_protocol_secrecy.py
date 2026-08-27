from investigation_world.portable_runtime import PortableRuntimeProtocol

from test_portable_runtime import _runtime


def test_runtime_protocol_does_not_expose_full_evaluator_contract() -> None:
    runtime = _runtime()

    assert "contract" not in PortableRuntimeProtocol.__dict__
    assert not hasattr(runtime, "contract")


def test_runtime_protocol_surface_is_limited_to_portable_operations() -> None:
    public_operations = {
        "reset",
        "step",
        "verify",
        "submit",
        "public_state",
        "state_digest",
        "budget_state",
    }

    declared = {
        name
        for name in PortableRuntimeProtocol.__dict__
        if not name.startswith("_")
    }
    assert declared == public_operations
