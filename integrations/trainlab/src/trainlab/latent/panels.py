"""Model-free literal binding panels, train-only selection, and position controls."""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from copy import deepcopy
from itertools import combinations, product

import numpy as np

from ..runner import LabError

STRATA = ("shared_first", "shared_second", "neither")
FILLER = b". , "
CUE_FILLER = b". ,\n"


def _byte_string(value, name, *, nonempty=True):
    if not isinstance(value, bytes) or (nonempty and not value):
        raise LabError(f"{name} must be {'nonempty ' if nonempty else ''}bytes")
    return value


def _fill(pattern, length):
    _byte_string(pattern, "filler")
    if type(length) is not int or not 0 <= length <= 100_000:
        raise LabError("filler length must be an integer in [0,100000]")
    return (pattern * ((length + len(pattern) - 1) // len(pattern)))[:length]


def association_families(first_bytes=b"abcdefgh", second_bytes=b"ijklmnop"):
    """All unordered pairs of the Cartesian two-byte key vocabulary."""
    first, second = (
        _byte_string(first_bytes, "first bytes"),
        _byte_string(second_bytes, "second bytes"),
    )
    if len(set(first)) != len(first) or len(set(second)) != len(second) or set(first) & set(second):
        raise LabError("key alphabets must be unique and disjoint for unambiguous literal slots")
    keys = [bytes(pair) for pair in product(first, second)]
    if not 2 <= len(keys) <= 256:
        raise LabError("association key vocabulary must contain 2–256 keys")
    return [
        {
            "family_id": i,
            "key_ids": [a, b],
            "keys": [keys[a].hex(), keys[b].hex()],
            "stratum": STRATA[0]
            if keys[a][0] == keys[b][0]
            else STRATA[1]
            if keys[a][1] == keys[b][1]
            else STRATA[2],
        }
        for i, (a, b) in enumerate(combinations(range(len(keys)), 2))
    ]


def split_association_families(
    families, split_counts=None, *, seed=0, require_key_coverage=True, max_attempts=1000
):
    """Freeze disjoint family splits using only family identities and key coverage.

    Counts map split names to stratum quotas. TRAIN receives the remainder.
    Defaults reproduce the005 split sizes for the64-key vocabulary, not its RNG.
    """
    if (
        type(seed) is not int
        or not 0 <= seed < 2**64
        or type(max_attempts) is not int
        or not 1 <= max_attempts <= 10000
    ):
        raise LabError("invalid split seed or bounded attempt count")
    if not isinstance(families, list) or not families:
        raise LabError("families must be a nonempty list")
    ids = [f["family_id"] for f in families]
    if len(set(ids)) != len(ids):
        raise LabError("duplicate family identities")
    quotas = (
        split_counts
        if split_counts is not None
        else {"validation": dict.fromkeys(STRATA, 32), "test": dict.fromkeys(STRATA, 64)}
    )
    if not isinstance(quotas, dict) or not quotas or "train" in quotas:
        raise LabError("declare non-training split quotas; train is the remainder")
    pools = {s: [f["family_id"] for f in families if f["stratum"] == s] for s in STRATA}
    if sum(map(len, pools.values())) != len(families):
        raise LabError("unknown overlap stratum")
    for name, counts in quotas.items():
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(counts, dict)
            or set(counts) != set(STRATA)
        ):
            raise LabError("each split must declare every overlap-stratum quota")
        if any(type(n) is not int or n < 0 for n in counts.values()) or not sum(counts.values()):
            raise LabError("split quotas must be nonnegative with a nonempty split")
    for s in STRATA:
        requested = sum(q[s] for q in quotas.values())
        if requested > len(pools[s]) or (requested == len(pools[s]) and len(pools[s])):
            raise LabError("split quotas must leave training families in every available stratum")
    all_keys = set(k for f in families for k in f["key_ids"])
    by_id = {f["family_id"]: f for f in families}
    if require_key_coverage and any(2 * sum(q.values()) < len(all_keys) for q in quotas.values()):
        raise LabError("split is too small to contain every individual key")
    rng = np.random.default_rng(seed)
    for attempt in range(1, max_attempts + 1):
        result = {name: [] for name in (*quotas, "train")}
        for s in STRATA:
            shuffled = rng.permutation(pools[s]).tolist()
            start = 0
            for name, counts in quotas.items():
                result[name].extend(shuffled[start : start + counts[s]])
                start += counts[s]
            result["train"].extend(shuffled[start:])
        coverage = {
            name: {key for fid in selected for key in by_id[fid]["key_ids"]}
            for name, selected in result.items()
        }
        if all(result.values()) and (
            not require_key_coverage or all(k == all_keys for k in coverage.values())
        ):
            return {
                "splits": {name: sorted(selected) for name, selected in result.items()},
                "key_coverage": {name: sorted(keys) for name, keys in coverage.items()},
                "seed": seed,
                "attempts": attempt,
                "selection": "model-free fixed family quotas",
                "disjoint_families": True,
                "every_key_in_every_split": all(k == all_keys for k in coverage.values()),
            }
    raise LabError("no input-only split met key coverage within the declared attempt budget")


def _value_pairs(values):
    _byte_string(values, "values")
    if len(values) < 2 or len(values) % 2 or len(set(values)) != len(values):
        raise LabError("values must contain an even number of distinct bytes")
    return [(values[i], values[i + 1]) for i in range(0, len(values), 2)]


def _rows_for_family(family, delays, value_pairs, filler, prefix, include_local3, include_copy):
    keys = [bytes.fromhex(v) for v in family["keys"]]
    if len(keys) != 2 or keys[0] == keys[1] or any(len(k) != 2 for k in keys):
        raise LabError("binding families require two distinct two-byte keys")
    if any(not 0 <= v <= 255 for pair in value_pairs for v in pair):
        raise LabError("binding values must be bytes")
    rows = []
    for pair_number, values in enumerate(value_pairs):
        for delay, order, query in product(delays, (0, 1), (0, 1)):
            for assignment in (0, 1):
                assigned = (values[assignment], values[1 - assignment])
                ordered = (order, 1 - order)
                binding = b" ".join(keys[j] + bytes([assigned[j]]) for j in ordered) + b" "
                full = prefix + binding + _fill(filler, delay) + keys[query]
                for condition in ("full", "local3") if include_local3 else ("full",):
                    prompt = full if condition == "full" else full[-3:]
                    rows.append(
                        {
                            "input": prompt,
                            "full_input": full,
                            "target_ids": assigned[query],
                            "candidate_ids": values,
                            "family_ids": family["family_id"],
                            "stratum_ids": STRATA.index(family["stratum"]),
                            "assignment": assignment,
                            "order": order,
                            "query": query,
                            "query_key_ids": family["key_ids"][query],
                            "delay": delay,
                            "condition": condition,
                            "task": "two_binding",
                            "position_offset": 0 if condition == "full" else len(full) - 3,
                            "pair_key": (
                                family["family_id"],
                                pair_number,
                                delay,
                                order,
                                query,
                                condition,
                                "two",
                            ),
                        }
                    )
        if include_copy:
            for query, assignment in product((0, 1), (0, 1)):
                target = values[assignment if query == 0 else 1 - assignment]
                prompt = prefix + keys[query] + bytes([target]) + b" " + keys[query]
                rows.append(
                    {
                        "input": prompt,
                        "full_input": prompt,
                        "target_ids": target,
                        "candidate_ids": values,
                        "family_ids": family["family_id"],
                        "stratum_ids": STRATA.index(family["stratum"]),
                        "assignment": assignment,
                        "order": -1,
                        "query": query,
                        "query_key_ids": family["key_ids"][query],
                        "delay": 0,
                        "condition": "full",
                        "task": "one_binding",
                        "position_offset": 0,
                        "pair_key": (family["family_id"], pair_number, 0, -1, query, "full", "one"),
                    }
                )
    return rows


def _pack(rows, metadata, *, delays, include_local3, include_copy):
    if not rows or len(rows) > 2_000_000:
        raise LabError("panel requires 1–2000000 rows")
    metadata = deepcopy(metadata)
    if metadata["kind"] == "copy_control":
        family_ids = key_ids = list(range(len(metadata["keys"])))
        values = metadata["values"]
    else:
        family_ids = [f["family_id"] for f in metadata["families"]]
        key_ids = sorted({k for f in metadata["families"] for k in f["key_ids"]})
        values = (
            metadata["values"]
            if metadata["kind"] == "full_key_association"
            else [v for f in metadata["families"] for v in f["values"]]
        )
    # This declaration comes from the requested design, never from observed rows.
    # A subset needs its own explicitly generated design; it cannot inherit PASS.
    metadata["design"] = {
        "schema": "trainlab.literal-panel-design.v1",
        "scope": "complete_declared_design",
        "delays": list(delays),
        "include_local3": include_local3,
        "include_copy": include_copy,
        "family_ids": sorted(family_ids),
        "key_ids": key_ids,
        "values": sorted(set(values)),
    }
    lengths = np.asarray([len(r["input"]) for r in rows], dtype=np.int64)
    if len(rows) * int(lengths.max()) > 100_000_000:
        raise LabError("padded panel exceeds 100000000 bytes")
    inputs = np.zeros((len(rows), int(lengths.max())), dtype=np.uint8)
    for i, row in enumerate(rows):
        inputs[i, : lengths[i]] = np.frombuffer(row["input"], dtype=np.uint8)
    pair_map = {}
    pair_ids = []
    for r in rows:
        if r["pair_key"] not in pair_map:
            pair_map[r["pair_key"]] = len(pair_map)
        pair_ids.append(pair_map[r["pair_key"]])
    names = (
        "target_ids",
        "candidate_ids",
        "family_ids",
        "stratum_ids",
        "assignment",
        "order",
        "query",
        "query_key_ids",
        "delay",
        "condition",
        "task",
        "position_offset",
    )
    result = {name: np.asarray([r[name] for r in rows]) for name in names}
    result.update(
        input_ids=inputs,
        lengths=lengths,
        pair_ids=np.asarray(pair_ids),
        full_input_hex=np.asarray([r["full_input"].hex() for r in rows]),
        metadata=metadata,
    )
    result["audit"] = audit_association_panel(result)
    return result


def _panel_budget(rows, length, max_rows):
    if type(max_rows) is not int or not 1 <= max_rows <= 2_000_000:
        raise LabError("max_rows must be a positive integer at most2000000")
    if rows > max_rows or rows * length > 100_000_000:
        raise LabError("declared panel exceeds its pre-allocation row or padded-byte budget")


def make_association_panel(
    *,
    families=None,
    family_ids=None,
    delays=(0, 8),
    values=b"ABCDEFGH",
    filler=FILLER,
    prefix=b"",
    include_local3=False,
    include_copy=False,
    max_rows=1_000_000,
):
    """Full two-byte-key, assignment-swap panel with all values in every family."""
    families = association_families() if families is None else families
    _byte_string(prefix, "prefix", nonempty=False)
    _fill(filler, 0)
    if not delays or len(set(delays)) != len(delays):
        raise LabError("delays must be nonempty and unique")
    for delay in delays:
        _fill(filler, delay)
    selected = (
        list(families)
        if family_ids is None
        else [f for f in families if f["family_id"] in set(family_ids)]
    )
    if not selected or (
        family_ids is not None
        and (len(selected) != len(family_ids) or len(set(family_ids)) != len(family_ids))
    ):
        raise LabError("requested family IDs are absent or duplicated")
    pairs = _value_pairs(values)
    rows_per_family = len(pairs) * (
        8 * len(delays) * (2 if include_local3 else 1) + (4 if include_copy else 0)
    )
    _panel_budget(len(selected) * rows_per_family, len(prefix) + 10 + max(delays), max_rows)
    rows = [
        row
        for f in selected
        for row in _rows_for_family(f, delays, pairs, filler, prefix, include_local3, include_copy)
    ]
    return _pack(
        rows,
        {
            "kind": "full_key_association",
            "families": selected,
            "values": list(values),
            "filler_hex": filler.hex(),
            "prefix_hex": prefix.hex(),
            "selection": "model-free constructed vocabulary",
            "padding_is_not_input": True,
        },
        delays=delays,
        include_local3=include_local3,
        include_copy=include_copy,
    )


def make_copy_panel(*, keys=None, values=b"ABCDEFGH", prefix=b"", max_rows=1_000_000):
    """One-binding familiar-key controls; each pair swaps only its answer value."""
    _byte_string(prefix, "prefix", nonempty=False)
    keys = [bytes([a, b]) for a, b in product(b"abcdefgh", b"ijklmnop")] if keys is None else keys
    if (
        not keys
        or len(set(keys)) != len(keys)
        or any(not isinstance(k, bytes) or len(k) != 2 for k in keys)
    ):
        raise LabError("copy keys must be distinct two-byte strings")
    _panel_budget(len(keys) * len(_value_pairs(values)) * 2, len(prefix) + 6, max_rows)
    rows = []
    for ki, key in enumerate(keys):
        for pi, candidates in enumerate(_value_pairs(values)):
            for assignment in (0, 1):
                prompt = prefix + key + bytes([candidates[assignment]]) + b" " + key
                rows.append(
                    {
                        "input": prompt,
                        "full_input": prompt,
                        "target_ids": candidates[assignment],
                        "candidate_ids": candidates,
                        "family_ids": ki,
                        "stratum_ids": 2,
                        "assignment": assignment,
                        "order": -1,
                        "query": 0,
                        "query_key_ids": ki,
                        "delay": 0,
                        "condition": "full",
                        "task": "one_binding",
                        "position_offset": 0,
                        "pair_key": (ki, pi),
                    }
                )
    return _pack(
        rows,
        {
            "kind": "copy_control",
            "filler_hex": FILLER.hex(),
            "prefix_hex": prefix.hex(),
            "values": list(values),
            "keys": [key.hex() for key in keys],
            "padding_is_not_input": True,
        },
        delays=(),
        include_local3=False,
        include_copy=True,
    )


def _training_records(records):
    if not isinstance(records, (list, tuple)) or not records:
        raise LabError("provide explicit nonempty training records")
    output = []
    for record in records:
        if isinstance(record, bytes):
            raw = record
        elif isinstance(record, dict) and record.get("split") == "train":
            text = record.get("text")
            if not isinstance(text, (str, bytes)):
                raise LabError("training record text must be str or bytes")
            raw = text.encode("utf-8") if isinstance(text, str) else text
        else:
            raise LabError(
                "selection accepts training bytes or records explicitly labelled split=train"
            )
        if not raw:
            raise LabError("empty training record")
        output.append(raw)
    return output


def select_training_cues(training_records, *, min_count=3, max_families=96):
    """TRAIN-only lowercase whole-word quartets, ranked without model outcomes."""
    records = _training_records(training_records)
    if (
        type(min_count) is not int
        or min_count < 1
        or type(max_families) is not int
        or not 1 <= max_families <= 10000
    ):
        raise LabError("invalid lexical count or family limit")
    words = Counter(
        word for raw in records for word in re.findall(rb"(?<![A-Za-z])[a-z]{3}(?![A-Za-z])", raw)
    )
    prefixes = defaultdict(dict)
    for word, count in words.items():
        if count >= min_count:
            prefixes[word[:2]][word[2]] = count
    candidates = []
    for a, b in combinations(sorted(prefixes), 2):
        for x, y in combinations(sorted(set(prefixes[a]) & set(prefixes[b])), 2):
            quartet = (a + bytes([x]), a + bytes([y]), b + bytes([x]), b + bytes([y]))
            if any(
                [i for i in range(2) if word[i : i + 2] == key]
                != ([0] if word.startswith(key) else [])
                for word in quartet
                for key in (a, b)
            ):
                continue
            counts = [words[w] for w in quartet]
            candidates.append((-min(counts), -sum(counts), a, b, x, y, counts))
    selected, seen = [], set()
    key_ids = {key: i for i, key in enumerate(sorted(prefixes))}
    for neg_min, neg_sum, a, b, x, y, counts in sorted(candidates):
        if (a, b) in seen:
            continue
        seen.add((a, b))
        selected.append(
            {
                "family_id": len(selected),
                "keys": [a.hex(), b.hex()],
                "key_ids": [key_ids[a], key_ids[b]],
                "values": [x, y],
                "stratum": STRATA[0] if a[0] == b[0] else STRATA[1] if a[1] == b[1] else STRATA[2],
                "training_counts": counts,
                "minimum_count": -neg_min,
                "total_count": -neg_sum,
            }
        )
        if len(selected) == max_families:
            break
    if len(selected) != max_families:
        raise LabError(
            f"only {len(selected)} unambiguous lexical families meet the predeclared "
            f"{max_families}-family plan"
        )
    return {
        "families": selected,
        "training_records": len(records),
        "min_count": min_count,
        "selection": (
            "literal lowercase three-letter TRAIN words; min count, sum count, lexical ranking"
        ),
        "record_sha256": [hashlib.sha256(raw).hexdigest() for raw in records],
        "new_model_forwards": 0,
    }


def make_cue_panel(
    training_records,
    *,
    min_count=3,
    max_families=96,
    delays=(0, 8, 24, 40),
    filler=CUE_FILLER,
    include_local3=True,
    include_copy=True,
    max_rows=1_000_000,
):
    selected = select_training_cues(
        training_records, min_count=min_count, max_families=max_families
    )
    if not delays or len(set(delays)) != len(delays):
        raise LabError("cue delays must be nonempty and unique")
    for delay in delays:
        _fill(filler, delay)
    _panel_budget(
        max_families
        * (8 * len(delays) * (2 if include_local3 else 1) + (4 if include_copy else 0)),
        10 + max(delays),
        max_rows,
    )
    rows = [
        row
        for f in selected["families"]
        for row in _rows_for_family(
            f, delays, [f["values"]], filler, b"", include_local3, include_copy
        )
    ]
    return _pack(
        rows,
        {
            "kind": "lexical_cue",
            "families": selected["families"],
            "selection": selected,
            "filler_hex": filler.hex(),
            "prefix_hex": "",
            "padding_is_not_input": True,
        },
        delays=delays,
        include_local3=include_local3,
        include_copy=include_copy,
    )


def _declared_panel_design(metadata):
    if not isinstance(metadata, dict) or metadata.get("kind") not in (
        "full_key_association",
        "copy_control",
        "lexical_cue",
    ):
        raise LabError("unknown literal panel design")
    design = metadata.get("design")
    if (
        not isinstance(design, dict)
        or design.get("schema") != "trainlab.literal-panel-design.v1"
        or design.get("scope") != "complete_declared_design"
        or type(design.get("include_local3")) is not bool
        or type(design.get("include_copy")) is not bool
    ):
        raise LabError("a frozen complete panel design is required")
    delays = design.get("delays")
    if (
        type(delays) is not list
        or any(type(d) is not int or not 0 <= d <= 100_000 for d in delays)
        or len(set(delays)) != len(delays)
    ):
        raise LabError("declared delays must be distinct bounded integers")

    def values(value):
        if type(value) is not list or any(type(v) is not int or not 0 <= v <= 255 for v in value):
            raise LabError("declared values must be literal byte integers")
        return tuple(_value_pairs(bytes(value)))

    def keys(value):
        if type(value) is not list or any(type(k) is not str for k in value):
            raise LabError("declare literal key bytes as hexadecimal strings")
        try:
            decoded = [bytes.fromhex(k) for k in value]
        except ValueError as exc:
            raise LabError("malformed declared key bytes") from exc
        if not decoded or any(len(k) != 2 for k in decoded) or len(set(decoded)) != len(decoded):
            raise LabError("declared keys must be distinct two-byte strings")
        return decoded

    families, key_map, value_pairs = {}, {}, {}
    if metadata["kind"] == "copy_control":
        if delays or design["include_local3"] or not design["include_copy"]:
            raise LabError("copy controls require the declared one-binding design only")
        key_map = dict(enumerate(keys(metadata.get("keys"))))
        declared_values = values(metadata.get("values"))
        value_pairs = dict.fromkeys(key_map, declared_values)
        expected_pairs = len(key_map) * len(declared_values)
    else:
        if not delays:
            raise LabError("two-binding designs must declare their delays")
        declared_families = metadata.get("families")
        if type(declared_families) is not list or not declared_families:
            raise LabError("declare all intended binding families")
        shared_values = (
            values(metadata.get("values")) if metadata["kind"] == "full_key_association" else None
        )
        literal_families = set()
        for family in declared_families:
            if not isinstance(family, dict) or type(family.get("family_id")) is not int:
                raise LabError("family identities must be explicit integers")
            identity, ids = family["family_id"], family.get("key_ids")
            if identity < 0 or identity in families:
                raise LabError("family identities must be distinct nonnegative integers")
            if (
                type(ids) is not list
                or len(ids) != 2
                or any(type(k) is not int or k < 0 for k in ids)
                or ids[0] == ids[1]
            ):
                raise LabError("each family requires two distinct key identities")
            literal_keys = keys(family.get("keys"))
            if len(literal_keys) != 2 or frozenset(literal_keys) in literal_families:
                raise LabError("binding families must contain distinct unordered key pairs")
            literal_families.add(frozenset(literal_keys))
            stratum = (
                STRATA[0]
                if literal_keys[0][0] == literal_keys[1][0]
                else STRATA[1]
                if literal_keys[0][1] == literal_keys[1][1]
                else STRATA[2]
            )
            if family.get("stratum") != stratum:
                raise LabError("declared overlap stratum differs from literal family keys")
            for identity_key, literal in zip(ids, literal_keys):
                if identity_key in key_map and key_map[identity_key] != literal:
                    raise LabError("one key identity names different literal keys")
                key_map[identity_key] = literal
            family_values = (
                shared_values if shared_values is not None else values(family.get("values"))
            )
            if metadata["kind"] == "lexical_cue" and len(family_values) != 1:
                raise LabError("each lexical quartet must declare exactly one value pair")
            families[identity], value_pairs[identity] = family, family_values
        if len(set(key_map.values())) != len(key_map):
            raise LabError("one literal key has multiple declared identities")
        if metadata["kind"] == "lexical_cue" and (
            not isinstance(metadata.get("selection"), dict)
            or metadata["selection"].get("families") != declared_families
        ):
            raise LabError("lexical family design differs from its recorded TRAIN selection")
        pairs_per_value = 4 * len(delays) * (2 if design["include_local3"] else 1)
        pairs_per_value += 2 if design["include_copy"] else 0
        expected_pairs = sum(map(len, value_pairs.values())) * pairs_per_value
    expected_sets = {
        "family_ids": sorted(value_pairs),
        "key_ids": sorted(key_map),
        "values": sorted({v for pairs in value_pairs.values() for pair in pairs for v in pair}),
    }
    for name, expected in expected_sets.items():
        observed = design.get(name)
        if (
            type(observed) is not list
            or any(type(v) is not int for v in observed)
            or observed != expected
        ):
            raise LabError(f"declared {name} coverage disagrees with the full panel design")
    if not 1 <= expected_pairs <= 1_000_000:
        raise LabError("declared design exceeds the supported complete-pair budget")
    return design, families, key_map, value_pairs, expected_pairs


def audit_association_panel(panel):
    """Audit literal oracles and every cell of the frozen Cartesian design.

    Complete pairs alone do not establish whole-design coverage. Unversioned
    panels or arbitrary subsets must be regenerated with their intended design;
    they cannot receive the complete-design PASS from row-local checks.
    """
    design, families, key_map, value_pairs, expected_pairs = _declared_panel_design(
        panel.get("metadata")
    )
    x, lengths, targets = (
        np.asarray(panel.get(name)) for name in ("input_ids", "lengths", "target_ids")
    )
    try:
        prefix = bytes.fromhex(panel["metadata"]["prefix_hex"])
        filler = bytes.fromhex(panel["metadata"]["filler_hex"])
    except (KeyError, TypeError, ValueError) as exc:
        raise LabError("panel prefix or filler declaration is malformed") from exc
    _fill(filler, 0)
    if (
        x.dtype != np.uint8
        or x.ndim != 2
        or not 1 <= len(x) <= 2_000_000
        or lengths.shape != (len(x),)
        or targets.shape != (len(x),)
        or lengths.dtype.kind not in "iu"
        or targets.dtype.kind not in "iu"
        or np.any(lengths < 1)
        or np.any(lengths > x.shape[1])
        or np.any(targets < 0)
        or np.any(targets > 255)
    ):
        raise LabError("panel storage shapes or byte dtype differ")
    names = (
        "family_ids",
        "stratum_ids",
        "assignment",
        "order",
        "query",
        "query_key_ids",
        "delay",
        "condition",
        "task",
        "position_offset",
        "full_input_hex",
        "pair_ids",
    )
    fields = {name: np.asarray(panel.get(name)) for name in names}
    if any(field.shape != (len(x),) for field in fields.values()):
        raise LabError("panel metadata fields must align to every stored row")
    if any(
        fields[name].dtype.kind not in "iu"
        for name in names
        if name not in ("condition", "task", "full_input_hex")
    ):
        raise LabError("panel row identities and design factors must be integer arrays")
    panel = {**panel, **fields}
    candidates = np.asarray(panel.get("candidate_ids"))
    if (
        candidates.shape != (len(x), 2)
        or candidates.dtype.kind not in "iu"
        or np.any(candidates > 255)
        or np.any(candidates < 0)
    ):
        raise LabError("panel requires exactly two byte candidates per row")
    if np.any(candidates[:, 0] == candidates[:, 1]) or not np.all(
        (candidates == targets[:, None]).any(axis=1)
    ):
        raise LabError("panel candidates must be distinct and include the target")
    if np.any((panel["assignment"] != 0) & (panel["assignment"] != 1)) or np.any(
        (panel["query"] != 0) & (panel["query"] != 1)
    ):
        raise LabError("assignment and query metadata must be binary")
    for i, (length, target, encoded) in enumerate(zip(lengths, targets, panel["full_input_hex"])):
        try:
            full = bytes.fromhex(str(encoded))
        except ValueError as exc:
            raise LabError("malformed literal prompt encoding") from exc
        if not full.startswith(prefix):
            raise LabError("panel prefix identity differs")
        raw = full[len(prefix) :]
        two = panel["task"][i] == "two_binding"
        delay = int(panel["delay"][i])
        identity = int(panel["family_ids"][i])
        if identity not in value_pairs or tuple(candidates[i]) not in value_pairs[identity]:
            raise LabError("row references an undeclared family or value pair")
        if two:
            conditions = ("full", "local3") if design["include_local3"] else ("full",)
            if (
                not families
                or delay not in design["delays"]
                or panel["order"][i] not in (0, 1)
                or panel["condition"][i] not in conditions
            ):
                raise LabError("row lies outside the declared two-binding Cartesian design")
            if (
                len(raw) != 10 + delay
                or raw[3:4] != b" "
                or raw[7:8] != b" "
                or raw[8:-2] != _fill(filler, delay)
            ):
                raise LabError("malformed two-binding literal prompt")
            bindings = [(raw[:2], raw[2]), (raw[4:6], raw[6])]
        else:
            if (
                not design["include_copy"]
                or delay != 0
                or panel["order"][i] != -1
                or panel["condition"][i] != "full"
            ):
                raise LabError("row lies outside the declared one-binding control design")
            if panel["task"][i] != "one_binding" or len(raw) != 6 or raw[3:4] != b" ":
                raise LabError("malformed one-binding literal prompt")
            bindings = [(raw[:2], raw[2])]
        matches = [value for key, value in bindings if key == raw[-2:]]
        if (
            len(matches) != 1
            or matches[0] != target
            or len({k for k, _ in bindings}) != len(bindings)
        ):
            raise LabError("literal binding oracle differs from target or is ambiguous")
        for key, _ in bindings:
            expected = [
                len(prefix) + j * 4 for j, (other, _) in enumerate(bindings) if other == key
            ]
            if key == raw[-2:]:
                expected.append(len(full) - 2)
            observed = [j for j in range(len(full) - 1) if full[j : j + 2] == key]
            if expected != observed:
                raise LabError("cue has an ambiguous extra occurrence outside binding/query slots")
        if families:
            family = families.get(panel["family_ids"][i])
            if family is None:
                raise LabError("row references an undeclared family")
            keys = [bytes.fromhex(v) for v in family["keys"]]
            query = int(panel["query"][i])
            assignment = int(panel["assignment"][i])
            if raw[-2:] != keys[query] or panel["query_key_ids"][i] != family["key_ids"][query]:
                raise LabError("query role or key identity disagrees with literal prompt")
            if panel["stratum_ids"][i] != STRATA.index(family["stratum"]):
                raise LabError("overlap stratum differs from family metadata")
            if target != candidates[i, assignment if query == 0 else 1 - assignment]:
                raise LabError("target disagrees with candidate assignment metadata")
            if two and (panel["order"][i] not in (0, 1) or raw[:2] != keys[int(panel["order"][i])]):
                raise LabError("presentation order disagrees with literal prompt")
            if two:
                order = int(panel["order"][i])
                expected_bindings = [
                    (keys[j], candidates[i, assignment if j == 0 else 1 - assignment])
                    for j in (order, 1 - order)
                ]
                if bindings != expected_bindings:
                    raise LabError("binding keys or values differ from the declared assignment")
        elif panel["metadata"]["kind"] == "copy_control":
            if (
                target != candidates[i, int(panel["assignment"][i])]
                or panel["family_ids"][i] != panel["query_key_ids"][i]
                or raw[-2:] != key_map[identity]
                or panel["query"][i] != 0
                or panel["stratum_ids"][i] != 2
            ):
                raise LabError("copy-control key or assignment metadata differs")
        if panel["condition"][i] not in ("full", "local3"):
            raise LabError("unknown full/local context condition")
        expected = full if panel["condition"][i] == "full" else full[-3:]
        offset = 0 if panel["condition"][i] == "full" else len(full) - 3
        if (
            int(length) != len(expected)
            or bytes(x[i, :length]) != expected
            or panel["position_offset"][i] != offset
        ):
            raise LabError("stored input or matched-position local control differs")
    pairs = defaultdict(list)
    for i, p in enumerate(panel["pair_ids"]):
        pairs[int(p)].append(i)
    cells = set()
    for members in pairs.values():
        if len(members) != 2:
            raise LabError("a panel pair is incomplete")
        a, b = members
        if set(panel["assignment"][members].tolist()) != {0, 1} or targets[a] == targets[b]:
            raise LabError("a counterfactual pair does not swap assignments and targets")
        if panel["family_ids"][a] != panel["family_ids"][b]:
            raise LabError("pair crosses families")
        if any(
            panel[name][a] != panel[name][b]
            for name in (
                "stratum_ids",
                "order",
                "query",
                "query_key_ids",
                "delay",
                "condition",
                "task",
                "position_offset",
            )
        ):
            raise LabError("paired counterfactual metadata differs")
        if not np.array_equal(candidates[a], candidates[b]):
            raise LabError("paired candidate vocabularies differ")
        cell = (
            int(panel["family_ids"][a]),
            tuple(candidates[a]),
            int(panel["delay"][a]),
            int(panel["order"][a]),
            int(panel["query"][a]),
            str(panel["condition"][a]),
            str(panel["task"][a]),
        )
        if cell in cells:
            raise LabError("duplicate Cartesian design cell, even if pair IDs differ")
        cells.add(cell)
        if panel["task"][a] == "two_binding":
            left, right = (bytes.fromhex(str(panel["full_input_hex"][j])) for j in members)
            if left[-3:] != right[-3:] or Counter(left) != Counter(right):
                raise LabError("counterfactual pair changes its suffix or byte histogram")
    # Membership plus uniqueness plus the declared product size establishes
    # completeness without allocating a second potentially million-cell set.
    if len(cells) != expected_pairs:
        raise LabError("panel omits cells from its frozen complete Cartesian design")
    for name, field in (("family_ids", "family_ids"), ("key_ids", "query_key_ids")):
        if np.unique(panel[field]).tolist() != design[name]:
            raise LabError("panel lacks declared family or key coverage")
    if np.unique(targets).tolist() != design["values"]:
        raise LabError("panel lacks declared answer-value coverage")
    return {
        "status": "PASS",
        "scope": "complete_declared_design",
        "rows": len(x),
        "pairs": len(pairs),
        "expected_rows": 2 * expected_pairs,
        "expected_pairs": expected_pairs,
        "literal_oracle_rows": len(x),
        "padding_is_not_input": True,
        "new_model_forwards": 0,
        "family_coverage": np.unique(panel["family_ids"]).tolist(),
        "key_coverage": np.unique(panel["query_key_ids"]).tolist(),
        "value_coverage": np.unique(targets).tolist(),
    }


def training_byte_frequency(training_records):
    """Byte bins from TRAIN without separators, case conversion or outcome selection."""
    records = _training_records(training_records)
    counts = sum(
        (np.bincount(np.frombuffer(raw, dtype=np.uint8), minlength=256) for raw in records),
        np.zeros(256, dtype=np.int64),
    )
    total = int(counts.sum())
    groups = np.where(
        counts == 0, 0, np.where(counts * 1000 < total, 1, np.where(counts * 100 < total, 2, 3))
    )
    return {
        "counts": counts,
        "total_bytes": total,
        "byte_groups": groups,
        "group_names": [
            "unseen",
            "seen_below_0.001",
            "frequency_0.001_to_below_0.01",
            "frequency_at_least_0.01",
        ],
        "record_sha256": [hashlib.sha256(raw).hexdigest() for raw in records],
        "split": "train",
    }


def position_conditions(
    *, short_gap=8, long_gap=40, prefix_length=32, global_offset=8, position_limit=64
):
    """The eleven frozen physical-input / embedding-ID controls from cycle006."""
    if (
        any(
            type(v) is not int or v < 0
            for v in (short_gap, long_gap, prefix_length, global_offset, position_limit)
        )
        or short_gap < 1
        or long_gap < 4
    ):
        raise LabError("invalid position-condition lengths")
    specs = [
        ("gap8_native", short_gap, 0, 0, False, False, "original"),
        ("gap40_native", long_gap, 0, 0, False, False, "original"),
        ("gap8_global8", short_gap, 0, global_offset, False, False, "original"),
        ("gap40_global8", long_gap, 0, global_offset, False, False, "original"),
        ("gap8_global32", short_gap, 0, prefix_length, False, False, "original"),
        ("gap40_query16", long_gap, 0, 0, True, False, "original"),
        ("gap40_fillerwrap", long_gap, 0, 0, False, True, "original"),
        ("gap40_query16_fillerwrap", long_gap, 0, 0, True, True, "original"),
        ("prefix32_gap8", short_gap, prefix_length, 0, False, False, "original"),
        ("gap40_phase_swap", long_gap, 0, 0, False, False, "phase_swap"),
        ("gap40_spaces", long_gap, 0, 0, False, False, "spaces"),
    ]
    result = []
    for name, gap, prefix, offset, reset, wrap, content in specs:
        length = prefix + 10 + gap
        ids = np.arange(length) + offset
        if wrap:
            ids[prefix + 8 : prefix + 8 + gap] = 8 + np.arange(gap) % short_gap
        if reset:
            ids[-2:] = [8 + short_gap, 9 + short_gap]
        if ids.max() >= position_limit:
            raise LabError("position intervention exceeds the declared embedding table")
        positional = bool(offset or reset or wrap)
        result.append(
            {
                "name": name,
                "gap": gap,
                "prefix_length": prefix,
                "length": length,
                "position_ids": ids.tolist(),
                "query_position_reset": reset,
                "filler_position_wrap": wrap,
                "position_offset": offset,
                "filler_content": content,
                "position_only_intervention": positional,
                "recurrent_alias_of": ("gap8_native" if gap == short_gap else "gap40_native")
                if positional
                else None,
                "scope": (
                    "physical causal order unchanged; reused position IDs are nonnative"
                    " interventions"
                ),
            }
        )
    return result


def condition_prompt(binding_prefix, query_bytes, specification, *, filler=FILLER):
    _byte_string(binding_prefix, "binding prefix")
    _byte_string(query_bytes, "query bytes")
    if len(binding_prefix) != 8 or len(query_bytes) != 2:
        raise LabError("position panel needs eight-byte binding prefix and two-byte query")
    gap = specification["gap"]
    content = _fill(filler, gap)
    if specification["filler_content"] == "phase_swap":
        shifted = filler[len(filler) // 2 :] + filler[: len(filler) // 2]
        content = _fill(shifted, gap - 4) + content[-4:]
    elif specification["filler_content"] == "spaces":
        content = b" " * (gap - 4) + content[-4:]
    elif specification["filler_content"] != "original":
        raise LabError("unknown filler intervention")
    return _fill(filler, specification["prefix_length"]) + binding_prefix + content + query_bytes


def position_contrasts():
    """Frozen contrast coefficients; positive accuracy is gain, positive NLL loss."""
    rows = [
        ("query_reset_at_native_filler", {"gap40_query16": 1, "gap40_native": -1}),
        ("filler_wrap_at_native_query", {"gap40_fillerwrap": 1, "gap40_native": -1}),
        ("query_reset_at_wrapped_filler", {"gap40_query16_fillerwrap": 1, "gap40_fillerwrap": -1}),
        ("filler_wrap_at_reset_query", {"gap40_query16_fillerwrap": 1, "gap40_query16": -1}),
        (
            "query_filler_interaction",
            {
                "gap40_query16_fillerwrap": 1,
                "gap40_query16": -1,
                "gap40_fillerwrap": -1,
                "gap40_native": 1,
            },
        ),
        ("global8_short", {"gap8_global8": 1, "gap8_native": -1}),
        ("global8_long", {"gap40_global8": 1, "gap40_native": -1}),
        ("gap_effect_offset0", {"gap40_native": 1, "gap8_native": -1}),
        ("gap_effect_offset8", {"gap40_global8": 1, "gap8_global8": -1}),
        (
            "gap_global_interaction",
            {"gap40_global8": 1, "gap8_global8": -1, "gap40_native": -1, "gap8_native": 1},
        ),
        ("global32_short", {"gap8_global32": 1, "gap8_native": -1}),
        ("prefix_beyond_position_shift", {"prefix32_gap8": 1, "gap8_global32": -1}),
        ("long_gap_vs_prefix_at_query49", {"gap40_native": 1, "prefix32_gap8": -1}),
        ("long_gap_vs_global32_at_query49", {"gap40_native": 1, "gap8_global32": -1}),
        ("phase_swap_long", {"gap40_phase_swap": 1, "gap40_native": -1}),
        ("spaces_long", {"gap40_spaces": 1, "gap40_native": -1}),
    ]
    return [
        {
            "name": name,
            "coefficients": coefficients,
            "role": "primary_in_transformer_balanced_replay" if i == 0 else "secondary",
        }
        for i, (name, coefficients) in enumerate(rows)
    ]
