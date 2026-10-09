"""Edge branches for fakzed-server internals: tenancy, persistence, registry, runs."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from fakzed.observability.metrics import MetricsCollector, RunMetrics
from fakzed_server.monitoring import MonitoringStore
from fakzed_server.persistence import JsonStore
from fakzed_server.registry import AgentRegistry
from fakzed_server.runs import RunManager
from fakzed_server.tenancy import TenantStore

# -- tenancy -------------------------------------------------------------------


def test_tenancy_errors_and_queries() -> None:
    tm = TenantStore()
    org = tm.create_org("org1", owner_id="u1")

    with pytest.raises(KeyError, match="unknown organization"):
        tm.create_project("missing", "p")

    with pytest.raises(KeyError, match="unknown organization"):
        tm.add_member("missing", "u2")

    tm.add_member(org.org_id, "u2", role="admin")
    project = tm.create_project(org.org_id, "p1")

    assert tm.projects_of(org.org_id) == [project]
    assert [o.org_id for o in tm.orgs_of("u1")] == [org.org_id]
    assert tm.role_in("u2", org.org_id) == "admin"
    assert tm.role_in("nobody", org.org_id) is None
    assert tm.projects_of("unknown") == []


# -- persistence ---------------------------------------------------------------


def test_json_store_corrupt_file_and_pop(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    store = JsonStore(path=bad)
    assert store.get("x") is None

    good = tmp_path / "good.json"
    store = JsonStore(path=good)
    store.put("k", {"v": 1})
    assert store.pop("k") == {"v": 1}
    assert store.get("k") is None


# -- registry ------------------------------------------------------------------


def test_registry_edges() -> None:
    reg = AgentRegistry()

    with pytest.raises(ValueError, match="requires a name"):
        reg.register(SimpleNamespace(name=None))

    reg.register(SimpleNamespace(name="a"), project_id="p1")
    reg.register(SimpleNamespace(name="b"), project_id="p2")

    assert [e.name for e in reg.list()] == ["a", "b"]
    assert [e.name for e in reg.list(project_id="p1")] == ["a"]
    assert reg.unregister("a") is True
    assert reg.unregister("a") is False


# -- runs ----------------------------------------------------------------------


def test_run_manager_factory_not_wired() -> None:
    rm = RunManager(agent_factory=None)
    with pytest.raises(RuntimeError, match="not wired"):
        rm._call("a", "hi", None, False)  # noqa: SLF001


def test_run_manager_sets_session_id() -> None:
    class _Agent:
        session_id: str | None = None

        def run(self, message: str, stop_after_tool_call: bool = False) -> str:  # noqa: ARG002
            return "done"

    instance = _Agent()

    def factory(name: str) -> _Agent:  # noqa: ARG001
        return instance

    rm = RunManager(agent_factory=factory)
    result = rm._call("a", "hi", "sess-1", False)  # noqa: SLF001

    assert result == "done"
    assert instance.session_id == "sess-1"


def test_run_manager_wait_timeout() -> None:
    rm = RunManager(agent_factory=None)
    assert rm.wait("unknown-run", timeout=0.01) is None


# -- monitoring + metrics ------------------------------------------------------


def test_monitoring_cost_by_agent() -> None:
    m = MonitoringStore(
        metrics=MetricsCollector(
            metrics=[
                RunMetrics(agent_name="a", cost_usd=0.5),
                RunMetrics(agent_name="a", cost_usd=0.25),
                RunMetrics(agent_name=None, cost_usd=99.0),
            ]
        )
    )

    assert m.cost_by_agent() == {"a": 0.75}


def test_metrics_collector_cap_get_export() -> None:
    collector = MetricsCollector(max_metrics=2)
    runs = [RunMetrics(cost_usd=float(i)) for i in range(5)]
    for run in runs:
        collector.record(run)

    # capped at max_metrics (keeps the most recent)
    assert len(collector.all()) == 2
    assert collector.get(runs[4].run_id) is not None
    assert collector.get("missing") is None

    exported = collector.export_json()
    assert exported.startswith("[") and exported.endswith("]")
