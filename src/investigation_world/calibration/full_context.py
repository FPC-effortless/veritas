from __future__ import annotations

import json
import re
from collections.abc import Callable
from statistics import mean
from typing import Any

from investigation_world.benchmark.policies import PublicEvidenceReferencePolicy
from investigation_world.companyworld.dynamic_reference import run_dynamic_public_reference
from investigation_world.companyworld.dynamic_runtime import DynamicCompanyWorldRuntime
from investigation_world.companyworld.interactive_models import OperationalAction, OperationalActionType
from investigation_world.companyworld.interactive_reference import solve_interactive_public
from investigation_world.companyworld.interactive_runtime import InteractiveCompanyWorldRuntime
from investigation_world.companyworld.sequential_reference import solve_sequential_public
from investigation_world.companyworld.sequential_runtime import SequentialCompanyWorldRuntime
from investigation_world.companyworld.verifier import verify_companyworld
from investigation_world.core.models import InvestigationResult
from investigation_world.calibration.fixtures import (
    diagnostic_fixture,
    dynamic_fixture,
    interactive_fixture,
    sequential_fixture,
)

GenerateFn = Callable[[str], str]


def _json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S | re.I)
    candidates = [fenced.group(1)] if fenced else []
    first = text.find("{")
    last = text.rfind("}")
    if first >= 0 and last > first:
        candidates.append(text[first : last + 1])
    candidates.append(text)
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(value, dict):
            return value
    return {}


def _claims(payload: dict[str, Any], task: dict[str, Any]) -> InvestigationResult:
    raw_claims = payload.get("claims")
    claims: list[dict[str, Any]] = []
    if isinstance(raw_claims, list):
        for item in raw_claims:
            if not isinstance(item, dict):
                continue
            if "field_name" not in item or "value" not in item:
                continue
            claims.append(
                {
                    "object_type": item.get("object_type", task.get("target_object_type")),
                    "object_id": item.get("object_id", task.get("target_object_id")),
                    "field_name": item.get("field_name"),
                    "value": item.get("value"),
                }
            )
    evidence_ids = payload.get("evidence_record_ids") or []
    evidence = [
        {"record_id": str(record_id)}
        for record_id in evidence_ids
        if isinstance(record_id, (str, int))
    ]
    confidence = payload.get("confidence", payload.get("overall_confidence", 0.5))
    try:
        confidence_value = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        confidence_value = 0.5
    return InvestigationResult(
        claims=claims,
        evidence=evidence,
        conclusion=str(payload.get("conclusion", "")),
        overall_confidence=confidence_value,
    )


def _action(payload: dict[str, Any], task: dict[str, Any]) -> OperationalAction | None:
    raw = payload.get("action")
    if not isinstance(raw, dict):
        return None
    try:
        action_type = OperationalActionType(str(raw.get("action_type")))
    except (ValueError, TypeError):
        return None
    return OperationalAction(
        action_type=action_type,
        target_object_type=str(raw.get("target_object_type") or task["target_object_type"]),
        target_object_id=str(raw.get("target_object_id") or task["target_object_id"]),
        parameters=raw.get("parameters") if isinstance(raw.get("parameters"), dict) else {},
    )


def _step_action(step: dict[str, Any], task: dict[str, Any]) -> OperationalAction | None:
    raw = {
        "action_type": step.get("action_type"),
        "target_object_type": step.get("target_object_type"),
        "target_object_id": step.get("target_object_id"),
        "parameters": step.get("parameters", {}),
    }
    return _action({"action": raw}, task)


def _prompt(level: str, public_payload: dict[str, Any]) -> str:
    common = (
        "You are controlling a synthetic enterprise benchmark. Use only the PUBLIC_PAYLOAD below. "
        "Return exactly one JSON object and no prose. Do not invent record IDs. "
        "Claims must use field_name and value; cite supporting records in evidence_record_ids. "
    )
    if level == "diagnostic":
        schema = (
            'Return {"claims":[{"field_name":"...","value":...}],'
            '"evidence_record_ids":["..."],"confidence":0.0}. '
        )
    elif level == "interactive":
        schema = (
            'Return {"claims":[...],"evidence_record_ids":[...],"confidence":0.0,'
            '"action":{"action_type":"...","parameters":{}}}. '
            "Choose one available action that produces the correct operational outcome. "
        )
    elif level == "sequential":
        schema = (
            'Return {"claims":[...],"evidence_record_ids":[...],"confidence":0.0,'
            '"steps":[{"kind":"action","action_type":"...","parameters":{}},'
            '{"kind":"advance","ticks":1}]}. '
            "Plan the complete control workflow in prerequisite order, including approval when needed, "
            "delayed ticks, reconciliation, verification, and case closure. "
        )
    elif level == "dynamic":
        schema = (
            'Return {"case_results":{"CASE_ID":{"claims":[...],"evidence_record_ids":[...],'
            '"confidence":0.0}},"steps":[{"kind":"action","case_id":"...",'
            '"action_type":"...","parameters":{}},{"kind":"advance","ticks":1},'
            '{"kind":"handoff","case_id":"...","role":"..."}]}. '
            "Manage all concurrent cases. Respect shared-resource capacity, authority and deadlines. "
            "Approval outcomes are hidden, so the plan may include safe handoffs where appropriate. "
        )
    else:
        raise ValueError(level)
    return common + schema + "PUBLIC_PAYLOAD:\n" + json.dumps(public_payload, sort_keys=True, default=str)


def _score_diagnostic(generate: GenerateFn) -> tuple[list[float], int]:
    scores: list[float] = []
    parse_failures = 0
    for episode in diagnostic_fixture():
        output = _json_object(generate(_prompt("diagnostic", episode.public_payload())))
        if not output:
            parse_failures += 1
        result = _claims(output, episode.task.model_dump(mode="json"))
        scores.append(verify_companyworld(result, episode).overall_reward)
    return scores, parse_failures


def _score_interactive(generate: GenerateFn) -> tuple[list[float], int]:
    scores: list[float] = []
    parse_failures = 0
    for episode in interactive_fixture():
        public = episode.public_payload()
        output = _json_object(generate(_prompt("interactive", public)))
        if not output:
            parse_failures += 1
        result = _claims(output, episode.task.model_dump(mode="json"))
        runtime = InteractiveCompanyWorldRuntime(episode)
        action = _action(output, episode.task.model_dump(mode="json"))
        if action is not None:
            try:
                runtime.act(action)
            except (ValueError, KeyError):
                pass
        scores.append(runtime.submit(result).overall_reward)
    return scores, parse_failures


def _score_sequential(generate: GenerateFn) -> tuple[list[float], int]:
    scores: list[float] = []
    parse_failures = 0
    for episode in sequential_fixture():
        public = episode.public_payload()
        output = _json_object(generate(_prompt("sequential", public)))
        if not output:
            parse_failures += 1
        result = _claims(output, episode.task.model_dump(mode="json"))
        runtime = SequentialCompanyWorldRuntime(episode)
        steps = output.get("steps") if isinstance(output.get("steps"), list) else []
        for step in steps:
            if not isinstance(step, dict):
                continue
            kind = str(step.get("kind", "")).casefold()
            try:
                if kind == "advance":
                    runtime.advance(max(1, int(step.get("ticks", 1))))
                elif kind == "action":
                    action = _step_action(step, episode.task.model_dump(mode="json"))
                    if action is not None:
                        runtime.act(action)
            except (ValueError, KeyError, TypeError):
                continue
        scores.append(runtime.submit(result).overall_reward)
    return scores, parse_failures


def _score_dynamic(generate: GenerateFn) -> tuple[list[float], int]:
    scenario = dynamic_fixture()
    public = scenario.public_payload()
    output = _json_object(generate(_prompt("dynamic", public)))
    parse_failures = 0 if output else 1
    runtime = DynamicCompanyWorldRuntime(scenario)
    case_by_id = {item.case_id: item for item in scenario.cases}
    steps = output.get("steps") if isinstance(output.get("steps"), list) else []
    for step in steps:
        if not isinstance(step, dict):
            continue
        kind = str(step.get("kind", "")).casefold()
        try:
            if kind == "advance":
                runtime.advance(max(1, int(step.get("ticks", 1))))
                continue
            case_id = str(step.get("case_id", ""))
            if case_id not in case_by_id:
                continue
            if kind == "handoff":
                runtime.handoff(case_id, str(step.get("role", "")))
            elif kind == "action":
                task = case_by_id[case_id].sequential.task.model_dump(mode="json")
                action = _step_action(step, task)
                if action is not None:
                    runtime.act(case_id, action)
        except (ValueError, KeyError, TypeError):
            continue

    case_payloads = output.get("case_results") if isinstance(output.get("case_results"), dict) else {}
    results: dict[str, InvestigationResult] = {}
    for case_id, case in case_by_id.items():
        item = case_payloads.get(case_id) if isinstance(case_payloads, dict) else None
        item = item if isinstance(item, dict) else {}
        results[case_id] = _claims(item, case.sequential.task.model_dump(mode="json"))
    return [runtime.submit(results).overall_reward], parse_failures


def _stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "min": 0.0, "max": 0.0}
    return {
        "mean": round(mean(values), 6),
        "min": round(min(values), 6),
        "max": round(max(values), 6),
    }


def reference_anchors() -> dict[str, dict[str, float]]:
    diagnostic = []
    for episode in diagnostic_fixture():
        result = PublicEvidenceReferencePolicy()(episode.public_payload())
        diagnostic.append(verify_companyworld(result, episode).overall_reward)

    interactive = []
    for episode in interactive_fixture():
        runtime = InteractiveCompanyWorldRuntime(episode)
        result, action = solve_interactive_public(episode.public_payload())
        runtime.act(action)
        interactive.append(runtime.submit(result).overall_reward)

    sequential = []
    for episode in sequential_fixture():
        runtime = SequentialCompanyWorldRuntime(episode)
        result, plan = solve_sequential_public(episode.public_payload())
        for step in plan:
            if step.kind == "advance":
                runtime.advance(step.ticks)
            elif step.action is not None:
                runtime.act(step.action)
        sequential.append(runtime.submit(result).overall_reward)

    dynamic_runtime = DynamicCompanyWorldRuntime(dynamic_fixture())
    _, dynamic_score = run_dynamic_public_reference(dynamic_runtime, dynamic_runtime.public_task())
    return {
        "diagnostic": _stats(diagnostic),
        "interactive": _stats(interactive),
        "sequential": _stats(sequential),
        "dynamic": _stats([dynamic_score.overall_reward]),
    }


def empty_anchors() -> dict[str, dict[str, float]]:
    diagnostic = [verify_companyworld(InvestigationResult(), item).overall_reward for item in diagnostic_fixture()]

    interactive = []
    for episode in interactive_fixture():
        interactive.append(InteractiveCompanyWorldRuntime(episode).submit(InvestigationResult()).overall_reward)

    sequential = []
    for episode in sequential_fixture():
        sequential.append(SequentialCompanyWorldRuntime(episode).submit(InvestigationResult()).overall_reward)

    dynamic = DynamicCompanyWorldRuntime(dynamic_fixture()).submit({}).overall_reward
    return {
        "diagnostic": _stats(diagnostic),
        "interactive": _stats(interactive),
        "sequential": _stats(sequential),
        "dynamic": _stats([dynamic]),
    }


def run_full_context_calibration(
    generate: GenerateFn,
    *,
    model_name: str,
) -> dict[str, Any]:
    levels = {
        "diagnostic": _score_diagnostic,
        "interactive": _score_interactive,
        "sequential": _score_sequential,
        "dynamic": _score_dynamic,
    }
    model_scores: dict[str, dict[str, float]] = {}
    parse_failures: dict[str, int] = {}
    for level, scorer in levels.items():
        scores, failures = scorer(generate)
        model_scores[level] = _stats(scores)
        parse_failures[level] = failures

    return {
        "schema_version": "0.1.0",
        "mode": "full_context_plan",
        "model": model_name,
        "episodes": {"diagnostic": 3, "interactive": 3, "sequential": 3, "dynamic": 1},
        "model_scores": model_scores,
        "reference_anchors": reference_anchors(),
        "empty_anchors": empty_anchors(),
        "parse_failures": parse_failures,
    }
