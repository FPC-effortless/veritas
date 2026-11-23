"""Explicit diagnostic operations; plan files never choose arbitrary imports."""

from __future__ import annotations

import importlib
from dataclasses import dataclass

from ..runner import LabError


@dataclass(frozen=True)
class Operation:
    name: str
    mode: str = "analysis"
    requires: tuple = ()

    def function(self):
        module, name = self.name.split(".", 1)
        package = _EXISTING.get(module, f"trainlab.latent.{module}")
        function = getattr(importlib.import_module(package), name, None)
        if not callable(function):
            raise LabError("declared diagnostic implementation is unavailable")
        return function


_EXISTING = {
    "experiment": "trainlab.experiment_diagnostics",
    "assessment": "trainlab.assessment_diagnostics",
    "training_observer": "trainlab.training_observer",
}

_ANALYSIS = {
    "geometry": (
        "pca_fit",
        "pca_transform",
        "pca_reconstruct",
        "latent_geometry",
        "neighborhood_quality",
        "tsne_projection",
        "linear_cka",
        "cka_matrix",
        "conditional_permutations",
        "window_derangement",
        "matched_context_pairs",
        "token_conditioned_geometry",
        "decoder_metric_fit",
        "decoder_metric_reconstruct",
        "random_subspace",
        "cka_bootstrap",
    ),
    "calibration": (
        "log_softmax",
        "temperature_scale",
        "probability_metrics",
        "select_calibration_settings",
        "record_domain_weights",
    ),
    "scoring": (
        "classification_metrics",
        "counterfactual_metrics",
        "calibration",
        "correctness_transition_masks",
        "additive_nll_decomposition",
        "competence_retention_gates",
        "summarize_counterfactual",
    ),
    "statistics": ("cluster_means", "record_means", "fixed_seed_mean"),
    "data": (
        "prepare_token_rows",
        "source_record_folds",
        "language_panel",
        "language_overlap",
        "hierarchical_means",
    ),
    "analysis": (
        "bootstrap_estimate",
        "paired_estimate",
        "linear_contrast",
        "factorial_contrast",
        "sign_flip",
        "holm",
        "inventory_models",
        "timing_summary",
    ),
    "panels": (
        "association_families",
        "split_association_families",
        "make_association_panel",
        "make_copy_panel",
        "select_training_cues",
        "make_cue_panel",
        "training_byte_frequency",
        "position_conditions",
        "condition_prompt",
        "position_contrasts",
        "audit_association_panel",
    ),
    "learning": (
        "training_recipe",
        "audit_matched_recipes",
        "audit_training_events",
        "audit_seed_panel",
        "audit_first_update",
    ),
    "interventions": (
        "suffix_intervention",
        "position_ids",
        "state_distances",
        "response_metrics",
        "read_footprint",
        "analyze_future_access",
    ),
    "experiment": (
        "training_diagnostics",
        "benchmark_diagnostics",
        "comparison_ledger",
        "paired_statistics",
        "classification_diagnostics",
        "quality_cost",
    ),
    "assessment": ("generalization_audit", "training_order_audit", "paired_slices"),
    "training_observer": ("freeze_slices", "slice_trajectory"),
}

_CALLBACKS = {
    "geometry.compression_diagnostic",
    "calibration.native_readout_contrast",
    "calibration.bank_gain_diagnostics",
    "calibration.component_readout_diagnostics",
}

_NATIVE = {
    "interventions.component_lesions": ("initial_state", "clone_state", "step"),
    "interventions.unread_future": ("clone_state", "step", "edit_state", "state_arrays"),
    "interventions.history_sweep": ("forward",),
    "interventions.position_sweep": ("forward", "position_info", "position_forward"),
    "interventions.native_parity": ("native_forward", "forward", "readout"),
    "interventions.state_interventions": (
        "clone_state",
        "step",
        "select_state",
        "edit_state",
        "state_arrays",
    ),
    "interventions.native_component_sweep": ("native_forward", "forward_condition"),
    "interventions.retrieval_sweep": (
        "initial_state",
        "step",
        "clone_state",
        "select_state",
        "edit_state",
        "state_arrays",
    ),
    "interventions.latency_sweep": ("native_forward", "timed_native_forward", "weights_digest"),
}


def catalog():
    result = {
        f"{module}.{name}": Operation(f"{module}.{name}")
        for module, names in _ANALYSIS.items()
        for name in names
    }
    result.update({name: Operation(name, "callback") for name in _CALLBACKS})
    result.update({name: Operation(name, "native", requires) for name, requires in _NATIVE.items()})
    for name in (
        "forward",
        "native_forward",
        "embedding",
        "readout",
        "position_forward",
        "position_info",
        "weights_digest",
        "timed_native_forward",
    ):
        result[f"native.{name}"] = Operation(f"native.{name}", "capture", (name,))
    return result


def get_operation(name):
    try:
        return catalog()[name]
    except KeyError as exc:
        raise LabError("unknown diagnostic operation; inspect the catalog") from exc
