"""Local + S3 model artifact registry for the Hybrid Audit Engine (HAE-4)."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import joblib

logger = logging.getLogger(__name__)

DEFAULT_ARTIFACT_DIR = Path(
    os.environ.get("HAE_ARTIFACT_DIR", "/tmp/cae_hae_models")
)


def artifact_dir(org_id: str | None = None) -> Path:
    path = DEFAULT_ARTIFACT_DIR / (str(org_id) if org_id else "_global")
    path.mkdir(parents=True, exist_ok=True)
    return path


def model_path(org_id: str | None, name: str, version: str = "latest") -> Path:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
    return artifact_dir(org_id) / f"{safe}__{version}.joblib"


def meta_path(org_id: str | None, name: str, version: str = "latest") -> Path:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
    return artifact_dir(org_id) / f"{safe}__{version}.meta.json"


def save_artifact(
    org_id: str | None,
    name: str,
    payload: Any,
    metadata: Optional[dict] = None,
    version: str = "latest",
    upload_s3: bool = True,
) -> dict:
    """Persist a joblib artifact locally and optionally mirror to S3."""
    path = model_path(org_id, name, version)
    joblib.dump(payload, path)
    meta = {
        "name": name,
        "version": version,
        "org_id": str(org_id) if org_id else None,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "local_path": str(path),
        **(metadata or {}),
    }
    meta_file = meta_path(org_id, name, version)
    meta_file.write_text(json.dumps(meta, default=str), encoding="utf-8")

    if version != "latest":
        # Also refresh the "latest" pointer.
        save_artifact(org_id, name, payload, metadata, version="latest", upload_s3=False)

    if upload_s3:
        try:
            from app.services.s3_service import upload_bytes
            from app.config import settings

            if getattr(settings, "S3_BUCKET", None):
                key = f"hae-models/{org_id or 'global'}/{name}/{version}.joblib"
                upload_bytes(key, path.read_bytes(), "application/octet-stream")
                meta["s3_key"] = key
                meta_file.write_text(json.dumps(meta, default=str), encoding="utf-8")
        except Exception as exc:  # pragma: no cover - S3 optional in tests
            logger.debug("S3 model upload skipped: %s", exc)

    return meta


def load_artifact(org_id: str | None, name: str, version: str = "latest") -> Any | None:
    path = model_path(org_id, name, version)
    if not path.exists() and org_id:
        path = model_path(None, name, version)
    if not path.exists():
        return None
    try:
        return joblib.load(path)
    except Exception as exc:
        logger.warning("Failed to load HAE artifact %s: %s", path, exc)
        return None


def load_metadata(org_id: str | None, name: str, version: str = "latest") -> dict | None:
    path = meta_path(org_id, name, version)
    if not path.exists() and org_id:
        path = meta_path(None, name, version)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_artifacts(org_id: str | None = None) -> list[dict]:
    base = artifact_dir(org_id)
    results = []
    for meta_file in sorted(base.glob("*.meta.json")):
        try:
            results.append(json.loads(meta_file.read_text(encoding="utf-8")))
        except Exception:
            continue
    return results
