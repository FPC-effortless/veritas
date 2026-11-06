from __future__ import annotations

import random
from typing import Callable

from investigation_world.operational.models import (
    ActionKind,
    AssertionComparison,
    HiddenActionEffect,
    OperationalEpisode,
    OperationalInvariant,
    OperationalRecord,
    PublicActionSpec,
    StateAssertion,
    WorldDomain,
)


def _ensure_systems(episode: OperationalEpisode, *systems: str) -> None:
    for system in systems:
        if system not in episode.task.permitted_systems:
            episode.task.permitted_systems.append(system)


def _add_action(
    episode: OperationalEpisode,
    name: str,
    kind: ActionKind,
    system: str,
    description: str,
    *parameters: str,
    cost: int = 1,
) -> None:
    if any(action.name == name for action in episode.task.available_actions):
        return
    episode.task.available_actions.append(
        PublicActionSpec(
            name=name,
            kind=kind,
            system=system,
            description=description,
            parameter_names=list(parameters),
            cost=cost,
        )
    )


def _record(
    record_id: str,
    system: str,
    record_type: str,
    object_id: str,
    fields: dict,
    searchable_text: str,
    *,
    related: list[str] | None = None,
    provenance: list[str] | None = None,
    authority: str = "high",
    confidence: float = 0.95,
    freshness: str = "current",
    observed_at: str = "2026-08-26T12:00:00Z",
    valid_from: str | None = "2026-08-01T00:00:00Z",
    valid_to: str | None = None,
) -> OperationalRecord:
    return OperationalRecord(
        record_id=record_id,
        system=system,
        record_type=record_type,
        object_id=object_id,
        fields=fields,
        related_object_ids=related or [],
        searchable_text=searchable_text,
        observed_at=observed_at,
        valid_from=valid_from,
        valid_to=valid_to,
        source_authority=authority,
        confidence=confidence,
        freshness=freshness,
        provenance_ids=provenance or [],
    )


def _annotate_existing_records(episode: OperationalEpisode, index: int) -> None:
    authority_by_system = {
        "WORKBOOK": "high",
        "CALC_ENGINE": "authoritative",
        "CRM": "high",
        "ERP": "authoritative",
        "OBSERVABILITY": "high",
        "KUBERNETES": "authoritative",
        "DATABASE": "authoritative",
        "REGISTRY": "authoritative",
        "ARCHIVE": "high",
        "DIRECTORY": "medium",
        "GIS": "high",
        "WORKFLOW": "authoritative",
    }
    for position, record in enumerate(episode.records):
        record.observed_at = f"2026-08-{20 + ((index + position) % 7):02d}T{8 + position:02d}:00:00Z"
        record.valid_from = f"2026-07-{1 + ((index + position) % 28):02d}T00:00:00Z"
        record.source_authority = authority_by_system.get(record.system, "medium")
        record.confidence = round(max(0.65, 0.99 - 0.03 * position), 3)
        record.freshness = "current" if position < 2 else "recent"


def _target(episode: OperationalEpisode, key: str) -> StateAssertion | None:
    for assertion in episode.oracle.target_state:
        if assertion.key() == key:
            return assertion
    return None


def _effect(episode: OperationalEpisode, action_name: str) -> HiddenActionEffect | None:
    for effect in episode.oracle.action_effects:
        if effect.action_name == action_name:
            return effect
    return None


def _finance(episode: OperationalEpisode, rng: random.Random, index: int, scenario_family: str) -> None:
    _ensure_systems(episode, "GENERAL_LEDGER", "MODEL_GOVERNANCE")
    _add_action(
        episode,
        "inspect_formula_lineage",
        ActionKind.READ,
        "WORKBOOK",
        "Trace upstream/downstream formula lineage before editing the model.",
        "cell",
        cost=2,
    )
    _add_action(
        episode,
        "reconcile_source_balance",
        ActionKind.EXECUTE,
        "GENERAL_LEDGER",
        "Reconcile model source balances to the authoritative ledger period.",
        "model",
        "period",
        cost=3,
    )
    _add_action(
        episode,
        "validate_model_controls",
        ActionKind.EXECUTE,
        "MODEL_GOVERNANCE",
        "Run model-control checks after recalculation.",
        "model",
        cost=2,
    )

    repair = _effect(episode, "repair_formula")
    recalc = _effect(episode, "recalculate_model")
    if repair is None or recalc is None:
        raise ValueError("financial realism requires repair/recalculate effects")
    cell = str(repair.required_parameters["cell"])
    correct_formula = str(repair.required_parameters["formula"])
    valuation_target = _target(episode, "valuation.enterprise_value_m")
    if valuation_target is None:
        raise ValueError("financial realism requires enterprise value target")

    episode.oracle.initial_state.update(
        {
            "model.lineage_inspected": False,
            "model.source_reconciled": False,
            "model.control_validation": "pending",
            "workbook.source_balances_preserved": True,
            "workbook.external_links_valid": True,
            "model.recalculated": False,
        }
    )
    repair.required_state = [
        StateAssertion(object_id="model", field_name="lineage_inspected", expected_value=True)
    ]
    repair.blocked_observable_result = {"accepted": False, "reason": "lineage_review_required"}
    recalc.required_state = [
        StateAssertion(object_id=cell, field_name="formula", expected_value=correct_formula),
        StateAssertion(object_id="model", field_name="source_reconciled", expected_value=True),
    ]
    recalc.set_state["model.recalculated"] = True
    recalc.blocked_observable_result = {"accepted": False, "reason": "model_not_ready"}

    episode.oracle.action_effects.extend(
        [
            HiddenActionEffect(
                action_name="inspect_formula_lineage",
                required_parameters={"cell": cell},
                set_state={"model.lineage_inspected": True},
                observable_result={"lineage_status": "reviewed"},
            ),
            HiddenActionEffect(
                action_name="reconcile_source_balance",
                required_parameters={"model": "valuation", "period": "FY2026"},
                required_state=[
                    StateAssertion(object_id="model", field_name="lineage_inspected", expected_value=True)
                ],
                set_state={"model.source_reconciled": True},
                observable_result={"reconciliation": "balanced"},
                blocked_observable_result={"accepted": False, "reason": "lineage_review_required"},
            ),
            HiddenActionEffect(
                action_name="validate_model_controls",
                required_parameters={"model": "valuation"},
                required_state=[
                    StateAssertion(object_id="model", field_name="recalculated", expected_value=True),
                    StateAssertion(
                        object_id="valuation",
                        field_name="enterprise_value_m",
                        expected_value=valuation_target.expected_value,
                        tolerance=valuation_target.tolerance,
                    ),
                ],
                set_state={"model.control_validation": "passed"},
                observable_result={"control_status": "passed"},
                blocked_observable_result={"accepted": False, "reason": "recalculation_required"},
            ),
        ]
    )
    episode.oracle.target_state.append(
        StateAssertion(object_id="model", field_name="control_validation", expected_value="passed")
    )
    episode.oracle.invariants.extend(
        [
            OperationalInvariant(
                invariant_id="fin-source-balance-preserved",
                description="Authoritative source balances must never be destructively changed.",
                assertion=StateAssertion(
                    object_id="workbook", field_name="source_balances_preserved", expected_value=True
                ),
                severity="critical",
                scope="always",
            ),
            OperationalInvariant(
                invariant_id="fin-external-links-valid",
                description="External workbook links must remain valid throughout repair.",
                assertion=StateAssertion(
                    object_id="workbook", field_name="external_links_valid", expected_value=True
                ),
                severity="high",
                scope="always",
            ),
        ]
    )
    for name in ("inspect_formula_lineage", "reconcile_source_balance", "validate_model_controls"):
        if name not in episode.oracle.required_actions:
            episode.oracle.required_actions.append(name)
    episode.oracle.required_action_order = [
        "inspect_formula_lineage",
        "reconcile_source_balance",
        "repair_formula",
        "recalculate_model",
        "validate_model_controls",
    ]

    broken_formula = next(
        (record.fields.get("formula") for record in episode.records if record.record_type == "formula_audit"),
        "unknown",
    )
    base_ids = [record.record_id for record in episode.records]
    episode.records.extend(
        [
            _record(
                "fin-deep-001",
                "WORKBOOK",
                "workbook_manifest",
                "valuation-model",
                {
                    "file_format": "xlsx",
                    "sheets": ["Revenue", "DCF", "WACC", "Checks"],
                    "calculation_mode": "automatic",
                    "defined_names": 34 + index % 11,
                    "external_links": 2,
                    "protected_ranges": 7,
                    "scenario_family": scenario_family.replace("_", " "),
                },
                "workbook manifest sheets calculation mode named ranges external links controls",
                related=[cell, "valuation"],
                provenance=base_ids[:1],
                authority="authoritative",
            ),
            _record(
                "fin-deep-002",
                "WORKBOOK",
                "formula_lineage",
                cell,
                {
                    "current_formula": broken_formula,
                    "expected_formula_class": "periodic_aggregation",
                    "upstream_nodes": ["Revenue!B2", "Revenue!B13"],
                    "downstream_nodes": ["valuation.enterprise_value_m", "Checks!B4"],
                    "dependency_depth": 4 + index % 3,
                },
                "formula dependency graph upstream downstream lineage audit",
                related=["valuation"],
                provenance=base_ids[:2],
            ),
            _record(
                "fin-deep-003",
                "GENERAL_LEDGER",
                "source_reconciliation",
                "FY2026-ledger",
                {
                    "ledger_period": "FY2026",
                    "model_balance_m": round(210 + rng.random() * 900, 2),
                    "ledger_balance_m": None,
                    "currency": rng.choice(["USD", "EUR", "GBP", "NGN"]),
                    "close_status": "soft_closed",
                    "materiality_m": 0.5,
                },
                "general ledger source reconciliation model balance authoritative close period",
                related=["valuation-model"],
                authority="authoritative",
            ),
            _record(
                "fin-deep-004",
                "MODEL_GOVERNANCE",
                "model_control_policy",
                "POLICY-MODEL-VAL",
                {
                    "formula_lineage_required": True,
                    "source_reconciliation_required": True,
                    "hardcodes_permitted": False,
                    "max_unexplained_variance_pct": 0.5,
                    "post_recalc_control_check": True,
                },
                "model governance policy formula lineage reconciliation hardcodes validation controls",
                authority="authoritative",
            ),
            _record(
                "fin-deep-005",
                "CALC_ENGINE",
                "calculation_chain",
                "valuation-calc-chain",
                {
                    "engine_version": "calc-4.8",
                    "dirty_nodes": 1,
                    "dependency_nodes": 42 + index % 17,
                    "volatile_functions": index % 3,
                    "last_full_calc": "2026-08-25T21:40:00Z",
                },
                "calculation chain dirty nodes dependency graph full recalc",
                related=[cell, "valuation"],
                authority="authoritative",
            ),
            _record(
                "fin-deep-006",
                "WORKBOOK",
                "review_note",
                "review-thread-17",
                {
                    "author_role": "fp&a_manager",
                    "status": "open",
                    "note": "Validate source tie-out before accepting valuation output.",
                    "material": True,
                },
                "review note source tie out valuation acceptance",
                related=[cell],
                authority="medium",
                confidence=0.9,
            ),
        ]
    )
    episode.oracle.required_evidence_ids.extend(["fin-deep-002", "fin-deep-003", "fin-deep-004"])
    episode.task.constraints.extend(
        ["Reconcile authoritative source balances before recalculation", "Complete post-recalc model controls"]
    )
    episode.task.metadata["artifact_contract"] = "xlsx_formula_dependency_graph_v2"


def _enterprise(episode: OperationalEpisode, rng: random.Random, index: int, scenario_family: str) -> None:
    _ensure_systems(episode, "CPQ", "IAM", "FINANCE_CONTROL")
    _add_action(
        episode,
        "verify_actor_authority",
        ActionKind.READ,
        "IAM",
        "Verify the acting user's authority for the requested commercial exception.",
        "user_id",
        "deal_id",
        cost=2,
    )
    _add_action(
        episode,
        "validate_credit_terms",
        ActionKind.EXECUTE,
        "FINANCE_CONTROL",
        "Validate customer credit and payment terms before approval routing.",
        "account",
        "deal_id",
        cost=2,
    )
    _add_action(
        episode,
        "reconcile_quote_order",
        ActionKind.EXECUTE,
        "CPQ",
        "Reconcile quote, CRM opportunity and ERP order state after routing.",
        "deal_id",
        "order_id",
        cost=2,
    )
    opportunity = next(record for record in episode.records if record.record_type == "opportunity")
    order = next(record for record in episode.records if record.record_type == "sales_order")
    deal_id = opportunity.object_id
    order_id = order.object_id
    account = str(opportunity.fields["account"])

    episode.oracle.initial_state.update(
        {
            f"{deal_id}.authority_verified": False,
            f"{deal_id}.credit_checked": False,
            f"{deal_id}.cross_system_reconciled": False,
            f"{order_id}.customer_master_integrity": True,
        }
    )
    request = _effect(episode, "request_discount_approval")
    hold = _effect(episode, "create_order_hold")
    stage = _effect(episode, "update_deal_stage")
    if request is None or hold is None or stage is None:
        raise ValueError("enterprise realism requires approval/hold/stage effects")
    request.required_state = [
        StateAssertion(object_id=deal_id, field_name="authority_verified", expected_value=True),
        StateAssertion(object_id=deal_id, field_name="credit_checked", expected_value=True),
    ]
    request.blocked_observable_result = {"accepted": False, "reason": "prechecks_incomplete"}
    hold.required_state = [
        StateAssertion(object_id=deal_id, field_name="approval", expected_value="vp_requested")
    ]
    hold.blocked_observable_result = {"accepted": False, "reason": "approval_not_routed"}
    stage.required_state = [
        StateAssertion(object_id=order_id, field_name="hold", expected_value=True),
        StateAssertion(object_id=deal_id, field_name="approval", expected_value="vp_requested"),
    ]
    stage.blocked_observable_result = {"accepted": False, "reason": "linked_order_not_controlled"}

    episode.oracle.action_effects.extend(
        [
            HiddenActionEffect(
                action_name="verify_actor_authority",
                required_parameters={"user_id": "USR-REVOPS-01", "deal_id": deal_id},
                set_state={f"{deal_id}.authority_verified": True},
                observable_result={"authority": "verified"},
            ),
            HiddenActionEffect(
                action_name="validate_credit_terms",
                required_parameters={"account": account, "deal_id": deal_id},
                set_state={f"{deal_id}.credit_checked": True},
                observable_result={"credit_review": "acceptable"},
            ),
            HiddenActionEffect(
                action_name="reconcile_quote_order",
                required_parameters={"deal_id": deal_id, "order_id": order_id},
                required_state=[
                    StateAssertion(object_id=deal_id, field_name="stage", expected_value="Approval"),
                    StateAssertion(object_id=order_id, field_name="hold", expected_value=True),
                ],
                set_state={f"{deal_id}.cross_system_reconciled": True},
                observable_result={"reconciliation": "consistent"},
                blocked_observable_result={"accepted": False, "reason": "workflow_state_inconsistent"},
            ),
        ]
    )
    episode.oracle.target_state.append(
        StateAssertion(object_id=deal_id, field_name="cross_system_reconciled", expected_value=True)
    )
    episode.oracle.invariants.append(
        OperationalInvariant(
            invariant_id="ent-master-data-integrity",
            description="Customer/order master data must not be mutated to bypass controls.",
            assertion=StateAssertion(
                object_id=order_id, field_name="customer_master_integrity", expected_value=True
            ),
            severity="critical",
            scope="always",
        )
    )
    for name in ("verify_actor_authority", "validate_credit_terms", "reconcile_quote_order"):
        if name not in episode.oracle.required_actions:
            episode.oracle.required_actions.append(name)
    episode.oracle.required_action_order = [
        "verify_actor_authority",
        "validate_credit_terms",
        "request_discount_approval",
        "create_order_hold",
        "update_deal_stage",
        "reconcile_quote_order",
    ]
    episode.records.extend(
        [
            _record(
                "ent-deep-001",
                "CPQ",
                "quote_version",
                f"QUOTE-{deal_id}",
                {
                    "version": 3 + index % 4,
                    "account": account,
                    "net_amount_usd": opportunity.fields.get("amount_usd"),
                    "discount_pct": opportunity.fields.get("requested_discount_pct"),
                    "approval_status": "pending",
                    "scenario": scenario_family.replace("_", " "),
                },
                "cpq quote version discount approval account commercial terms",
                related=[deal_id, order_id],
                provenance=[opportunity.record_id],
                authority="authoritative",
            ),
            _record(
                "ent-deep-002",
                "IAM",
                "role_assignment",
                "USR-REVOPS-01",
                {
                    "role": "revenue_operations_manager",
                    "region": rng.choice(["EMEA", "AMER", "APAC"]),
                    "delegated_approval_limit_pct": 10,
                    "can_override_controls": False,
                    "active": True,
                },
                "iam role assignment authority delegation approval limit active user",
                related=[deal_id],
                authority="authoritative",
            ),
            _record(
                "ent-deep-003",
                "FINANCE_CONTROL",
                "credit_profile",
                account,
                {
                    "credit_status": "approved",
                    "credit_limit_usd": int(opportunity.fields.get("amount_usd", 100000) * 1.8),
                    "open_receivables_usd": int(rng.random() * 150000),
                    "days_past_due": index % 8,
                    "payment_terms": "NET45",
                },
                "customer credit profile receivables limit payment terms finance control",
                related=[deal_id],
                authority="authoritative",
            ),
            _record(
                "ent-deep-004",
                "ERP",
                "order_line_summary",
                order_id,
                {
                    "line_count": 2 + index % 12,
                    "currency": "USD",
                    "tax_status": "calculated",
                    "billing_schedule": "annual",
                    "customer_master_id": f"CUST-{10000 + index}",
                },
                "erp order lines billing tax customer master commercial order",
                related=[deal_id, account],
                provenance=[order.record_id],
                authority="authoritative",
            ),
            _record(
                "ent-deep-005",
                "CRM",
                "account_relationship",
                account,
                {
                    "segment": rng.choice(["enterprise", "strategic", "mid_market"]),
                    "renewal_risk": round(rng.random() * 0.35, 3),
                    "contract_status": "active",
                    "owner": "AE-204",
                },
                "crm account relationship segment contract renewal owner",
                related=[deal_id],
                authority="high",
            ),
            _record(
                "ent-deep-006",
                "ERP",
                "audit_event",
                f"AUDIT-{order_id}",
                {
                    "event": "order_created_from_quote",
                    "actor": "integration-cpq-erp",
                    "immutable": True,
                    "control_context": "discount_approval",
                },
                "immutable audit event cpq erp integration order approval control",
                related=[deal_id, order_id],
                authority="authoritative",
            ),
        ]
    )
    episode.oracle.required_evidence_ids.extend(["ent-deep-002", "ent-deep-003", "ent-deep-006"])
    episode.task.constraints.extend(
        ["Verify acting authority and customer credit before routing", "Reconcile CPQ/CRM/ERP state after the controlled transition"]
    )
    episode.task.metadata["artifact_contract"] = "crm_cpq_erp_control_graph_v2"


def _devops(episode: OperationalEpisode, rng: random.Random, index: int, scenario_family: str) -> None:
    _ensure_systems(episode, "CHANGE_MGMT", "TRACING", "SLO")
    _add_action(
        episode,
        "correlate_change",
        ActionKind.READ,
        "CHANGE_MGMT",
        "Correlate the incident onset with recent production changes.",
        "service",
        "deployment",
        cost=2,
    )
    _add_action(
        episode,
        "inspect_dependency_graph",
        ActionKind.READ,
        "TRACING",
        "Inspect live dependency health and isolate the smallest justified blast radius.",
        "service",
        cost=2,
    )
    _add_action(
        episode,
        "validate_slo",
        ActionKind.EXECUTE,
        "SLO",
        "Validate post-recovery SLI/SLO health over the verification window.",
        "service",
        cost=2,
    )
    alert = next(record for record in episode.records if record.record_type == "alert")
    service = alert.object_id
    deployment = str(alert.fields.get("started_after"))
    db_record = next(record for record in episode.records if record.record_type == "replication_health")
    database = db_record.object_id

    episode.oracle.initial_state.update(
        {
            f"{service}.change_correlated": False,
            f"{service}.dependencies_checked": False,
            f"{service}.slo_verified": False,
            f"{service}.dependency_integrity": True,
        }
    )
    restart = _effect(episode, "restart_service")
    verify = _effect(episode, "verify_health")
    if restart is None or verify is None:
        raise ValueError("devops realism requires restart/verify effects")
    restart.required_state = [
        StateAssertion(object_id=service, field_name="change_correlated", expected_value=True),
        StateAssertion(object_id=service, field_name="dependencies_checked", expected_value=True),
    ]
    restart.blocked_observable_result = {"accepted": False, "reason": "diagnosis_incomplete"}
    verify.required_state = [StateAssertion(object_id=service, field_name="health", expected_value="healthy")]
    verify.blocked_observable_result = {"accepted": False, "reason": "service_not_recovered"}

    episode.oracle.action_effects.extend(
        [
            HiddenActionEffect(
                action_name="correlate_change",
                required_parameters={"service": service, "deployment": deployment},
                set_state={f"{service}.change_correlated": True},
                observable_result={"change_correlation": "strong"},
            ),
            HiddenActionEffect(
                action_name="inspect_dependency_graph",
                required_parameters={"service": service},
                set_state={f"{service}.dependencies_checked": True},
                observable_result={"dependency_scope": "service_local"},
            ),
            HiddenActionEffect(
                action_name="validate_slo",
                required_parameters={"service": service},
                required_state=[
                    StateAssertion(object_id=service, field_name="health_verified", expected_value=True)
                ],
                set_state={f"{service}.slo_verified": True},
                observable_result={"slo_window": "healthy"},
                blocked_observable_result={"accepted": False, "reason": "health_check_required"},
            ),
        ]
    )
    episode.oracle.target_state.append(
        StateAssertion(object_id=service, field_name="slo_verified", expected_value=True)
    )
    episode.oracle.invariants.append(
        OperationalInvariant(
            invariant_id="dev-dependency-integrity",
            description="Healthy dependencies must not be degraded while recovering the target service.",
            assertion=StateAssertion(
                object_id=service, field_name="dependency_integrity", expected_value=True
            ),
            severity="critical",
            scope="always",
        )
    )
    for name in ("correlate_change", "inspect_dependency_graph", "validate_slo"):
        if name not in episode.oracle.required_actions:
            episode.oracle.required_actions.append(name)
    episode.oracle.required_action_order = [
        "correlate_change",
        "inspect_dependency_graph",
        "restart_service",
        "verify_health",
        "validate_slo",
    ]
    episode.records.extend(
        [
            _record(
                "dev-deep-001",
                "CHANGE_MGMT",
                "deployment_change",
                deployment,
                {
                    "service": service,
                    "version_from": "2.8.0",
                    "version_to": "2.8.1",
                    "changed_files": 18 + index % 40,
                    "risk_score": round(0.45 + rng.random() * 0.45, 3),
                    "rollback_ready": True,
                    "scenario": scenario_family.replace("_", " "),
                },
                "deployment change production release risk rollback incident correlation",
                related=[service],
                authority="authoritative",
            ),
            _record(
                "dev-deep-002",
                "TRACING",
                "service_dependency_graph",
                service,
                {
                    "upstreams": ["gateway", "identity"],
                    "downstreams": [database, "payments-cache"],
                    "healthy_dependencies": [database, "payments-cache"],
                    "suspect_edge": f"{service}->{service}-worker",
                    "trace_sample_count": 1200 + index * 3,
                },
                "distributed trace service dependency graph healthy upstream downstream suspect edge",
                related=[database],
                authority="high",
            ),
            _record(
                "dev-deep-003",
                "OBSERVABILITY",
                "sli_window",
                service,
                {
                    "availability_5m": round(0.61 + rng.random() * 0.2, 4),
                    "latency_p99_ms": int(2200 + rng.random() * 4000),
                    "error_budget_burn_1h": round(6 + rng.random() * 18, 2),
                    "request_rate_rps": int(150 + rng.random() * 1800),
                },
                "sli availability latency error budget burn request rate incident",
                related=[service],
                authority="high",
            ),
            _record(
                "dev-deep-004",
                "SLO",
                "service_level_objective",
                service,
                {
                    "availability_target": 0.999,
                    "latency_p95_target_ms": 350,
                    "error_budget_policy": "protect_remaining_budget",
                    "verification_window_min": 10,
                },
                "service level objective availability latency verification error budget",
                related=[service],
                authority="authoritative",
            ),
            _record(
                "dev-deep-005",
                "KUBERNETES",
                "deployment_spec",
                service,
                {
                    "replicas": 4 + index % 8,
                    "max_unavailable": 1,
                    "readiness_probe": "/health/ready",
                    "liveness_probe": "/health/live",
                    "resource_limits": {"cpu": "2", "memory": "2Gi"},
                },
                "kubernetes deployment replicas probes resource limits rollout",
                related=[service],
                authority="authoritative",
            ),
            _record(
                "dev-deep-006",
                "OBSERVABILITY",
                "log_signature",
                service,
                {
                    "signature": "worker initialization timeout",
                    "first_seen_after": deployment,
                    "affected_pods": 3,
                    "database_errors": 0,
                    "confidence": 0.96,
                },
                "log signature timeout deployment pods database no errors root cause evidence",
                related=[service, database],
                confidence=0.96,
            ),
        ]
    )
    episode.oracle.required_evidence_ids.extend(["dev-deep-001", "dev-deep-002", "dev-deep-004", "dev-deep-006"])
    episode.task.constraints.extend(
        ["Correlate the failure to evidence before intervention", "Validate the service over an SLO window after apparent recovery"]
    )
    episode.task.metadata["artifact_contract"] = "incident_telemetry_dependency_graph_v2"


def _osint(episode: OperationalEpisode, rng: random.Random, index: int, scenario_family: str) -> None:
    _ensure_systems(episode, "DOCUMENTS", "NEWS")
    _add_action(
        episode,
        "record_hypothesis",
        ActionKind.WRITE,
        "CASEFILE",
        "Record the leading identity hypothesis without prematurely merging identities.",
        "subject",
        "candidate",
        cost=1,
    )
    _add_action(
        episode,
        "corroborate_identity",
        ActionKind.WRITE,
        "CASEFILE",
        "Corroborate the resolution using independent source roots.",
        "subject",
        "resolved_to",
        cost=2,
    )
    _add_action(
        episode,
        "close_case",
        ActionKind.SUBMIT,
        "CASEFILE",
        "Close the case only after provenance and corroboration requirements are satisfied.",
        "case_id",
        cost=1,
    )
    resolve = _effect(episode, "resolve_identity")
    link = _effect(episode, "link_evidence")
    if resolve is None or link is None:
        raise ValueError("osint realism requires resolve/link effects")
    subject = str(resolve.required_parameters["subject"])
    resolved_to = str(resolve.required_parameters["resolved_to"])
    primary_record_id = str(link.required_parameters["record_id"])
    archive = next(record for record in episode.records if record.record_type == "historical_filing")
    secondary_record_id = archive.record_id

    episode.oracle.initial_state.update(
        {
            "investigation.hypothesis_recorded": False,
            "investigation.primary_evidence_linked": False,
            "investigation.secondary_evidence_linked": False,
            "investigation.corroborated": False,
            "investigation.case_closed": False,
            "investigation.chain_of_custody": True,
        }
    )
    resolve.required_state = [
        StateAssertion(object_id="investigation", field_name="hypothesis_recorded", expected_value=True)
    ]
    resolve.blocked_observable_result = {"accepted": False, "reason": "hypothesis_not_recorded"}
    link.set_state = {"investigation.primary_evidence_linked": True}
    link.required_state = [
        StateAssertion(object_id="investigation", field_name="subject_resolved", expected_value=True)
    ]
    episode.oracle.action_effects.append(
        HiddenActionEffect(
            action_name="link_evidence",
            required_parameters={"record_id": secondary_record_id},
            required_state=[
                StateAssertion(object_id="investigation", field_name="subject_resolved", expected_value=True)
            ],
            set_state={"investigation.secondary_evidence_linked": True},
            observable_result={"evidence_linked": True},
        )
    )
    episode.oracle.action_effects.extend(
        [
            HiddenActionEffect(
                action_name="record_hypothesis",
                required_parameters={"subject": subject, "candidate": resolved_to},
                set_state={"investigation.hypothesis_recorded": True},
                observable_result={"hypothesis_status": "recorded"},
            ),
            HiddenActionEffect(
                action_name="corroborate_identity",
                required_parameters={"subject": subject, "resolved_to": resolved_to},
                required_state=[
                    StateAssertion(object_id="investigation", field_name="primary_evidence_linked", expected_value=True),
                    StateAssertion(object_id="investigation", field_name="secondary_evidence_linked", expected_value=True),
                ],
                set_state={
                    "investigation.corroborated": True,
                    "investigation.provenance_complete": True,
                },
                observable_result={"corroboration": "independent_sources_satisfied"},
                blocked_observable_result={"accepted": False, "reason": "independent_evidence_required"},
            ),
            HiddenActionEffect(
                action_name="close_case",
                required_parameters={"case_id": "CASE-001"},
                required_state=[
                    StateAssertion(object_id="investigation", field_name="corroborated", expected_value=True),
                    StateAssertion(object_id="investigation", field_name="provenance_complete", expected_value=True),
                ],
                set_state={"investigation.case_closed": True},
                observable_result={"case_status": "closed"},
                blocked_observable_result={"accepted": False, "reason": "case_not_ready"},
            ),
        ]
    )
    episode.oracle.target_state.extend(
        [
            StateAssertion(object_id="investigation", field_name="corroborated", expected_value=True),
            StateAssertion(object_id="investigation", field_name="case_closed", expected_value=True),
        ]
    )
    episode.oracle.invariants.append(
        OperationalInvariant(
            invariant_id="osi-chain-of-custody",
            description="Evidence chain-of-custody must remain intact throughout the investigation.",
            assertion=StateAssertion(
                object_id="investigation", field_name="chain_of_custody", expected_value=True
            ),
            severity="critical",
            scope="always",
        )
    )
    for name in ("record_hypothesis", "corroborate_identity", "close_case"):
        if name not in episode.oracle.required_actions:
            episode.oracle.required_actions.append(name)
    episode.oracle.required_action_counts["link_evidence"] = 2
    episode.oracle.required_action_order = [
        "record_hypothesis",
        "resolve_identity",
        "link_evidence",
        "corroborate_identity",
        "close_case",
    ]

    company = next(record.object_id for record in episode.records if record.record_type == "company_filing")
    directory_records = [record for record in episode.records if record.record_type == "identity_record"]
    decoy = next((record.object_id for record in directory_records if record.object_id != resolved_to), "alternate candidate")
    episode.records.extend(
        [
            _record(
                "osi-deep-001",
                "DOCUMENTS",
                "source_provenance",
                f"DOC-{company}",
                {
                    "source_root": "corporate_registry_export",
                    "retrieved_at": "2026-08-24T14:00:00Z",
                    "document_hash": f"sha256:{index:064x}"[-71:],
                    "independent_of_directory": True,
                    "scenario": scenario_family.replace("_", " "),
                },
                "document provenance registry export hash independent source root",
                related=[company, resolved_to],
                authority="high",
            ),
            _record(
                "osi-deep-002",
                "NEWS",
                "archived_article",
                resolved_to,
                {
                    "year": 2021 + index % 4,
                    "employer": company,
                    "role": "finance adviser",
                    "address_mentioned": True,
                    "source_independence": "partial",
                },
                "archived article person company role historical address corroboration",
                related=[company],
                authority="medium",
                confidence=0.78,
                freshness="historical",
            ),
            _record(
                "osi-deep-003",
                "DOCUMENTS",
                "identifier_crosswalk",
                resolved_to,
                {
                    "name_variants": [subject, resolved_to],
                    "shared_address": True,
                    "occupation_consistent": True,
                    "unique_identifier_present": False,
                    "false_positive_candidate": decoy,
                },
                "identity crosswalk name variants address occupation false positive candidate",
                related=[company, decoy],
                confidence=0.91,
            ),
            _record(
                "osi-deep-004",
                "DIRECTORY",
                "negative_evidence",
                decoy,
                {
                    "address_mismatch": True,
                    "occupation_mismatch": True,
                    "timeline_overlap": False,
                    "supports_exclusion": True,
                },
                "negative evidence address mismatch occupation mismatch exclude identity candidate",
                related=[resolved_to],
                authority="medium",
                confidence=0.94,
            ),
            _record(
                "osi-deep-005",
                "REGISTRY",
                "filing_metadata",
                company,
                {
                    "filing_sequence": 6 + index % 8,
                    "filing_status": "accepted",
                    "schema_version": "registry-v3",
                    "signed": True,
                    "historical_amendments": 2,
                },
                "registry filing metadata accepted signed amendments provenance",
                related=[resolved_to],
                authority="authoritative",
            ),
        ]
    )
    episode.oracle.required_evidence_ids.extend(["osi-deep-001", "osi-deep-003", "osi-deep-004"])
    episode.task.constraints.extend(
        ["Use at least two evidence links before corroboration", "Distinguish source independence from repeated claims"]
    )
    episode.task.metadata["artifact_contract"] = "multi_source_provenance_casefile_v2"


def _gis(episode: OperationalEpisode, rng: random.Random, index: int, scenario_family: str) -> None:
    _ensure_systems(episode, "DATA_CATALOG", "QA")
    _add_action(
        episode,
        "inspect_spatial_metadata",
        ActionKind.READ,
        "DATA_CATALOG",
        "Inspect CRS, datum, axis order, schema and lineage before transformation.",
        "layer",
        cost=2,
    )
    _add_action(
        episode,
        "validate_topology",
        ActionKind.EXECUTE,
        "QA",
        "Run topology and geometry-quality checks on the derived layer.",
        "layer",
        cost=2,
    )
    _add_action(
        episode,
        "execute_overlay",
        ActionKind.EXECUTE,
        "GIS",
        "Execute the requested spatial overlay only after CRS/topology validation.",
        "source_layer",
        "target_layer",
        cost=3,
    )
    source = next(record for record in episode.records if record.record_type == "layer_metadata" and record.fields.get("invalid_geometries", 0) > 0)
    target = next(record for record in episode.records if record.record_type == "layer_metadata" and record.object_id != source.object_id)
    layer = source.object_id
    overlay = target.object_id
    required_crs = str(target.fields["crs"])

    episode.oracle.initial_state.update(
        {
            f"{layer}.metadata_inspected": False,
            f"{layer}.topology_validated": False,
            "overlay.created": False,
            "overlay.sliver_rate": 1.0,
            f"{layer}.lineage_preserved": True,
        }
    )
    reproject = _effect(episode, "reproject_layer")
    repair = _effect(episode, "repair_geometry")
    if reproject is None or repair is None:
        raise ValueError("gis realism requires reproject/repair effects")
    reproject.required_state = [
        StateAssertion(object_id=layer, field_name="metadata_inspected", expected_value=True)
    ]
    reproject.blocked_observable_result = {"accepted": False, "reason": "metadata_review_required"}
    repair.required_state = [
        StateAssertion(object_id=layer, field_name="crs", expected_value=required_crs)
    ]
    repair.blocked_observable_result = {"accepted": False, "reason": "target_crs_required"}
    sliver_rate = round(0.0005 + rng.random() * 0.002, 5)
    episode.oracle.action_effects.extend(
        [
            HiddenActionEffect(
                action_name="inspect_spatial_metadata",
                required_parameters={"layer": layer},
                set_state={f"{layer}.metadata_inspected": True},
                observable_result={"metadata_status": "reviewed"},
            ),
            HiddenActionEffect(
                action_name="validate_topology",
                required_parameters={"layer": layer},
                required_state=[
                    StateAssertion(object_id=layer, field_name="crs", expected_value=required_crs),
                    StateAssertion(object_id=layer, field_name="invalid_geometries", expected_value=0),
                ],
                set_state={f"{layer}.topology_validated": True},
                observable_result={"topology": "valid"},
                blocked_observable_result={"accepted": False, "reason": "geometry_not_ready"},
            ),
            HiddenActionEffect(
                action_name="execute_overlay",
                required_parameters={"source_layer": layer, "target_layer": overlay},
                required_state=[
                    StateAssertion(object_id=layer, field_name="topology_validated", expected_value=True)
                ],
                set_state={"overlay.created": True, "overlay.sliver_rate": sliver_rate},
                observable_result={"overlay_status": "created"},
                blocked_observable_result={"accepted": False, "reason": "qa_validation_required"},
            ),
        ]
    )
    episode.oracle.target_state.extend(
        [
            StateAssertion(object_id="overlay", field_name="created", expected_value=True),
            StateAssertion(
                object_id="overlay",
                field_name="sliver_rate",
                expected_value=0.003,
                comparison=AssertionComparison.LESS_THAN_OR_EQUAL,
            ),
        ]
    )
    episode.oracle.invariants.append(
        OperationalInvariant(
            invariant_id="gis-lineage-preserved",
            description="Derived processing must preserve source lineage and immutable source identity.",
            assertion=StateAssertion(object_id=layer, field_name="lineage_preserved", expected_value=True),
            severity="critical",
            scope="always",
        )
    )
    for name in ("inspect_spatial_metadata", "validate_topology", "execute_overlay"):
        if name not in episode.oracle.required_actions:
            episode.oracle.required_actions.append(name)
    episode.oracle.required_action_order = [
        "inspect_spatial_metadata",
        "reproject_layer",
        "repair_geometry",
        "validate_topology",
        "execute_overlay",
    ]
    episode.records.extend(
        [
            _record(
                "gis-deep-001",
                "DATA_CATALOG",
                "dataset_catalog_entry",
                layer,
                {
                    "geometry_type": "MultiPolygon",
                    "source_crs": source.fields["crs"],
                    "axis_order": "longitude_latitude",
                    "datum": "WGS84" if source.fields["crs"] == "EPSG:4326" else "projected",
                    "feature_count": source.fields.get("feature_count"),
                    "lineage_id": f"LINEAGE-{1000 + index}",
                    "scenario": scenario_family.replace("_", " "),
                },
                "dataset catalog geometry crs axis order datum feature count lineage",
                related=[layer, overlay],
                authority="authoritative",
            ),
            _record(
                "gis-deep-002",
                "DATA_CATALOG",
                "crs_definition",
                required_crs,
                {
                    "epsg": required_crs,
                    "units": "metre" if required_crs != "EPSG:4326" else "degree",
                    "axis_order": "easting_northing",
                    "area_of_use": "project_specific",
                    "transform_available": True,
                },
                "coordinate reference system epsg units axis order transform area of use",
                related=[layer, overlay],
                authority="authoritative",
            ),
            _record(
                "gis-deep-003",
                "QA",
                "topology_rule_set",
                layer,
                {
                    "must_not_overlap": True,
                    "must_not_self_intersect": True,
                    "minimum_area_m2": 0.5,
                    "sliver_threshold": 0.003,
                    "repair_strategy": "make_valid_then_snap",
                },
                "topology rules overlap self intersection sliver threshold geometry repair",
                related=[layer],
                authority="authoritative",
            ),
            _record(
                "gis-deep-004",
                "GIS",
                "spatial_extent",
                layer,
                {
                    "bbox": [3.1 + rng.random(), 6.2 + rng.random(), 3.9 + rng.random(), 7.1 + rng.random()],
                    "feature_density": round(12 + rng.random() * 130, 2),
                    "spatial_index": "rtree",
                    "precision_grid": 0.001,
                },
                "spatial extent bounding box density spatial index precision grid",
                related=[layer],
                authority="high",
            ),
            _record(
                "gis-deep-005",
                "WORKFLOW",
                "output_contract",
                "overlay",
                {
                    "output_geometry": "Polygon",
                    "required_crs": required_crs,
                    "max_sliver_rate": 0.003,
                    "preserve_source": True,
                    "lineage_required": True,
                },
                "geoprocessing output contract geometry crs sliver source lineage",
                related=[layer, overlay],
                authority="authoritative",
            ),
            _record(
                "gis-deep-006",
                "GIS",
                "schema_profile",
                layer,
                {
                    "required_fields": ["parcel_id", "owner_class", "area_m2"],
                    "nullable_fields": ["owner_class"],
                    "unique_key": "parcel_id",
                    "encoding": "UTF-8",
                },
                "geospatial schema required fields unique key encoding nullable",
                related=[layer],
                authority="high",
            ),
        ]
    )
    episode.oracle.required_evidence_ids.extend(["gis-deep-001", "gis-deep-003", "gis-deep-005"])
    episode.task.constraints.extend(
        ["Inspect datum/axis-order metadata before transformation", "Validate topology and output tolerance before accepting the overlay"]
    )
    episode.task.metadata["artifact_contract"] = "vector_crs_topology_lineage_v2"


_REALISM_BUILDERS: dict[WorldDomain, Callable[[OperationalEpisode, random.Random, int, str], None]] = {
    WorldDomain.FINANCIAL_SPREADSHEET: _finance,
    WorldDomain.ENTERPRISE_OPERATIONS: _enterprise,
    WorldDomain.DEVOPS_INCIDENT_RESPONSE: _devops,
    WorldDomain.INVESTIGATION_OSINT: _osint,
    WorldDomain.GIS_OPERATIONS: _gis,
}


def apply_domain_realism(
    episode: OperationalEpisode,
    *,
    rng: random.Random,
    index: int,
    scenario_family: str,
) -> OperationalEpisode:
    """Deepen one procedural episode while preserving the shared public/verifier contract."""

    _annotate_existing_records(episode, index)
    _REALISM_BUILDERS[episode.task.domain](episode, rng, index, scenario_family)
    episode.metadata["realism_profile"] = "domain_native_operational_v2"
    episode.metadata["temporal_provenance"] = True
    episode.task.metadata["stateful_preconditions"] = True
    episode.oracle.metadata["realism_profile"] = "domain_native_operational_v2"
    episode.oracle.metadata["scenario_family"] = scenario_family
    return OperationalEpisode.model_validate(episode.model_dump(mode="python"))
