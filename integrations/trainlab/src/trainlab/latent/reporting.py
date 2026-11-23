"""Source-bound tables, shareable figures, reports and a local latent atlas."""

from __future__ import annotations

import csv
import html
import json
from pathlib import Path

import numpy as np

from ..runner import LabError, write_json
from .artifacts import NAME, require, resolve


def metric_rows(value, path=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from metric_rows(item, f"{path}.{key}" if path else key)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from metric_rows(item, f"{path}[{index}]")
    elif isinstance(value, (int, float, np.number)) and not isinstance(value, (bool, np.bool_)):
        yield path, float(value)


def _finite_array(value, *, ndim=None):
    a = np.asarray(value, dtype=np.float64)
    require(
        a.size > 0
        and a.size <= 2_000_000
        and np.isfinite(a).all()
        and (ndim is None or a.ndim == ndim),
        "invalid finite plot data",
    )
    return a


def draw_figure(spec, destination):
    """Render declared numerical data; never infer scientific qualification."""
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    require(
        type(spec) is dict and isinstance(spec.get("id"), str) and NAME.fullmatch(spec["id"]),
        "bounded unique figure ID required",
    )
    kind, data = spec.get("kind"), spec.get("data", {})
    require(type(data) is dict, "figure data must be an object")
    fig, ax = plt.subplots(figsize=(7.6, 4.8), constrained_layout=True)
    try:
        if kind in ("scatter", "trajectory"):
            coordinates = _finite_array(data["coordinates"], ndim=2)
            require(coordinates.shape[1] >= 2, "two coordinates required")
            groups = np.asarray(data.get("groups", ["observations"] * len(coordinates)), dtype=str)
            require(groups.shape == (len(coordinates),), "scatter groups misaligned")
            for label in np.unique(groups):
                selected = coordinates[groups == label]
                ax.scatter(selected[:, 0], selected[:, 1], s=12, alpha=0.7, label=str(label))
                if kind == "trajectory":
                    ax.plot(selected[:, 0], selected[:, 1], alpha=0.45, linewidth=1)
                    ax.scatter(*selected[-1, :2], s=45, marker="x")
            if len(np.unique(groups)) <= 12:
                ax.legend(frameon=False, fontsize=8)
        elif kind == "heatmap":
            values = _finite_array(data["values"], ndim=2)
            image = ax.imshow(values, aspect="auto", cmap=spec.get("cmap", "viridis"))
            fig.colorbar(image, ax=ax, label=spec.get("unit", "value"))
            if "row_labels" in data:
                require(len(data["row_labels"]) == values.shape[0], "row label count mismatch")
                ax.set_yticks(range(values.shape[0]), data["row_labels"])
            if "column_labels" in data:
                require(
                    len(data["column_labels"]) == values.shape[1], "column label count mismatch"
                )
                ax.set_xticks(
                    range(values.shape[1]), data["column_labels"], rotation=35, ha="right"
                )
        elif kind == "forest":
            point, low, high = (_finite_array(data[k], ndim=1) for k in ("point", "lower", "upper"))
            require(
                point.shape == low.shape == high.shape and np.all(low <= high),
                "forest interval shape/order mismatch",
            )
            labels = data.get("labels", [str(i) for i in range(len(point))])
            require(len(labels) == len(point), "forest labels mismatch")
            positions = np.arange(len(point))
            ax.hlines(positions, low, high, color="#3c6eab", linewidth=2)
            ax.scatter(point, positions, color="#153d69", s=28)
            ax.axvline(0, color="#777", linestyle=":", linewidth=1)
            ax.set_yticks(positions, labels)
            ax.invert_yaxis()
        elif kind in ("curve", "spectrum", "reliability", "cdf"):
            series = data.get("series")
            if series is None:
                series = {"observed": data["y"]}
            require(type(series) is dict and 1 <= len(series) <= 32, "bounded plot series required")
            for label, values in series.items():
                y = _finite_array(values, ndim=1)
                if kind == "cdf":
                    x = np.sort(y)
                    y = np.arange(1, len(y) + 1) / len(y)
                else:
                    x = _finite_array(data.get("x", np.arange(1, len(y) + 1)), ndim=1)
                require(x.shape == y.shape, "curve coordinate mismatch")
                ax.plot(x, y, marker="o" if len(x) <= 30 else None, linewidth=1.6, label=label)
            if kind == "reliability":
                ax.plot([0, 1], [0, 1], linestyle=":", color="#777")
                ax.set(xlim=(0, 1), ylim=(0, 1))
            if len(series) > 1:
                ax.legend(frameon=False, fontsize=8)
        elif kind == "stacked":
            values = _finite_array(data["values"], ndim=2)
            labels = data.get("labels", [str(i) for i in range(values.shape[0])])
            groups = data.get("groups", [str(i) for i in range(values.shape[1])])
            require(
                len(labels) == values.shape[0] and len(groups) == values.shape[1],
                "stacked labels mismatch",
            )
            positive, negative = np.zeros(len(values)), np.zeros(len(values))
            for i, label in enumerate(groups):
                y = values[:, i]
                bottom = np.where(y >= 0, positive, negative)
                ax.bar(np.arange(len(values)), y, bottom=bottom, label=label)
                positive += np.maximum(y, 0)
                negative += np.minimum(y, 0)
            ax.axhline(0, linewidth=0.7, color="#777")
            ax.set_xticks(range(len(labels)), labels, rotation=25, ha="right")
            ax.legend(frameon=False, fontsize=8)
        else:
            raise LabError("unsupported figure kind")
        ax.set_title(spec.get("title", spec["id"]), loc="left", fontsize=13)
        ax.set_xlabel(spec.get("xlabel", ""))
        ax.set_ylabel(spec.get("ylabel", ""))
        if kind != "heatmap":
            ax.spines[["top", "right"]].set_visible(False)
            ax.grid(alpha=0.15)
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        paths = []
        for extension in ("png", "svg", "pdf"):
            path = destination / f"{spec['id']}.{extension}"
            fig.savefig(path, dpi=150)
            paths.append(path.name)
        return paths
    finally:
        plt.close(fig)


def _jsonable(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def atlas(views, destination, *, title="Latent atlas"):
    """Self-contained 2D/3D exploration of declared aligned observations.

    PCA/t-SNE are computed before rendering; coordinates are never generated by
    the viewer. Context fields belong to the operator's authorized local panel.
    """
    require(isinstance(views, list) and 1 <= len(views) <= 128, "bounded atlas views required")
    clean = []
    for view in views:
        coordinates = _finite_array(view["coordinates"], ndim=2)
        require(
            coordinates.shape[1] in (2, 3) and len(coordinates) <= 20000,
            "atlas requires bounded 2D/3D coordinates",
        )
        labels = view.get("rows", [{"id": i} for i in range(len(coordinates))])
        require(
            type(labels) is list
            and len(labels) == len(coordinates)
            and all(type(row) is dict for row in labels),
            "atlas rows misaligned",
        )
        clean.append(
            {
                "label": str(view["label"]),
                "coordinates": coordinates.tolist(),
                "rows": _jsonable(labels),
                "metadata": _jsonable(view.get("metadata", {})),
            }
        )
    payload = json.dumps(clean, allow_nan=False).replace("<", "\\u003c").replace("&", "\\u0026")
    require(len(payload) <= 32 * 1024 * 1024, "atlas exceeds supported size")
    document = _ATLAS.replace("__TITLE__", html.escape(title)).replace("__DATA__", payload)
    Path(destination).write_text(document, encoding="utf-8")
    return {"views": len(clean), "points": sum(len(v["rows"]) for v in clean)}


def render(plan, results, coverage, root, *, inputs=None):
    root = Path(root)
    summary = {
        "schema": "trainlab.latent-summary.v1",
        "title": plan["title"],
        "identities": plan["identities"],
        "coverage": coverage,
        "subchecks": [],
        "scientific_qualification": "NOT_QUALIFIED",
        "figures": [],
        "figure_errors": [],
    }
    table = []
    by_id = {job["id"]: job for job in plan["jobs"]}
    for identity, result in results.items():
        job = by_id[identity]
        if (
            isinstance(result, dict)
            and result.get("schema") == "trainlab.experiment-diagnostics.v1"
        ):
            summary["subchecks"].extend(
                {
                    "name": f"{identity}/{row['name']}",
                    "status": row["status"],
                    "reason": "REUSED_DIAGNOSTIC_SUBCHECK",
                }
                for row in result.get("coverage", [])
            )
        for metric, value in metric_rows(result):
            table.append(
                {
                    "job": identity,
                    "operation": job["operation"],
                    "metric": metric,
                    "value": value,
                    "unit": job.get("unit", "see metric definition"),
                    "role": job.get("role", "exploratory"),
                    "scope": job.get("scope", "declared observed panel"),
                    "source": f"results/{identity}.json",
                }
            )
    with (root / "metrics.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["job", "operation", "metric", "value", "unit", "role", "scope", "source"],
        )
        writer.writeheader()
        writer.writerows(table)
    seen = set()
    atlas_views = []
    for declaration in plan.get("figures", []):
        identity = declaration.get("id", "invalid")
        try:
            require(identity not in seen, "duplicate figure ID")
            seen.add(identity)
            spec = resolve(declaration, inputs or {}, results)
            paths = draw_figure(spec, root / "figures")
            data = _jsonable(spec)
            write_json(root / "figures" / f"{identity}.data.json", data)
            summary["figures"].append(
                {"id": identity, "files": paths, "title": spec.get("title", identity)}
            )
            if spec["kind"] in ("scatter", "trajectory"):
                atlas_views.append(
                    {
                        "label": spec.get("title", identity),
                        "coordinates": spec["data"]["coordinates"],
                        "rows": spec["data"].get(
                            "rows", [{"id": i} for i in range(len(spec["data"]["coordinates"]))]
                        ),
                        "metadata": spec.get("metadata", {}),
                    }
                )
        except (LabError, ValueError, KeyError, ImportError, TypeError) as exc:
            summary["figure_errors"].append({"id": identity, "reason": type(exc).__name__})
    if atlas_views:
        try:
            summary["atlas"] = atlas(atlas_views, root / "atlas.html", title=plan["title"])
        except (LabError, ValueError, KeyError, ImportError, TypeError) as exc:
            summary["figure_errors"].append(
                {"id": "interactive_atlas", "reason": type(exc).__name__}
            )
            atlas_views = []
    write_json(root / "summary.json", summary)
    lines = [
        f"# {plan['title']}",
        "",
        "## Diagnostic coverage",
        "",
        "Completion records execution on the declared panel. Scientific qualification remains "
        "`NOT_QUALIFIED`; model-specific conclusions require their stated competence "
        "and control gates.",
        "",
        "| Diagnostic | Status | Reason |",
        "| --- | --- | --- |",
    ]
    display_coverage = coverage + summary["subchecks"]
    for row in display_coverage:
        lines.append(f"| {row['name']} | {row['status']} | {row['reason']} |")
    lines += [
        "",
        "## Reproducibility",
        "",
        f"Configuration SHA256: `{plan['identities']['configuration']}`.",
        "The bundle retains the frozen plan, input hashes, numerical results, arrays, "
        "coverage and operation ledger. Intervals retain their declared resampling unit and "
        "fixed-seed scope. Offline replay reuses captures and executes analysis only.",
        "",
        "Numerical values and source paths are in [metrics.csv](metrics.csv).",
    ]
    if atlas_views:
        lines += ["", "[Open the interactive atlas](atlas.html)."]
    for figure in summary["figures"]:
        lines += [
            "",
            f"## {figure['title']}",
            "",
            f"![{figure['title']}](figures/{figure['id']}.png)",
        ]
    if summary["figure_errors"]:
        lines += [
            "",
            "## Incomplete figures",
            "",
            "Some declared figures could not be generated; see summary.json. Missing figures "
            "are retained as failures, not silently counted as complete.",
        ]
    (root / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    rows_html = "".join(
        "<tr>"
        + "".join(f"<td>{html.escape(str(row[key]))}</td>" for key in ("name", "status", "reason"))
        + "</tr>"
        for row in display_coverage
    )
    pictures = "".join(
        f"<section><h2>{html.escape(f['title'])}</h2>"
        f'<img alt="{html.escape(f["title"], quote=True)}" '
        f'src="figures/{f["id"]}.svg"></section>'
        for f in summary["figures"]
    )
    incomplete = ""
    if summary["figure_errors"]:
        missing = ", ".join(html.escape(str(row["id"])) for row in summary["figure_errors"])
        incomplete = (
            "<section><h2>Incomplete figures</h2>"
            f"<p>These declared outputs could not be generated: {missing}. "
            "See summary.json for recorded errors. This report is incomplete.</p></section>"
        )
    page = f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(plan["title"])}</title>
<style>body{{font:16px system-ui;max-width:1100px;margin:auto;padding:24px;color:#16324c}}
table{{border-collapse:collapse;width:100%}}
td,th{{border-bottom:1px solid #ccc;padding:10px;text-align:left}}
img{{width:100%;height:auto}}section{{margin-top:36px}}.scroll{{overflow:auto}}</style>
<h1>{html.escape(plan["title"])}</h1>
<p>Observed diagnostic evidence. Scientific qualification: NOT_QUALIFIED.</p>
<p><a href="metrics.csv">Numerical results</a> ·
<a href="summary.json">Machine-readable coverage</a>
{' · <a href="atlas.html">Interactive atlas</a>' if atlas_views else ""}</p>
<div class="scroll"><table><thead><tr><th>Diagnostic</th><th>Status</th><th>Reason</th></tr></thead>
<tbody>{rows_html}</tbody></table></div>{incomplete}{pictures}</html>"""
    (root / "report.html").write_text(page, encoding="utf-8")
    try:
        report_pdf(summary, root / "report.pdf")
        summary["pdf"] = "report.pdf"
    except ImportError:
        summary["pdf"] = "UNSUPPORTED_MISSING_REPORTLAB"
    write_json(root / "summary.json", summary)
    return summary


def report_pdf(summary, destination):
    from matplotlib import font_manager
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        Image,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    root = Path(destination).parent
    for name, weight in (("LatentSans", "normal"), ("LatentSansBold", "bold")):
        font_path = font_manager.findfont(
            font_manager.FontProperties(family="DejaVu Sans", weight=weight)
        )
        pdfmetrics.registerFont(TTFont(name, font_path))
    styles = getSampleStyleSheet()
    for name in ("Normal", "Title", "Heading1", "Heading2"):
        styles[name].fontName = "LatentSans" if name == "Normal" else "LatentSansBold"
    styles["Normal"].fontSize = 9
    styles["Normal"].leading = 13
    styles["Title"].textColor = colors.HexColor("#153d69")
    doc = SimpleDocTemplate(
        str(destination), pagesize=A4, rightMargin=42, leftMargin=42, topMargin=42, bottomMargin=42
    )

    def paragraph(text):
        return Paragraph(html.escape(str(text)), styles["Normal"])

    story = [
        Paragraph(html.escape(summary["title"]), styles["Title"]),
        Spacer(1, 12),
        paragraph(
            "Diagnostic evidence on the declared observed panel. Scientific qualification: "
            "NOT_QUALIFIED. An executed test and a supported scientific claim "
            "are separate outcomes."
        ),
        Spacer(1, 12),
        Paragraph("Coverage", styles["Heading2"]),
    ]
    rows = [[paragraph("Diagnostic"), paragraph("Status"), paragraph("Reason")]]
    rows += [
        [paragraph(row[k]) for k in ("name", "status", "reason")]
        for row in summary["coverage"] + summary.get("subchecks", [])
    ]
    table = Table(rows, colWidths=[235, 90, 186], repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7eef5")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5df")),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story += [table, Spacer(1, 14), Paragraph("Identity and interpretation", styles["Heading2"])]
    for key, value in summary["identities"].items():
        story += [paragraph(f"{key}: {value}"), Spacer(1, 4)]
    story += [
        paragraph(
            "The portable bundle retains exact inputs, numerical arrays, result JSON, "
            "metrics.csv, figure data and the Workbench operation ledger. Confidence "
            "intervals use their declared observation units and fixed-seed scope. "
            "Offline reanalysis invokes no model forwards or training updates."
        )
    ]
    if summary["figure_errors"]:
        story += [
            Spacer(1, 12),
            Paragraph("Incomplete figures", styles["Heading2"]),
            paragraph(
                "These declared outputs could not be generated: "
                + ", ".join(str(row["id"]) for row in summary["figure_errors"])
                + ". See summary.json for recorded errors. This report is incomplete."
            ),
        ]
    for figure in summary["figures"]:
        story += [
            PageBreak(),
            Paragraph(html.escape(figure["title"]), styles["Heading1"]),
            Spacer(1, 12),
            Image(
                str(root / "figures" / f"{figure['id']}.png"), width=7.0 * inch, height=4.42 * inch
            ),
            Spacer(1, 12),
            paragraph(
                f"Source data: figures/{figure['id']}.data.json. "
                "Standalone PNG, SVG and PDF copies accompany this report."
            ),
        ]

    def footer(canvas, document):
        canvas.setFont("LatentSans", 8)
        canvas.setFillColor(colors.HexColor("#607080"))
        canvas.drawString(42, 25, "Veritas latent research diagnostics")
        canvas.drawRightString(A4[0] - 42, 25, str(document.page))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)


_ATLAS = (Path(__file__).parent / "static" / "atlas.html").read_text(encoding="utf-8")
