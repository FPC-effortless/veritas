"""Offline, content-bound diagnostic inspection; never execute imported packs."""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import html
import json
import re
import stat
import zipfile
from pathlib import Path

from .prediction_artifacts import MAX_BYTES, _bytes, _hash, _require, _text
from .runner import LabError, _constant, _pairs

STATUSES = ("TESTED", "FAILED", "INCONCLUSIVE", "UNSUPPORTED", "NOT_RUN")
KINDS = ("observation", "hypothesis", "intervention", "conclusion")
SCRIPT = """const filter=document.getElementById('status');
filter.addEventListener('change',()=>{for(const card of document.querySelectorAll('article')){
card.hidden=filter.value!=='ALL'&&card.dataset.status!==filter.value;}});"""


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _parse(data):
    _require(len(data) <= MAX_BYTES, "JSON size limit exceeded")
    try:
        value = json.loads(data, object_pairs_hook=_pairs, parse_constant=_constant)
        _bytes(value)
        return value
    except (ValueError, UnicodeError, OverflowError, RecursionError) as exc:
        raise LabError("invalid bounded finite JSON") from exc


def _read(path, pin):
    _require(_hash(pin), "external SHA256 required")
    _require(path.is_file() and not path.is_symlink(), "regular non-symlink input required")
    with path.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    _require(len(data) <= MAX_BYTES and _sha(data) == pin, "artifact size/hash mismatch")
    return data


def _safe(base, relative):
    _require(
        type(relative) is str
        and 0 < len(relative) <= 500
        and re.fullmatch(r"[A-Za-z0-9_./-]+", relative)
        and all(p not in ("", ".", "..") for p in relative.split("/"))
        and not relative.startswith("/"),
        "safe relative path required",
    )
    path = base
    for part in relative.split("/"):
        path = path / part
        _require(not path.is_symlink(), "symlink inputs are unsupported")
    _require(
        path.is_file() and path.resolve().is_relative_to(base.resolve()),
        "regular file inside specification directory required",
    )
    return path


def _strings(value):
    return type(value) is list and len(value) <= 32 and all(_text(x) for x in value)


def _validate(spec):
    _require(
        type(spec) is dict
        and set(spec) == {"schema", "title", "data_classification", "packs", "findings"}
        and spec["schema"] == "trainlab.diagnostic-bundle-spec.v1"
        and _text(spec["title"])
        and spec["data_classification"] in ("PUBLIC_AUTHORIZED", "CONSTRUCTED_PUBLIC"),
        "public-authorized bundle specification required",
    )
    packs, findings = spec["packs"], spec["findings"]
    _require(
        type(packs) is list
        and 1 <= len(packs) <= 64
        and type(findings) is list
        and 1 <= len(findings) <= 200,
        "bounded packs/findings required",
    )
    ids = []
    for pack in packs:
        _require(
            type(pack) is dict
            and set(pack)
            == {
                "id",
                "version",
                "applicability",
                "dependencies",
                "cost",
                "evidence_requirements",
                "limitations",
            }
            and all(_text(pack[k]) for k in ("id", "version", "applicability", "cost"))
            and all(
                _strings(pack[k]) for k in ("dependencies", "evidence_requirements", "limitations")
            ),
            "invalid pack metadata",
        )
        ids.append(pack["id"])
    _require(len(set(ids)) == len(ids), "duplicate pack identity")
    finding_ids = []
    for finding in findings:
        _require(
            type(finding) is dict
            and set(finding)
            == {"id", "pack_id", "kind", "summary", "status", "evidence", "reviews"}
            and _text(finding["id"])
            and finding["pack_id"] in ids
            and finding["kind"] in KINDS
            and _text(finding["summary"])
            and finding["status"] in STATUSES,
            "invalid finding",
        )
        finding_ids.append(finding["id"])
        evidence, reviews = finding["evidence"], finding["reviews"]
        _require(type(reviews) is list and len(reviews) <= 8, "bounded reviews required")
        if evidence is None:
            _require(
                finding["status"] in ("UNSUPPORTED", "NOT_RUN") and not reviews,
                "observed results and reviews require exact evidence",
            )
            continue
        _require(
            type(evidence) is dict
            and set(evidence) == {"path", "sha256", "pointer"}
            and _hash(evidence["sha256"])
            and type(evidence["pointer"]) is list
            and len(evidence["pointer"]) <= 32
            and all(_text(k) or (type(k) is int and 0 <= k < 10000) for k in evidence["pointer"]),
            "invalid evidence binding",
        )
        for review in reviews:
            _require(
                type(review) is dict
                and set(review) == {"reviewer", "note", "report_sha256"}
                and _text(review["reviewer"])
                and _text(review["note"])
                and review["report_sha256"] == evidence["sha256"],
                "review must bind exact evidence hash",
            )
    _require(len(set(finding_ids)) == len(finding_ids), "duplicate finding identity")


def _node(document, pointer):
    value = document
    for key in pointer:
        _require(
            (type(value) is dict and type(key) is str and key in value)
            or (type(value) is list and type(key) is int and 0 <= key < len(value)),
            "evidence pointer not found",
        )
        value = value[key]
    return value


def render(bundle):
    def esc(value):
        return html.escape(str(value), quote=True)

    counts = {s: sum(f["status"] == s for f in bundle["findings"]) for s in STATUSES}
    cards = []
    for finding in bundle["findings"]:
        evidence = finding["evidence"]
        detail = "No evidence inspected."
        if evidence:
            detail = (
                f'<a href="{esc(evidence["artifact"])}">Raw JSON evidence</a>'
                f'<p class="hash">SHA256 {esc(evidence["sha256"])}</p>'
                f"<pre>{esc(finding['preview'])}</pre>"
            )
        notes = "".join(
            f"<p><b>{esc(r['reviewer'])}</b>: {esc(r['note'])}</p>" for r in finding["reviews"]
        )
        cards.append(
            f'<article data-status="{finding["status"]}"><div class="eyebrow">'
            f"{esc(finding['kind'])} · {esc(finding['pack_id'])}</div>"
            f'<h2>{esc(finding["id"])}</h2><strong class="status">'
            f"{finding['status']}</strong><p>{esc(finding['summary'])}</p>"
            f"<details><summary>Inspect evidence and review notes</summary>{detail}"
            f"{notes}</details></article>"
        )
    packs = "".join(
        f"<details><summary>{esc(p['id'])} · {esc(p['version'])}</summary>"
        f"<pre>{esc(json.dumps(p, indent=2))}</pre></details>"
        for p in bundle["packs"]
    )
    script_hash = base64.b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()
    options = '<option value="ALL">All statuses</option>' + "".join(
        f'<option value="{s}">{s} ({counts[s]})</option>' for s in STATUSES
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none';

script-src 'sha256-{script_hash}';

style-src 'unsafe-inline';
 base-uri 'none';
 form-action 'none'">
<title>{esc(bundle["title"])}</title><style>
*{{box-sizing:border-box}}
body{{margin:0;
background:#eef2f5;
color:#172536;
font:16px/1.55 system-ui,sans-serif}}

main{{max-width:1000px;
overflow-wrap:anywhere;
margin:auto;
padding:28px 18px 60px}}
header{{background:#102c3b;
color:white;
padding:28px;
border-radius:16px}}

h1{{font-size:clamp(25px,4vw,38px);
line-height:1.15;
margin:10px 0}}
h2{{font-size:20px;
margin:8px 0}}

.eyebrow{{font-size:12px;
letter-spacing:.08em;
text-transform:uppercase;
overflow-wrap:anywhere}}

.notice{{padding:16px;
border-left:4px solid #d59b36;
background:#fff8e8}}
.grid{{display:grid;
grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));
gap:16px}}

article{{background:white;
padding:22px;
border:1px solid #d4dee5;
border-radius:12px;
min-width:0}}
article[hidden]{{display:none}}

.status{{font-size:12px;
letter-spacing:.06em}}
article[data-status=FAILED] .status{{color:#ac2735}}

article[data-status=INCONCLUSIVE] .status{{color:#8a5a00}}
details{{margin-top:16px}}
summary{{cursor:pointer}}

pre{{white-space:pre-wrap;
overflow-wrap:anywhere;
background:#f3f6f8;
padding:12px;
font-size:12px;
max-height:320px;
overflow:auto}}

.hash{{font-size:11px;
overflow-wrap:anywhere}}
select{{padding:10px;
margin:18px 0;
font:inherit;
max-width:100%}}
a{{color:#175d9c}}

footer{{font-size:13px;
margin-top:28px;
color:#52616e}}
label{{display:block;
margin-top:18px}}

</style></head><body><main><header><div class="eyebrow">VERITAS / RESEARCH DIAGNOSTICS</div>
<h1>{esc(bundle["title"])}</h1>
<p>Inspect failures, evidence and coverage in one offline report.</p></header>
<p class="notice">Scientific qualification: NOT QUALIFIED. TESTED means the declared check ran;
it does not mean the model is healthy. Hypotheses and review identities are caller declarations.</p>
<label for="status">Filter findings</label><select id="status">{options}</select>
<section class="grid">{"".join(cards)}</section><h2>Pack contracts and limitations</h2>{packs}
<footer>Public-authorized content declaration • No imported code executed • No overall health score
<p class="hash">Specification SHA256 {esc(bundle["specification_sha256"])}</p></footer></main>
<script>{SCRIPT}</script></body></html>"""


def create(specification, sha256, root):
    """Validate all inputs before writing a new offline bundle; return manifest pin."""
    specification, root = Path(specification), Path(root)
    _require(not specification.is_symlink(), "symlink specification unsupported")
    spec = _parse(_read(specification, sha256))
    _validate(spec)
    bundle = copy.deepcopy(spec)
    bundle.update(
        schema="trainlab.diagnostic-bundle.v1",
        specification_sha256=sha256,
        scientific_qualification="NOT_QUALIFIED",
        review_identity="CALLER_DECLARED",
    )
    artifacts, pins, total = {}, {}, 0
    for finding in bundle["findings"]:
        finding["preview"] = None
        evidence = finding["evidence"]
        if evidence is None:
            continue
        key = (evidence["path"], evidence["sha256"])
        if key not in pins:
            _require(len(pins) < 32, "at most 32 source files supported")
            raw = _read(_safe(specification.parent, evidence["path"]), evidence["sha256"])
            document = _parse(raw)
            total += len(raw)
            _require(total <= 32 * 1024**2, "aggregate evidence size exceeded")
            name = f"evidence/{len(pins):03}.json"
            artifacts[name] = raw
            pins[key] = (name, document)
        name, document = pins[key]
        node = _node(document, evidence["pointer"])
        _require(
            type(node) is dict and node.get("status") == finding["status"],
            "finding status must match exact source node",
        )
        preview = json.dumps(node, indent=2)
        finding["preview"] = preview[:8000] + (
            "\n[Preview truncated; inspect raw JSON]" if len(preview) > 8000 else ""
        )
        evidence["artifact"] = name
    artifacts["bundle.json"] = _bytes(bundle)
    artifacts["index.html"] = render(bundle).encode()
    _require(
        all(len(data) <= MAX_BYTES for data in artifacts.values())
        and sum(map(len, artifacts.values())) <= 64 * 1024**2,
        "rendered bundle exceeds output limits",
    )
    manifest = {
        "schema": "trainlab.diagnostic-bundle-manifest.v1",
        "files": [
            {"path": name, "bytes": len(data), "sha256": _sha(data)}
            for name, data in sorted(artifacts.items())
        ],
    }
    raw_manifest = _bytes(manifest)
    root.mkdir(parents=True, mode=0o700, exist_ok=False)
    for name, data in artifacts.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (root / "manifest.json").write_bytes(raw_manifest)
    return _sha(raw_manifest)


def _verified(root, sha256):
    """Require an external manifest pin; reject extra, missing, changed or linked files."""
    root = Path(root)
    _require(not root.is_symlink() and root.is_dir(), "regular bundle directory required")
    raw_manifest = _read(_safe(root, "manifest.json"), sha256)
    manifest = _parse(raw_manifest)
    snapshot = {"manifest.json": raw_manifest}
    _require(
        type(manifest) is dict
        and set(manifest) == {"schema", "files"}
        and manifest["schema"] == "trainlab.diagnostic-bundle-manifest.v1"
        and type(manifest["files"]) is list
        and 2 <= len(manifest["files"]) <= 34,
        "invalid manifest",
    )
    expected, total = {"manifest.json"}, 0
    for item in manifest["files"]:
        _require(
            type(item) is dict
            and set(item) == {"path", "bytes", "sha256"}
            and type(item["path"]) is str
            and re.fullmatch(r"(?:bundle\.json|index\.html|evidence/[0-9]{3}\.json)", item["path"])
            and item["path"] not in expected
            and type(item["bytes"]) is int
            and 0 <= item["bytes"] <= MAX_BYTES,
            "invalid manifest file",
        )
        data = _read(_safe(root, item["path"]), item["sha256"])
        _require(len(data) == item["bytes"], "artifact length mismatch")
        total += len(data)
        _require(total <= 64 * 1024**2, "bundle size exceeded")
        expected.add(item["path"])
        snapshot[item["path"]] = data
    _require({"bundle.json", "index.html"} <= expected, "missing bundle/index")
    observed = set()
    for path in root.rglob("*"):
        _require(not path.is_symlink(), "symlink bundle entry")
        if not path.is_dir():
            _require(stat.S_ISREG(path.stat().st_mode), "non-regular bundle entry")
            observed.add(path.relative_to(root).as_posix())
    _require(expected == observed, "unexpected or missing bundle files")
    return snapshot, {
        "valid": True,
        "manifest_sha256": sha256,
        "files": len(expected),
        "scope": "BYTE_INTEGRITY_NOT_TRUTH_OR_SIGNATURE",
    }


def verify(root, sha256):
    """Verify byte integrity against an externally retained manifest hash."""
    return _verified(root, sha256)[1]


def export(root, sha256, destination):
    """Verify before ZIP export; never extract or execute imported material."""
    snapshot, _ = _verified(root, sha256)
    destination = Path(destination)
    _require(
        not destination.resolve().is_relative_to(Path(root).resolve()),
        "export must be outside source bundle",
    )
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(snapshot.items()):
            archive.writestr(name, data)
    return {"path": str(destination), "sha256": _sha(destination.read_bytes())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("create", "verify", "export"))
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--zip", type=Path)
    args = parser.parse_args()
    if args.action == "create" and args.spec:
        result = {"manifest_sha256": create(args.spec, args.sha256, args.root)}
    elif args.action == "verify":
        result = verify(args.root, args.sha256)
    elif args.action == "export" and args.zip:
        result = export(args.root, args.sha256, args.zip)
    else:
        parser.error("create requires --spec; export requires --zip")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
