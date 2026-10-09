"""Smoke test: verify the package is importable and versioned."""

from fakzed import __version__


def test_version() -> None:
    assert __version__ == "0.1.0"


def test_import_submodules() -> None:
    from fakzed import (  # noqa: F401  # noqa: F401
        agent,
        evals,
        knowledge,
        memory,
        model,
        observability,
        session,
        storage,
        team,
        tools,
        workflow,
    )

    assert agent is not None
    assert team is not None
    assert workflow is not None
    assert model is not None
    assert tools is not None
    assert memory is not None
    assert knowledge is not None
    assert session is not None
    assert storage is not None
    assert observability is not None
    assert evals is not None
