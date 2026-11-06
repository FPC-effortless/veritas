"""Independent grammar-aware control and shortcut diagnostics for CSA-v02.

Reads only natural-language history/query; it does not access event replay.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from csa_v02 import LENGTHS, SPLITS, generate, labeled_rows, cross_rows, model_view, SUFFIX

BA = re.compile(r"Record \d+: Project (\w+) is assigned to (\w+)\.")
BU = re.compile(r"Record \d+: Project (\w+) has no assigned person\.")
BL = re.compile(r"Record \d+: (\w+) is at the (\w+)\.")
BV = re.compile(r"Record \d+: (\w+) has no current location\.")
OA = re.compile(r"Entry \d+ appoints (\w+) as the custodian of project (\w+)\.")
OU = re.compile(r"Entry \d+ revokes the custodian for project (\w+)\.")
OL = re.compile(r"Entry \d+ places the person named (\w+) inside the (\w+)\.")
OV = re.compile(r"Entry \d+ reports that the whereabouts of (\w+) are unknown\.")
BQ = re.compile(r"Where is the custodian of project (\w+)\?")
OQ = re.compile(r"State the location of whoever is responsible for project (\w+)\.")


def symbolic(view: dict[str,str]) -> str:
    q = BQ.fullmatch(view["query"]) or OQ.fullmatch(view["query"])
    if q is None:
        raise ValueError("unsupported question")
    project = q.group(1)
    assigned: dict[str,str] = {}
    positions: dict[str,str] = {}
    for ln in view["history"].splitlines():
        if ln == SUFFIX:
            continue
        if m := BA.fullmatch(ln):
            assigned[m.group(1)] = m.group(2)
        elif m := BU.fullmatch(ln):
            assigned.pop(m.group(1), None)
        elif m := BL.fullmatch(ln):
            positions[m.group(1)] = m.group(2)
        elif m := BV.fullmatch(ln):
            positions.pop(m.group(1), None)
        elif m := OA.fullmatch(ln):
            assigned[m.group(2)] = m.group(1)
        elif m := OU.fullmatch(ln):
            assigned.pop(m.group(1), None)
        elif m := OL.fullmatch(ln):
            positions[m.group(1)] = m.group(2)
        elif m := OV.fullmatch(ln):
            positions.pop(m.group(1), None)
        else:
            raise ValueError("unknown record grammar")
    return positions.get(assigned.get(project,""),"UNKNOWN")


def ignore_latest(view: dict[str,str]) -> str:
    lines = view["history"].splitlines()
    if lines[-1] != SUFFIX:
        raise ValueError("missing suffix")
    return symbolic({"history":"\n".join(lines[:-2]+lines[-1:]),"query":view["query"]})


def last_location(view: dict[str,str]) -> str:
    words = []
    for ln in view["history"].splitlines():
        if m := BL.fullmatch(ln): words.append(m.group(2))
        elif m := OL.fullmatch(ln): words.append(m.group(2))
    return words[-1] if words else "UNKNOWN"


def evaluate(seed: int=49621, pairs: int=40) -> dict:
    result = {"mode":"NO_FIT","models_trained":0,"seed":seed,"pairs":pairs,"cells":{}}
    for si, split in enumerate(SPLITS):
        for length in LENGTHS:
            cases=generate(split,length,pairs,seed+1000003*si+length*67)
            rows=labeled_rows(cases)
            cross=cross_rows(cases)
            n=len(rows)
            control=sum(symbolic(model_view(r))==r["answer"] for r in rows)
            heuristic=sum(last_location(model_view(r))==r["answer"] for r in rows)
            ignore=sum(ignore_latest(model_view(r))==r["answer"] for r in rows)
            cross_control=sum(symbolic(model_view(r))==r["answer"] for r in cross)
            cross_ignore=sum(ignore_latest(model_view(r))==r["answer"] for r in cross)
            kind_results={}
            for k in sorted({p.kind for p in cases}):
                selection=[r for r in rows if r["kind"]==k]
                kind_results[k]={"n":len(selection),"ignore_latest":sum(ignore_latest(model_view(r))==r["answer"] for r in selection)}
            result["cells"][f"{split}_L{length}"]={"primary_n":n,"cross_n":len(cross),
                "strong_symbolic_accuracy":control/n,"naive_last_location_accuracy":heuristic/n,
                "ignore_latest_accuracy":ignore/n,"cross_symbolic_accuracy":cross_control/len(cross),
                "cross_ignore_latest_accuracy":cross_ignore/len(cross),"by_kind":kind_results}
    return result

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--output", type=Path, required=True)
    args=a.parse_args()
    args.output.write_text(json.dumps(evaluate(),indent=2,sort_keys=True)+"\n")
