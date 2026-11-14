"""Metadata-only release readiness; deliberately has no tape/report outcome loader."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

from scripts.study_gate import gate as replication_gate
from scripts.successor_study import load_registration

ROOT = Path(__file__).resolve().parents[2]


def build(now=None):
    now = now or datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("aware UTC time required")
    now = now.astimezone(timezone.utc)
    plan = load_registration(ROOT / "configs/successor/registered_study.json")
    source = ROOT / "configs/successor/registered_study.json"
    release = datetime.fromisoformat(plan["outcome_release_date_utc"] + "T00:00:00+00:00")
    rows = [
        {
            "study_id": plan["study_id"],
            "registration": "source_verified",
            "release_utc": release.isoformat(),
            "release_shanghai": release.astimezone(timezone(timedelta(hours=8))).isoformat(),
            "outcome_time_gate_open": now >= release,
            "planned_slots": len(plan["planned_slots"]),
            "outcomes_status": "requires_authenticated_original_report"
            if now >= release
            else "EMPIRICAL_UNRELEASED",
            "configuration_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        }
    ]
    for name in ("study_v2_okx.json", "study_v2_bybit.json"):
        path = ROOT / "configs" / name
        config = json.loads(path.read_text())
        end = datetime.fromisoformat(config["end_date_utc"] + "T00:00:00+00:00")
        release = end + timedelta(days=1)
        rows.append(
            {
                "study_id": config["study_id"],
                "registration": "configuration_exists_activation_not_authenticated",
                "release_utc": release.isoformat(),
                "release_shanghai": release.astimezone(timezone(timedelta(hours=8))).isoformat(),
                "outcome_time_gate_open": replication_gate(
                    config, now, event="workflow_dispatch", report=True
                )["run"]
                == "true",
                "outcomes_status": "requires_authenticated_original_report"
                if now >= release
                else "EMPIRICAL_UNRELEASED",
                "configuration_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return {
        "schema_version": 1,
        "as_of_utc": now.isoformat(),
        "studies": rows,
        "outcome_files_read": 0,
        "market_tapes_read": 0,
        "source_binding_verified": True,
        "signing_status": "SHA256 integrity binding; no cryptographic signer configured",
        "decision": "Remain in research; a date gate opening alone never establishes eligible evidence or alpha.",
    }
