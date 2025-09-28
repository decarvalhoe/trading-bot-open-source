#!/usr/bin/env python3
"""Aggregate KPI metrics into Markdown and JSON dashboards."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


STATUS_ICONS = {
    "on_track": "🟢",
    "watch": "🟡",
    "at_risk": "🔴",
}

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="Chemin vers le fichier TOML de configuration des KPI.")
    parser.add_argument("--coverage-xml", type=Path, help="Chemin vers le rapport coverage.xml généré par coverage.py.")
    parser.add_argument("--test-outcome", choices=["success", "failure", "cancelled", "skipped"], default="success",
                        help="Statut du job de tests unitaires. Permet d'ajuster la valeur de couverture.")
    parser.add_argument("--e2e-log", type=Path, help="Journal texte produit par le scénario E2E.")
    parser.add_argument("--e2e-outcome", choices=["success", "failure", "cancelled", "skipped"], default="success",
                        help="Statut du job E2E pour calculer le taux de réussite.")
    parser.add_argument("--output-md", type=Path, required=True, help="Fichier Markdown à générer pour le tableau de bord.")
    parser.add_argument("--output-json", type=Path, required=True, help="Fichier JSON exportant les métriques.")
    return parser.parse_args()


def load_config(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Fichier de configuration introuvable: {path}")
    with path.open("rb") as fh:
        return tomllib.load(fh)


def find_kpi(kpis: list[dict], kpi_id: str) -> dict | None:
    for item in kpis:
        if item.get("id") == kpi_id:
            return item
    return None


def format_percentage(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f} %"


def update_coverage(kpi: dict, coverage_xml: Path | None, outcome: str, generated_at: dt.datetime) -> None:
    if kpi is None:
        return
    if outcome == "failure":
        kpi["current"] = "Tests en échec"
        kpi["status"] = "at_risk"
        existing = (kpi.get("notes") or "").strip()
        message = "CI: tests unitaires en échec."
        if message not in existing:
            kpi["notes"] = (existing + (" " if existing else "") + message).strip()
        else:
            kpi["notes"] = existing
        kpi["last_update"] = generated_at.isoformat()
        return
    if outcome in {"skipped", "cancelled"}:
        kpi["current"] = "Non exécuté"
        kpi["status"] = "watch"
        existing = (kpi.get("notes") or "").strip()
        message = "CI: tests unitaires non exécutés."
        if message not in existing:
            kpi["notes"] = (existing + (" " if existing else "") + message).strip()
        else:
            kpi["notes"] = existing
        kpi["last_update"] = generated_at.isoformat()
        return
    if not coverage_xml or not coverage_xml.exists():
        existing = (kpi.get("notes") or "").strip()
        extra = "Rapport coverage.xml absent."
        if extra not in existing:
            kpi["notes"] = (existing + (" " if existing else "") + extra).strip()
        else:
            kpi["notes"] = existing
        kpi.setdefault("current", "N/A")
        kpi["last_update"] = generated_at.isoformat()
        return
    tree = ET.parse(coverage_xml)
    root = tree.getroot()
    line_rate = root.attrib.get("line-rate")
    percent = None
    if line_rate is not None:
        try:
            percent = float(line_rate) * 100.0
        except ValueError:
            percent = None
    if percent is None:
        lines_valid = sum(int(pkg.attrib.get("lines-valid", 0)) for pkg in root.findall(".//package"))
        lines_covered = sum(int(pkg.attrib.get("lines-covered", 0)) for pkg in root.findall(".//package"))
        percent = (lines_covered / lines_valid * 100.0) if lines_valid else None
    kpi["current"] = format_percentage(percent)
    kpi["last_update"] = generated_at.isoformat()
    # Ajuster le statut en fonction de la cible si possible
    target_str = (kpi.get("target") or "").replace("%", "").strip()
    try:
        target_value = float(target_str)
    except ValueError:
        target_value = None
    if percent is not None and target_value is not None:
        kpi["status"] = "on_track" if percent >= target_value else "watch"


def update_e2e(kpi: dict, outcome: str, generated_at: dt.datetime, log_path: Path | None) -> None:
    if kpi is None:
        return
    if outcome == "failure":
        kpi["current"] = "0.00 %"
        kpi["status"] = "at_risk"
        failure_note = "Dernier run E2E en échec."
        existing = kpi.get("notes") or ""
        if failure_note not in existing:
            kpi["notes"] = (existing + (" " if existing else "") + failure_note).strip()
        kpi["last_update"] = generated_at.isoformat()
        return
    if outcome in {"skipped", "cancelled"}:
        kpi["current"] = "Non exécuté"
        kpi["status"] = "watch"
        note = "Dernier run E2E non exécuté (skipped/cancelled)."
        existing = kpi.get("notes") or ""
        if note not in existing:
            kpi["notes"] = (existing + (" " if existing else "") + note).strip()
        kpi["last_update"] = generated_at.isoformat()
        return
    kpi["current"] = "100.00 %"
    kpi["status"] = "on_track"
    kpi["last_update"] = generated_at.isoformat()
    if log_path and log_path.exists():
        kpi.setdefault("attachments", [])
        rel_path = str(log_path)
        if rel_path not in kpi["attachments"]:
            kpi["attachments"].append(rel_path)


def ensure_last_update(kpi: dict, generated_at: dt.datetime) -> None:
    if not kpi.get("last_update"):
        kpi["last_update"] = generated_at.isoformat()


def render_markdown(config: dict, kpis: list[dict], generated_at: dt.datetime) -> str:
    lines: list[str] = []
    title = config.get("title", "Tableau de bord KPI")
    description = config.get("description")
    owners_note = config.get("owners_note")
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"> Dernière génération : {generated_at.isoformat()}Z")
    if description:
        lines.append("")
        lines.append(description)
    if owners_note:
        lines.append("")
        lines.append(f"_Note : {owners_note}_")
    lines.append("")
    lines.append("## Synthèse rapide")
    lines.append("")
    for kpi in kpis:
        status = STATUS_ICONS.get(kpi.get("status", ""), "")
        current = kpi.get("current", "N/A")
        name = kpi.get("name", kpi.get("id", ""))
        lines.append(f"- {status} **{name}** — {current}")
    lines.append("")
    lines.append("## Détail par indicateur")
    lines.append("")
    headers = [
        "KPI",
        "Description",
        "Responsable",
        "Cible",
        "Valeur actuelle",
        "Source",
        "Mode",
        "Cadence",
        "Dernière mise à jour",
        "Notes",
    ]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for kpi in kpis:
        status = STATUS_ICONS.get(kpi.get("status", ""), "")
        row = [
            f"{status} {kpi.get('name', kpi.get('id', ''))}",
            kpi.get("description", ""),
            kpi.get("owner", ""),
            kpi.get("target", ""),
            kpi.get("current", "N/A"),
            kpi.get("data_source", ""),
            kpi.get("update_mode", ""),
            kpi.get("review_cadence", ""),
            kpi.get("last_update", ""),
            kpi.get("notes", ""),
        ]
        lines.append("| " + " | ".join(row) + " |")
    if any(kpi.get("attachments") for kpi in kpis):
        lines.append("")
        lines.append("## Pièces jointes")
        for kpi in kpis:
            attachments = kpi.get("attachments") or []
            if attachments:
                lines.append(f"- **{kpi.get('name')}** :")
                for attachment in attachments:
                    rel = attachment
                    lines.append(f"  - `{rel}`")
    return "\n".join(lines) + "\n"


def serialize_json(kpis: list[dict], generated_at: dt.datetime) -> str:
    payload = {
        "generated_at": generated_at.isoformat() + "Z",
        "kpis": kpis,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    args = parse_args()
    generated_at = dt.datetime.now(dt.timezone.utc)
    config = load_config(args.config)
    kpis: list[dict] = [dict(kpi) for kpi in config.get("kpis", [])]

    coverage_kpi = find_kpi(kpis, "coverage")
    update_coverage(coverage_kpi, args.coverage_xml, args.test_outcome, generated_at)

    e2e_kpi = find_kpi(kpis, "e2e_pass_rate")
    update_e2e(e2e_kpi, args.e2e_outcome, generated_at, args.e2e_log)

    for kpi in kpis:
        ensure_last_update(kpi, generated_at)

    markdown = render_markdown(config, kpis, generated_at)
    json_payload = serialize_json(kpis, generated_at)

    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(markdown, encoding="utf-8")
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json_payload, encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
