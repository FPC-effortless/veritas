"""Recompute public, constructed changing-memory predictions; no qualification."""

from __future__ import annotations


def _text(value):
    return isinstance(value, str) and 0 < len(value) <= 256 and "\0" not in value


def state(memory):
    """Replay one causal prefix. None is absence, never a stored value."""
    if not isinstance(memory, dict) or set(memory) != {"keys", "events"}:
        raise ValueError("memory requires exactly keys and events")
    keys, events = memory["keys"], memory["events"]
    if (
        not isinstance(keys, list) or not 1 <= len(keys) <= 1024
        or not all(_text(key) for key in keys) or len(set(keys)) != len(keys)
        or not isinstance(events, list) or len(events) > 10000
    ):
        raise ValueError("invalid bounded memory prefix")
    current = dict.fromkeys(keys)
    previous = current.copy()
    history = {key: set() for key in keys}
    deleted = set()
    for event in events:
        if not isinstance(event, dict) or event.get("op") not in ("set", "delete"):
            raise ValueError("invalid memory operation")
        fields = {"op", "key", "value"} if event["op"] == "set" else {"op", "key"}
        if set(event) != fields or not _text(event["key"]) or event["key"] not in current:
            raise ValueError("invalid memory event fields or key")
        previous = current.copy()
        key = event["key"]
        if event["op"] == "set":
            if not _text(event["value"]):
                raise ValueError("stored values must be nonempty strings")
            current[key] = event["value"]
            history[key].add(event["value"])
            deleted.discard(key)
        else:
            current[key] = None
            deleted.add(key)
    untouched = {
        key for key in keys
        if events and key != events[-1]["key"] and previous[key] is not None
    }
    stale = {key: values - {current[key]} for key, values in history.items()}
    return current, stale, deleted, untouched


def score(examples, predictions):
    """Score complete maps keyed by Forge record_id, without trusting metrics."""
    if not isinstance(examples, list) or not examples or len(examples) > 10000:
        raise ValueError("nonempty bounded examples required")
    ids = [example["record_id"] for example in examples]
    if (
        not all(_text(identity) for identity in ids) or len(set(ids)) != len(ids)
        or not isinstance(predictions, dict) or set(predictions) != set(ids)
    ):
        raise ValueError("prediction identities must cover every example exactly")
    counts = {
        key: [0, 0] for key in (
            "current_answer_accuracy", "stale_answer_rate", "deletion_accuracy",
            "untouched_fact_accuracy", "complete_state_accuracy", "absent_answer_accuracy",
        )
    }

    def add(metric, correct):
        counts[metric][0] += int(correct)
        counts[metric][1] += 1

    for example in examples:
        features = example["features"]
        if set(features) != {"memory"} or example["target"] is not None:
            raise ValueError("only public memory prefixes without target labels are supported")
        expected, stale, deleted, untouched = state(features["memory"])
        predicted = predictions[example["record_id"]]
        if (
            not isinstance(predicted, dict) or set(predicted) != set(expected)
            or any(value is not None and not _text(value) for value in predicted.values())
        ):
            raise ValueError("each prediction must include the complete declared key universe")
        add("complete_state_accuracy", predicted == expected)
        for key, value in expected.items():
            correct = predicted[key] == value
            add("current_answer_accuracy", correct)
            if stale[key]:
                add("stale_answer_rate", predicted[key] in stale[key])
            if key in deleted:
                add("deletion_accuracy", correct)
            if key in untouched:
                add("untouched_fact_accuracy", correct)
            if value is None:
                add("absent_answer_accuracy", correct)
    return {
        metric: {"numerator": n, "denominator": d, "value": n / d if d else None}
        for metric, (n, d) in counts.items()
    }
