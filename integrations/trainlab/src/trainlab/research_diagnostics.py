"""Trusted, single-thread diagnostic SDK; no automatic scientific qualification."""
from __future__ import annotations

import copy
import platform
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter_ns

from .runner import LabError, _finite, write_json

PHASES = {"setup", "preprocess", "load", "encode", "update", "retrieve", "answer",
          "decode", "verify", "persist"}


def _require(value, message):
    if not value:
        raise LabError(message)


def _name(value):
    _require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", value),
             "bounded diagnostic identifier required")


def _text(value):
    return isinstance(value, str) and 0 < len(value.strip()) <= 2000


class BudgetExceeded(LabError):
    """Cooperative call-boundary limit; not preemption of an active operation."""


@dataclass(frozen=True)
class Adapter:
    name: str
    operations: dict
    state_semantics: dict
    asynchronous: bool = False


@dataclass(frozen=True)
class Diagnostic:
    name: str
    version: str
    requires: tuple
    check: object
    scope: str


class Workbench:
    """Run declared checks, retaining incomplete evidence before each operation.

    Adapters/checks are trusted local code. Inputs/outputs and exception messages
    are not copied into this report. Check summaries/metrics remain caller-owned.
    Use a TrainLab recipe timeout for process supervision; this SDK cannot kill a
    hanging callback, meter remote billing or enforce RAM/GPU quotas.
    """

    def __init__(self, adapter, identities, root, *, max_calls=100, max_seconds=30,
                 required_phases=("answer",)):
        _name(adapter.name)
        _require(isinstance(adapter.operations, dict) and len(adapter.operations) <= 64,
                 "bounded adapter operations required")
        for key, operation in adapter.operations.items():
            _name(key)
            _require(callable(operation), "adapter capabilities must be callable")
        state = adapter.state_semantics
        _require(isinstance(state, dict) and set(state) == {"persists", "query_mutates", "reset"}
                 and _text(state["persists"]) and _text(state["reset"])
                 and type(state["query_mutates"]) is bool
                 and type(adapter.asynchronous) is bool, "explicit state semantics required")
        _require(isinstance(identities, dict)
                 and set(identities) == {"model", "dataset", "code", "configuration"}
                 and all(isinstance(v, str) and re.fullmatch("[0-9a-f]{64}", v)
                         for v in identities.values()), "four SHA256 identities required")
        _require(type(max_calls) is int and 1 <= max_calls <= 10000
                 and _finite(max_seconds) and 0 < max_seconds <= 86400,
                 "bounded positive call/time budget required")
        _require(isinstance(required_phases, (tuple, list)) and required_phases
                 and all(isinstance(p, str) and p in PHASES for p in required_phases)
                 and len(set(required_phases)) == len(required_phases), "invalid required phases")
        self.adapter = Adapter(adapter.name, dict(adapter.operations), copy.deepcopy(state),
                               adapter.asynchronous)
        self.root = Path(root).resolve()
        self.max_calls, self.max_seconds = max_calls, max_seconds
        self.required_phases = list(required_phases)
        self.started = None
        self.owner = threading.get_ident()
        self.active = False
        self.closed = False
        self.current = None
        self.exhausted = None
        self.report = {
            "schema": "trainlab.research_diagnostics.v1", "state": "PARTIAL",
            "identities": dict(identities), "identity_scope": "DECLARED_RECIPE_OR_ARTIFACT_HASHES",
            "adapter": {"name": adapter.name, "capabilities": sorted(adapter.operations),
                        "state_semantics": copy.deepcopy(state),
                        "asynchronous": adapter.asynchronous},
            "coverage": [], "attempts": [],
            "budget": {"max_calls": max_calls, "max_seconds": max_seconds,
                       "enforcement": "COOPERATIVE_BETWEEN_CALLS_NOT_HARD_PREEMPTION"},
            "runtime": {"python": platform.python_version(), "system": platform.system(),
                        "machine": platform.machine(), "processor": platform.processor(),
                        "device_identity": "NOT_ATTESTED"},
            "scientific_qualification": "NOT_QUALIFIED",
        }

    def _elapsed(self):
        return (perf_counter_ns() - self.started) / 1_000_000_000

    def _expire(self):
        if self._elapsed() >= self.max_seconds:
            self.exhausted = "WALL_TIME"

    def _save(self):
        elapsed = self._elapsed()
        if elapsed >= self.max_seconds:
            self.exhausted = "WALL_TIME"
        attempts = self.report["attempts"]
        completed = {a["phase"] for a in attempts if a["status"] == "SUCCEEDED"}
        missing = sorted(set(self.required_phases) - completed)
        sync_ok = not self.adapter.asynchronous or "synchronize" in self.adapter.operations
        self.report["session"] = {
            "elapsed_seconds": elapsed, "clock": "perf_counter_ns_host_wall",
            "aggregation": "DIRECT_SESSION_INTERVAL_NOT_SUM_OF_SPANS",
            "cost_coverage": "MEASURED" if self.report["state"] == "COMPLETE"
            and not missing and not self.exhausted and sync_ok
            and not any(a["sync_error"] for a in attempts)
            else "INCOMPLETE",
            "required_phases": self.required_phases, "missing_successful_phases": missing,
            "device_completion": "CALLER_SYNCHRONIZER" if "synchronize" in
            self.adapter.operations else "UNVERIFIED_ASYNC" if self.adapter.asynchronous
            else "DECLARED_SYNCHRONOUS",
            "scope": "AFTER_CATALOG_VALIDATION_AND_ROOT_CREATION_THROUGH_CHECK_COMPLETION",
            "excludes": ["adapter_construction", "caller_prework", "catalog_validation",
                         "output_directory_creation", "final_report_serialization"],
            "memory": "NOT_MEASURED", "energy": "NOT_MEASURED", "money": "NOT_MEASURED",
            "budget_exhausted": self.exhausted,
        }
        write_json(self.root / "report.json", self.report)

    def invoke(self, capability, *args, phase, retry_of=None, condition="unspecified", **kwargs):
        _require(self.started is not None and not self.closed and self.current is not None
                 and threading.get_ident() == self.owner and not self.active,
                 "operations require an active single-thread check; nesting is unsupported")
        _require(capability in self.adapter.operations and capability != "synchronize"
                 and phase in PHASES and condition in ("cold", "warm", "unspecified"),
                 "unsupported operation, phase or condition")
        if self.exhausted or len(self.report["attempts"]) >= self.max_calls or \
                self._elapsed() >= self.max_seconds:
            self.exhausted = self.exhausted or (
                "CALLS" if len(self.report["attempts"]) >= self.max_calls else "WALL_TIME")
            raise BudgetExceeded("diagnostic operation budget exhausted")
        attempts = self.report["attempts"]
        if retry_of is not None:
            _require(type(retry_of) is int and 0 <= retry_of < len(attempts)
                     and attempts[retry_of]["status"] == "FAILED"
                     and attempts[retry_of]["capability"] == capability
                     and attempts[retry_of]["phase"] == phase,
                     "retry must reference an earlier failed matching operation")
        row = {"id": len(attempts), "diagnostic": self.current, "capability": capability,
               "phase": phase, "condition": condition, "retry_of": retry_of, "status": "STARTED",
               "start_seconds": self._elapsed(), "end_seconds": None,
               "elapsed_seconds": None, "error_type": None, "sync_error": False}
        attempts.append(row)
        self._save()  # Durable intent before callbacks or device synchronization.
        self.active = True
        sync = self.adapter.operations.get("synchronize")
        stage = "pre_sync"
        try:
            self._expire()
            if self.exhausted:
                raise BudgetExceeded("time exhausted while retaining attempt intent")
            if sync:
                sync()
            self._expire()
            if self.exhausted:
                raise BudgetExceeded("time exhausted before operation callback")
            stage = "operation"
            result = self.adapter.operations[capability](*args, **kwargs)
            stage = "post_sync"
            if sync:
                sync()
            row["status"] = "SUCCEEDED"
            return result
        except BaseException as exc:
            cancelled = isinstance(exc, BudgetExceeded) and stage == "pre_sync"
            row["status"] = "BUDGET_CANCELLED" if cancelled else (
                "FAILED" if isinstance(exc, Exception) else "INTERRUPTED")
            row["error_type"] = type(exc).__name__
            row["sync_error"] = stage != "operation" and not cancelled
            # Drain failed async work without replacing the original exception.
            if sync and stage == "operation":
                try:
                    sync()
                except BaseException:
                    row["sync_error"] = True
            raise
        finally:
            self.active = False
            row["end_seconds"] = self._elapsed()
            row["elapsed_seconds"] = row["end_seconds"] - row["start_seconds"]
            self._save()

    def run(self, diagnostics, *, selected=None):
        _require(self.started is None and threading.get_ident() == self.owner,
                 "a workbench is single-use and single-thread")
        _require(isinstance(diagnostics, (tuple, list)) and 1 <= len(diagnostics) <= 128,
                 "bounded diagnostic catalog required")
        names = []
        for check in diagnostics:
            _name(check.name)
            _name(check.version)
            _require(check.name not in names and callable(check.check) and _text(check.scope)
                     and isinstance(check.requires, tuple) and len(check.requires) <= 64,
                     "invalid or duplicate diagnostic")
            for capability in check.requires:
                _name(capability)
            _require(len(set(check.requires)) == len(check.requires), "duplicate capability")
            names.append(check.name)
        selected = names if selected is None else selected
        _require(isinstance(selected, (list, tuple)) and all(n in names for n in selected)
                 and len(set(selected)) == len(selected), "unknown or duplicate selected check")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.started = perf_counter_ns()
        for check in diagnostics:
            missing = sorted(set(check.requires) - set(self.adapter.operations))
            self.report["coverage"].append({
                "name": check.name, "version": check.version, "scope": check.scope,
                "requires": list(check.requires), "status": "NOT_RUN",
                "reason": "NOT_SELECTED" if check.name not in selected else "PENDING",
                "missing_capabilities": missing, "observation": None,
            })
        self._save()
        try:
            for check, row in zip(diagnostics, self.report["coverage"]):
                self._expire()
                if check.name not in selected:
                    continue
                if row["missing_capabilities"]:
                    row.update(status="UNSUPPORTED", reason="MISSING_CAPABILITY")
                elif self.exhausted:
                    row["reason"] = "BUDGET_EXHAUSTED"
                else:
                    self.current = check.name
                    row.update(status="INCONCLUSIVE", reason="IN_PROGRESS")
                    self._save()
                    try:
                        self._expire()
                        if self.exhausted:
                            raise BudgetExceeded("time exhausted before diagnostic callback")
                        outcome = check.check(self)
                        self._expire()
                        _require(isinstance(outcome, dict)
                                 and set(outcome) == {"status", "summary", "metrics"}
                                 and outcome["status"] in ("TESTED", "FAILED", "INCONCLUSIVE")
                                 and _text(outcome["summary"])
                                 and isinstance(outcome["metrics"], dict)
                                 and len(outcome["metrics"]) <= 64,
                                 "invalid diagnostic observation")
                        for metric, value in outcome["metrics"].items():
                            _name(metric)
                            _require(_finite(value), "finite scalar diagnostic metric required")
                        row.update(status=outcome["status"], reason="OBSERVED",
                                   observation=copy.deepcopy(outcome))
                    except Exception as exc:
                        row.update(status="INCONCLUSIVE", reason=type(exc).__name__)
                    finally:
                        self.current = None
                    if self.exhausted:
                        row.update(status="INCONCLUSIVE", reason="BUDGET_EXHAUSTED")
                self._save()
            self.report["state"] = "COMPLETE"
        finally:
            self.closed = True
            self._save()
        return copy.deepcopy(self.report)
