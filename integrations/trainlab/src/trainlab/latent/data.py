"""Source-record splits, byte-language panels and explicit leakage accounting."""

from __future__ import annotations

import hashlib

import numpy as np

from .artifacts import require
from .statistics import _ids


def prepare_token_rows(
    capture,
    input_ids,
    *,
    record_ids,
    domains,
    target_ids=None,
    lengths=None,
    row_mask=None,
    window_ids=None,
    position_ids=None,
):
    """Align native B×T captures into explicit token rows for numerical jobs.

    Rows retain C-order window/position identity. The returned decoder context
    is selected into this same row order, so callback row_indices are relative
    to the returned rows, not to the original padded capture. No targets are
    inferred and padding is excluded only through declared lengths/masks.
    """
    from .native import _input_digest

    x = np.asarray(input_ids)
    require(
        x.ndim == 2 and x.dtype.kind in "iu" and 0 < x.size <= 2**20 and np.all(x >= 0),
        "bounded nonnegative B-by-T input IDs required",
    )
    require(
        type(capture) is dict and capture.get("input_sha256") == _input_digest(x),
        "capture does not belong to these exact input tokens",
    )
    batch, steps = x.shape
    records, labels = _ids(record_ids, name="source record IDs"), _ids(domains, name="domain IDs")
    windows = (
        np.arange(batch) if window_ids is None else _ids(window_ids, unique=True, name="window IDs")
    )
    require(
        records.shape == labels.shape == windows.shape == (batch,),
        "record/domain/window identities must align with captured windows",
    )
    for record in np.unique(records):
        require(len(np.unique(labels[records == record])) == 1, "source record crosses domains")
    physical = np.broadcast_to(np.arange(steps), x.shape)
    valid = np.ones(x.shape, dtype=bool)
    if lengths is not None:
        n = np.asarray(lengths)
        require(
            n.shape == (batch,) and n.dtype.kind in "iu" and np.all(n > 0) and np.all(n <= steps),
            "one valid physical length per window required",
        )
        valid &= physical < n[:, None]
    if row_mask is not None:
        mask = np.asarray(row_mask)
        require(
            mask.dtype.kind == "b" and mask.shape == x.shape,
            "token mask must align with B-by-T capture",
        )
        valid &= mask
    selected = np.flatnonzero(valid.reshape(-1))
    require(0 < len(selected) <= 100000, "select 1..100000 observed token rows")
    total = 0

    def aligned(value, name, *, features=False):
        nonlocal total
        a = np.asarray(value)
        require(
            a.size > 0
            and a.ndim >= (3 if features else 2)
            and a.shape[:2] == x.shape
            and a.dtype.kind in "biuf"
            and np.isfinite(a).all(),
            f"{name} must align with the captured B-by-T positions",
        )
        total += a.size
        require(total <= 50_000_000, "token capture preparation exceeds numeric element budget")
        if features:
            return a.reshape(x.size, -1)[selected].copy()
        return a.reshape((x.size,) + a.shape[2:])[selected].copy()

    hidden = aligned(capture.get("hidden"), "hidden", features=True)
    logits = aligned(capture.get("logits"), "logits", features=True)
    views, context = capture.get("views", {}), capture.get("context", {})
    require(
        type(views) is dict and type(context) is dict, "named views and decoder context required"
    )
    view_rows = {
        name: aligned(value, f"view {name}", features=True) for name, value in views.items()
    }
    context_rows = {name: aligned(value, f"context {name}") for name, value in context.items()}
    positions = physical if position_ids is None else np.asarray(position_ids)
    if positions.shape == (steps,):
        positions = np.broadcast_to(positions, x.shape)
    require(
        positions.shape == x.shape and positions.dtype.kind in "iu" and np.all(positions >= 0),
        "position IDs must align with the physical tokens",
    )
    window_index = np.repeat(np.arange(batch), steps)[selected]
    token_rows = x.reshape(-1)[selected].copy()
    position_rows = positions.reshape(-1)[selected].copy()
    result = {
        "hidden": hidden,
        "logits": logits,
        "views": view_rows,
        "context": context_rows,
        "capture_row_indices": selected,
        "row_indices": np.arange(len(selected)),
        "token_ids": token_rows,
        "record_ids": records[window_index],
        "domains": labels[window_index],
        "window_ids": windows[window_index],
        "physical_positions": physical.reshape(-1)[selected].copy(),
        "positions": position_rows,
        "readout_kind": capture.get("readout_kind", "logits"),
        "input_sha256": capture["input_sha256"],
        "source_shape": list(x.shape),
        "context_indexing": (
            "returned token-row order; callback row_indices index these context arrays"
        ),
        "position_semantics": "physical token positions"
        if position_ids is None
        else "declared lookup positions",
        "scope": (
            "observed token rows; window/record dependencies retained, not independent samples"
        ),
    }
    require(
        result["readout_kind"] in ("logits", "log_probabilities"),
        "explicit native readout kind required",
    )
    if target_ids is not None:
        targets = np.asarray(target_ids)
        require(
            targets.shape == x.shape and targets.dtype.kind in "iu",
            "targets must align with B-by-T capture",
        )
        targets = targets.reshape(-1)[selected].copy()
        require(
            np.all(targets >= 0) and np.all(targets < logits.shape[1]),
            "target outside captured vocabulary",
        )
        result["target_ids"] = targets
    result["rows"] = [
        {
            "id": int(original),
            "record_id": str(records[window]),
            "domain": str(labels[window]),
            "sequence": str(windows[window]),
            "position": int(position),
            "token": int(token),
        }
        for original, window, position, token in zip(
            selected, window_index, position_rows, token_rows
        )
    ]
    return result


def source_record_folds(record_ids, domains, *, folds=2, seed=0):
    records = _ids(record_ids, name="source record IDs").astype(str)
    labels = _ids(domains, name="domain IDs").astype(str)
    require(
        records.ndim == labels.ndim == 1 and records.shape == labels.shape and records.size > 0,
        "aligned record/domain IDs required",
    )
    require(
        type(folds) is int and 2 <= folds <= 20 and type(seed) is int and seed >= 0,
        "bounded source-fold count and seed required",
    )
    mapping, rng = {}, np.random.default_rng(seed)
    for record in np.unique(records):
        require(len(np.unique(labels[records == record])) == 1, "source record crosses domains")
    for domain in np.unique(labels):
        ids = np.unique(records[labels == domain])
        require(len(ids) >= folds, "each domain needs at least one source record per fold")
        for index, record in enumerate(rng.permutation(ids)):
            mapping[str(record)] = index % folds
    return {
        "folds": np.asarray([mapping[record] for record in records], dtype=np.int64),
        "record_assignment": mapping,
        "seed": seed,
        "scope": "source-record disjoint, domain-stratified fit/evaluation folds",
    }


def _records(records):
    require(
        type(records) is list and 1 <= len(records) <= 100000, "bounded source records required"
    )
    result, seen, total = [], set(), 0
    for record in records:
        require(
            type(record) is dict
            and {"id", "domain", "text"} <= set(record)
            and isinstance(record["id"], str)
            and 0 < len(record["id"]) <= 200
            and record["id"] not in seen
            and isinstance(record["domain"], str)
            and isinstance(record["text"], str),
            "invalid or duplicate source record",
        )
        data = record["text"].encode("utf-8")
        total += len(data)
        require(total <= 256 * 1024 * 1024, "language source byte budget exceeded")
        seen.add(record["id"])
        result.append((record["id"], record["domain"], data))
    return result


def language_panel(
    records,
    *,
    context=32,
    stride=None,
    windows_per_record=1,
    short_record="reject",
    exposure="declared_evaluation",
):
    """Nonoverlapping byte windows; labels are the following byte, with no separators."""
    require(
        type(context) is int
        and 1 <= context <= 65535
        and type(windows_per_record) is int
        and 1 <= windows_per_record <= 10000,
        "bounded language window shape required",
    )
    stride = context + 1 if stride is None else stride
    require(
        type(stride) is int and stride >= context + 1 and short_record in ("reject", "exclude"),
        "explicit nonoverlapping stride and short-record policy required",
    )
    require(isinstance(exposure, str) and exposure.strip(), "exposure status must be explicit")
    rows, excluded, seen_windows = [], [], set()
    for identity, domain, data in _records(records):
        offsets = list(range(0, len(data) - context, stride))[:windows_per_record]
        if not offsets:
            require(
                short_record == "exclude", "short source record lacks an explicit exclusion policy"
            )
            excluded.append(identity)
        for offset in offsets:
            window = data[offset : offset + context + 1]
            pin = hashlib.sha256(window).hexdigest()
            require(pin not in seen_windows, "duplicate language window")
            seen_windows.add(pin)
            rows.append((identity, domain, offset, hashlib.sha256(data).hexdigest(), pin, window))
            require(len(rows) * (context + 1) <= 100000000, "language panel byte budget exceeded")
    require(rows, "language panel contains no complete windows")
    windows = np.asarray([list(row[5]) for row in rows], dtype=np.int64)
    return {
        "input_ids": windows[:, :-1],
        "target_ids": windows[:, 1:],
        "record_ids": np.asarray([row[0] for row in rows]),
        "domains": np.asarray([row[1] for row in rows]),
        "offsets": np.asarray([row[2] for row in rows]),
        "record_sha256": np.asarray([row[3] for row in rows]),
        "window_sha256": np.asarray([row[4] for row in rows]),
        "excluded_short_records": excluded,
        "exposure": exposure,
        "reset": "fresh native state per window",
        "context": context,
        "scope": (
            "nonoverlapping windows within each record; declared exposure is "
            "not certified freshness"
        ),
    }


def language_overlap(training_records, evaluation_records, *, evaluation_windows=None):
    """Check full record identity and all original-training substring positions."""
    train, evaluation = _records(training_records), _records(evaluation_records)
    train_ids = {row[0] for row in train}
    train_hashes = {hashlib.sha256(row[2]).hexdigest() for row in train}
    collisions = [row[0] for row in evaluation if row[0] in train_ids]
    duplicates = [
        row[0] for row in evaluation if hashlib.sha256(row[2]).hexdigest() in train_hashes
    ]
    matches = []
    if evaluation_windows is not None:
        windows = np.asarray(evaluation_windows)
        require(
            windows.ndim == 2
            and windows.dtype.kind in "iu"
            and windows.size <= 100000000
            and np.all((0 <= windows) & (windows <= 255))
            and windows.shape[1] > 0,
            "bounded byte windows required",
        )
        require(len(windows) * len(train) <= 2_000_000, "substring comparison budget exceeded")
        for index, window in enumerate(windows):
            target = bytes(window.tolist())
            if any(target in record[2] for record in train):
                matches.append(index)
    return {
        "status": "FAILED" if collisions or duplicates or matches else "TESTED",
        "record_id_overlap": collisions,
        "record_content_overlap": duplicates,
        "window_training_substring_overlap": matches,
        "window_scan": "NOT_RUN" if evaluation_windows is None else "ALL_TRAINING_OFFSETS",
        "scope": "exact overlap only; semantic leakage and undeclared exposure are not ruled out",
    }


def hierarchical_means(values, record_ids, domains, *, window_ids=None):
    """Token -> window -> record -> domain -> equally weighted domain mean."""
    values = np.asarray(values, dtype=np.float64)
    records = _ids(record_ids, name="source record IDs").astype(str)
    labels = _ids(domains, name="domain IDs").astype(str)
    require(
        values.ndim >= 1
        and records.shape == labels.shape == (len(values),)
        and np.isfinite(values).all()
        and len(values) > 0,
        "hierarchical rows misaligned",
    )
    if values.ndim > 1:
        values = values.mean(axis=tuple(range(1, values.ndim)))
    windows = (
        np.arange(len(values)).astype(str)
        if window_ids is None
        else _ids(window_ids, name="window IDs").astype(str)
    )
    require(windows.shape == records.shape, "window IDs misaligned")
    by_record = []
    for identity in np.unique(records):
        mask = records == identity
        require(len(np.unique(labels[mask])) == 1, "record belongs to multiple domains")
        means = [values[mask & (windows == window)].mean() for window in np.unique(windows[mask])]
        by_record.append((identity, str(labels[mask][0]), float(np.mean(means))))
    domain_means = {
        domain: float(np.mean([row[2] for row in by_record if row[1] == domain]))
        for domain in sorted({row[1] for row in by_record})
    }
    return {
        "record_ids": np.asarray([row[0] for row in by_record]),
        "record_domains": np.asarray([row[1] for row in by_record]),
        "record_values": np.asarray([row[2] for row in by_record]),
        "domain_means": domain_means,
        "equal_domain_mean": float(np.mean(list(domain_means.values()))),
        "aggregation": "token-window-record-domain-equal_domain",
    }
