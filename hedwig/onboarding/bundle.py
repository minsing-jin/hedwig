"""Algorithm export/import bundle (Phase 7 S6).

The export contract declared in sovereignty.yaml says these files are all
the user needs to port their algorithm to another Hedwig install. This
module zips them into a single download and reverses the operation
(with a sovereignty check + dry-run preview before any writes).

Bundle layout:
    hedwig-algo-<short>.zip
    ├── manifest.json           # schema, exported_at, signature
    ├── criteria.yaml
    ├── algorithm.yaml
    ├── interpretation_style.json (active style only)
    └── README.md               # auto-generated profile
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import zipfile
from datetime import datetime, timezone

import yaml

from hedwig.config import ALGORITHM_PATH, CRITERIA_PATH, load_algorithm_config, load_criteria

logger = logging.getLogger(__name__)


SCHEMA = "hedwig-algo-bundle/1"


def _read_or_default(path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return default


def _active_style_json() -> str:
    try:
        from hedwig.storage import get_active_interpretation_style
        active = get_active_interpretation_style() or {}
    except Exception:
        active = {}
    return json.dumps(active, ensure_ascii=False, indent=2)


def _readme(criteria: dict, algorithm: dict, style: dict) -> str:
    care = (criteria.get("signal_preferences", {}).get("care_about") or [])[:8]
    enabled = [
        n for n, s in (algorithm.get("ranking", {}).get("components") or {}).items()
        if s.get("enabled")
    ]
    return (
        f"# Hedwig Algorithm Profile\n\n"
        f"Exported: {datetime.now(tz=timezone.utc).isoformat()}\n\n"
        f"## What I care about\n"
        + ("\n".join(f"- {c}" for c in care) or "_(empty)_") + "\n\n"
        f"## Active ranking components\n"
        + ("\n".join(f"- `{n}`" for n in enabled) or "_(none enabled)_") + "\n\n"
        f"## Interpretation style\n"
        f"- tone: {style.get('tone')}\n"
        f"- depth: {style.get('depth')}\n"
        f"- jargon: {style.get('jargon_level')}\n\n"
        f"---\n\nImport with `POST /algorithm/import` (multipart). "
        f"Sovereignty boundary is enforced — any path not in user_editable is dropped."
    )


def export_bundle() -> tuple[bytes, str]:
    """Build a zip bundle in-memory. Returns (bytes, suggested_filename)."""
    criteria = load_criteria() or {}
    algorithm = load_algorithm_config() or {}
    style_json = _active_style_json()
    try:
        style = json.loads(style_json) or {}
    except Exception:
        style = {}

    manifest = {
        "schema": SCHEMA,
        "exported_at": datetime.now(tz=timezone.utc).isoformat(),
        "criteria_summary": list(
            (criteria.get("signal_preferences", {}).get("care_about") or [])[:5]
        ),
        "algorithm_version": algorithm.get("version"),
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        crit_yaml = yaml.safe_dump(criteria, allow_unicode=True, sort_keys=False)
        algo_yaml = yaml.safe_dump(algorithm, allow_unicode=True, sort_keys=False)
        # manifest signature is a sha256 over the included files
        signature = hashlib.sha256(
            (crit_yaml + algo_yaml + style_json).encode("utf-8")
        ).hexdigest()
        manifest["signature"] = signature

        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr("criteria.yaml", crit_yaml)
        zf.writestr("algorithm.yaml", algo_yaml)
        zf.writestr("interpretation_style.json", style_json)
        zf.writestr("README.md", _readme(criteria, algorithm, style))

    short = (manifest["signature"] or "")[:10] or "noid"
    return buf.getvalue(), f"hedwig-algo-{short}.zip"


def parse_bundle(blob: bytes) -> dict:
    """Read a zip bundle into structured dict (no writes)."""
    out: dict = {"ok": False, "errors": []}
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            names = set(zf.namelist())
            required = {"manifest.json", "criteria.yaml", "algorithm.yaml"}
            missing = required - names
            if missing:
                out["errors"].append(f"missing files: {sorted(missing)}")
                return out
            try:
                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            except Exception as e:
                out["errors"].append(f"manifest parse: {e}")
                return out
            if str(manifest.get("schema") or "") != SCHEMA:
                out["errors"].append(
                    f"unsupported schema: {manifest.get('schema')!r} (expected {SCHEMA})"
                )
                return out
            try:
                criteria = yaml.safe_load(zf.read("criteria.yaml").decode("utf-8")) or {}
                algorithm = yaml.safe_load(zf.read("algorithm.yaml").decode("utf-8")) or {}
            except Exception as e:
                out["errors"].append(f"yaml parse: {e}")
                return out
            style = {}
            if "interpretation_style.json" in names:
                try:
                    style = json.loads(
                        zf.read("interpretation_style.json").decode("utf-8")
                    ) or {}
                except Exception as e:
                    out["errors"].append(f"style parse: {e}")
            out["ok"] = True
            out["manifest"] = manifest
            out["criteria"] = criteria
            out["algorithm"] = algorithm
            out["style"] = style
    except zipfile.BadZipFile:
        out["errors"].append("not a zip file")
    return out


def dry_run_import(blob: bytes) -> dict:
    """Parse + sovereignty filter + diff against current state. No writes."""
    parsed = parse_bundle(blob)
    if not parsed.get("ok"):
        return parsed

    from hedwig.sovereignty import filter_allowed_changes

    current_crit = load_criteria() or {}
    incoming_crit = parsed.get("criteria") or {}

    # Construct diff as a list of {op,path,value} so sovereignty filter can
    # decide which incoming paths the user is allowed to overwrite.
    crit_changes: list[dict] = []
    for top, val in incoming_crit.items():
        crit_changes.append({"op": "set", "path": top, "value": val})
    crit_allowed, crit_rejected = filter_allowed_changes(
        "criteria", crit_changes, actor="user",
    )

    incoming_algo = parsed.get("algorithm") or {}
    algo_changes: list[dict] = []
    for top, val in incoming_algo.items():
        algo_changes.append({"op": "set", "path": top, "value": val})
    algo_allowed, algo_rejected = filter_allowed_changes(
        "algorithm", algo_changes, actor="user",
    )

    return {
        "ok": True,
        "manifest": parsed["manifest"],
        "criteria_diff_count": len(crit_changes),
        "criteria_allowed": crit_allowed,
        "criteria_rejected": crit_rejected,
        "algorithm_diff_count": len(algo_changes),
        "algorithm_allowed": algo_allowed,
        "algorithm_rejected": algo_rejected,
        "preview": {
            "before": {"criteria": current_crit, "algorithm": load_algorithm_config()},
            "after_subset": {
                "criteria_top_keys": list(incoming_crit.keys()),
                "algorithm_top_keys": list(incoming_algo.keys()),
            },
        },
    }


def confirm_import(blob: bytes) -> dict:
    """Apply the sovereignty-filtered subset and bump versions."""
    dry = dry_run_import(blob)
    if not dry.get("ok"):
        return dry

    parsed = parse_bundle(blob)
    if not parsed.get("ok"):
        return parsed

    from hedwig.onboarding.nl_algo_editor import confirm_edit as algo_confirm
    from hedwig.onboarding.nl_editor import confirm_edit as crit_confirm

    crit_result = crit_confirm(dry["criteria_allowed"], intent="bundle_import") \
        if dry["criteria_allowed"] else {"ok": True, "skipped": True}
    algo_result = algo_confirm(dry["algorithm_allowed"], intent="bundle_import") \
        if dry["algorithm_allowed"] else {"ok": True, "skipped": True}

    return {
        "ok": True,
        "criteria": crit_result,
        "algorithm": algo_result,
        "manifest": dry["manifest"],
        "rejected": {
            "criteria": dry["criteria_rejected"],
            "algorithm": dry["algorithm_rejected"],
        },
    }
