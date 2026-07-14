"""
File & media storage for CA Copilot preview backend.

Design
------
- Adapter pattern so S3/R2/GCS drop in cleanly later. Today's default
  adapter is MongoDB GridFS.
- Presigned-URL flow:
    1. Client asks for an upload URL: `POST /documents/upload-url`
       → we mint a short-lived HMAC-signed token and return an in-app
         URL: `PUT /api/storage/upload/{token}`.
    2. Client PUTs bytes directly to that URL (no proxying through the
       app's JSON endpoints — supports big files).
    3. Client tells us the upload is done: `POST /documents/{id}/process`
       which flips status to "processed" and kicks off a mock task.
- Downloads follow the same pattern: signed `/api/storage/download/{token}`.

Signed tokens
-------------
- `token = base64url({document_id, op, expires_at}) + '.' + hmac_sig`
- Op is either `upload` or `download`.
- Signed with `STORAGE_SIGNING_SECRET` from env; expiry defaults to 5 min.
- Uploads are one-shot (dedup by document_id in status).

MongoDB collections
-------------------
- `documents` — metadata (id, org_id, client_id, doc_type, filename,
  mime_type, size, status, storage_key, checksum_sha256, tags, etc.)
- `fs.files` / `fs.chunks` — GridFS bucket that holds the actual bytes.

Presign response
----------------
{
  "document_id": "doc-xxx",
  "upload_url":  "http://<backend>/api/storage/upload/<token>",
  "download_url": "http://<backend>/api/storage/download/<token>",  (unused for upload flow)
  "content_type": "application/pdf",
  "expires_at":   "2026-07-14T16:45:00Z",
  "storage_adapter": "gridfs"
}
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket

load_dotenv()
log = logging.getLogger("ca_platform.storage")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MONGO_URL: str = os.environ.get("MONGO_URL", "mongodb://localhost:27017").strip()
DB_NAME: str = os.environ.get("DB_NAME", "ca_platform").strip()
STORAGE_ADAPTER: str = os.environ.get("STORAGE_ADAPTER", "gridfs").strip().lower()
STORAGE_URL_TTL_SECONDS: int = int(os.environ.get("STORAGE_URL_TTL_SECONDS", "300"))
STORAGE_MAX_UPLOAD_BYTES: int = int(os.environ.get("STORAGE_MAX_UPLOAD_BYTES", str(100 * 1024 * 1024)))
STORAGE_SIGNING_SECRET: str = os.environ.get(
    "STORAGE_SIGNING_SECRET", "change-me-storage-signing-secret"
).strip()

# Allowed content types (whitelist for demo; expand as needed)
ALLOWED_MIME_PREFIXES = (
    "application/pdf",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument",
    "application/msword",
    "application/zip",
    "text/",
    "image/",
)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    pad = 4 - (len(data) % 4)
    return base64.urlsafe_b64decode(data + ("=" * pad if pad != 4 else ""))


def _sign(payload: bytes) -> str:
    return _b64url_encode(
        hmac.new(STORAGE_SIGNING_SECRET.encode("utf-8"), payload, hashlib.sha256).digest()
    )


def make_signed_token(*, document_id: str, op: str, ttl_seconds: Optional[int] = None) -> Dict[str, str]:
    """Mint a signed short-lived token for upload/download of a document."""
    if op not in ("upload", "download"):
        raise ValueError("op must be upload|download")
    ttl = ttl_seconds if ttl_seconds is not None else STORAGE_URL_TTL_SECONDS
    body = {
        "document_id": document_id,
        "op": op,
        "expires_at": int(time.time()) + ttl,
        "nonce": uuid.uuid4().hex[:8],
    }
    body_b = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body_b64 = _b64url_encode(body_b)
    sig = _sign(body_b64.encode("ascii"))
    token = f"{body_b64}.{sig}"
    return {
        "token": token,
        "expires_at": datetime.fromtimestamp(body["expires_at"], tz=timezone.utc).isoformat(),
    }


def verify_signed_token(token: str, expected_op: str) -> str:
    """Return the document_id if valid, else raise ValueError."""
    try:
        body_b64, sig = token.rsplit(".", 1)
    except ValueError:
        raise ValueError("Malformed token")
    expected_sig = _sign(body_b64.encode("ascii"))
    if not hmac.compare_digest(sig, expected_sig):
        raise ValueError("Invalid signature")
    try:
        body = json.loads(_b64url_decode(body_b64).decode("utf-8"))
    except Exception:
        raise ValueError("Malformed token body")
    if body.get("op") != expected_op:
        raise ValueError(f"Wrong op — token is for {body.get('op')!r}, expected {expected_op!r}")
    if int(body.get("expires_at", 0)) < int(time.time()):
        raise ValueError("Token expired")
    return str(body.get("document_id") or "")


# ---------------------------------------------------------------------------
# Mongo + GridFS bootstrap
# ---------------------------------------------------------------------------

_mongo: Optional[AsyncIOMotorClient] = None
_gridfs: Optional[AsyncIOMotorGridFSBucket] = None


def _db():
    global _mongo
    if _mongo is None:
        _mongo = AsyncIOMotorClient(MONGO_URL, uuidRepresentation="standard")
    return _mongo[DB_NAME]


def _bucket() -> AsyncIOMotorGridFSBucket:
    global _gridfs
    if _gridfs is None:
        _gridfs = AsyncIOMotorGridFSBucket(_db(), bucket_name="fs")
    return _gridfs


async def ensure_indexes() -> None:
    db = _db()
    try:
        await db.documents.create_index("id", unique=True)
        await db.documents.create_index([("org_id", 1), ("created_at", -1)])
        await db.documents.create_index([("client_id", 1), ("doc_type", 1)])
        await db.documents.create_index("status")
    except Exception:
        log.exception("ensure_indexes failed")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Adapter interface
# ---------------------------------------------------------------------------


class StorageAdapter:
    """Minimal interface. GridFS is the default implementation; S3/R2 land
    here later without touching the router code."""

    name: str = "abstract"

    async def put_bytes(self, storage_key: str, data: bytes, content_type: str) -> str:
        raise NotImplementedError

    async def get_bytes(self, storage_key: str) -> bytes:
        raise NotImplementedError

    async def stream(self, storage_key: str) -> AsyncIterator[bytes]:
        raise NotImplementedError

    async def delete(self, storage_key: str) -> None:
        raise NotImplementedError


class GridFsAdapter(StorageAdapter):
    name = "gridfs"

    async def put_bytes(self, storage_key: str, data: bytes, content_type: str) -> str:
        # GridFS stores files by an ObjectId internally. We reference them
        # from `documents.storage_key` by filename (storage_key), and we
        # dedupe by deleting existing files with the same filename first.
        bucket = _bucket()
        async for f in bucket.find({"filename": storage_key}):
            await bucket.delete(f["_id"])
        oid = await bucket.upload_from_stream(
            storage_key,
            data,
            metadata={"content_type": content_type, "uploaded_at": _now().isoformat()},
        )
        return str(oid)

    async def get_bytes(self, storage_key: str) -> bytes:
        bucket = _bucket()
        stream = await bucket.open_download_stream_by_name(storage_key)
        return await stream.read()

    async def stream(self, storage_key: str) -> AsyncIterator[bytes]:
        bucket = _bucket()
        s = await bucket.open_download_stream_by_name(storage_key)
        try:
            while True:
                chunk = await s.readchunk()
                if not chunk:
                    break
                yield chunk
        finally:
            await s.close()

    async def delete(self, storage_key: str) -> None:
        bucket = _bucket()
        async for f in bucket.find({"filename": storage_key}):
            await bucket.delete(f["_id"])


_ADAPTER: Optional[StorageAdapter] = None


def get_adapter() -> StorageAdapter:
    global _ADAPTER
    if _ADAPTER is None:
        if STORAGE_ADAPTER == "gridfs":
            _ADAPTER = GridFsAdapter()
        else:
            log.warning(
                "STORAGE_ADAPTER=%s not implemented in preview backend — using GridFS.",
                STORAGE_ADAPTER,
            )
            _ADAPTER = GridFsAdapter()
    return _ADAPTER


# ---------------------------------------------------------------------------
# Document metadata CRUD
# ---------------------------------------------------------------------------


DOC_STATUS_PENDING = "pending_upload"
DOC_STATUS_UPLOADED = "uploaded"
DOC_STATUS_PROCESSING = "processing"
DOC_STATUS_PROCESSED = "processed"
DOC_STATUS_FAILED = "failed"


def _sanitise_filename(name: str) -> str:
    keep = "".join(c if c.isalnum() or c in ".-_" else "_" for c in (name or "file"))
    return keep[:200] or "file"


def _storage_key(org_id: str, client_id: str, doc_type: str, document_id: str, filename: str) -> str:
    return f"{org_id}/{client_id}/{doc_type}/{document_id}/{_sanitise_filename(filename)}"


async def create_document_placeholder(
    *,
    org_id: str,
    client_id: str,
    doc_type: str,
    filename: str,
    file_size_bytes: int,
    mime_type: str,
    user_id: str,
    tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if file_size_bytes and file_size_bytes > STORAGE_MAX_UPLOAD_BYTES:
        raise ValueError(f"File too large ({file_size_bytes} bytes; max {STORAGE_MAX_UPLOAD_BYTES}).")
    if mime_type and not any(mime_type.startswith(p) for p in ALLOWED_MIME_PREFIXES):
        raise ValueError(f"Content-Type '{mime_type}' is not allowed for demo.")

    document_id = f"doc-{uuid.uuid4().hex[:16]}"
    doc = {
        "id": document_id,
        "org_id": org_id,
        "client_id": client_id,
        "doc_type": doc_type,
        "filename": _sanitise_filename(filename),
        "original_filename": filename,
        "mime_type": mime_type or "application/octet-stream",
        "size": int(file_size_bytes or 0),
        "status": DOC_STATUS_PENDING,
        "storage_adapter": get_adapter().name,
        "storage_key": _storage_key(org_id, client_id, doc_type, document_id, filename),
        "sha256": None,
        "created_by": user_id,
        "created_at": _now(),
        "updated_at": _now(),
        "processed_at": None,
        "tags": tags or [],
    }
    await _db().documents.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def get_document(document_id: str) -> Optional[Dict[str, Any]]:
    return await _db().documents.find_one({"id": document_id}, {"_id": 0})


async def list_documents(
    *,
    org_id: str,
    client_id: Optional[str] = None,
    doc_type: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {"org_id": org_id}
    if client_id:
        q["client_id"] = client_id
    if doc_type:
        q["doc_type"] = doc_type
    cursor = _db().documents.find(q, {"_id": 0}).sort("created_at", -1).limit(limit)
    return [d async for d in cursor]


async def mark_uploaded(
    document_id: str,
    *,
    actual_size: int,
    sha256: str,
    content_type: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    update = {
        "status": DOC_STATUS_UPLOADED,
        "size": actual_size,
        "sha256": sha256,
        "updated_at": _now(),
    }
    if content_type:
        update["mime_type"] = content_type
    result = await _db().documents.find_one_and_update(
        {"id": document_id},
        {"$set": update},
        return_document=True,
        projection={"_id": 0},
    )
    return result


async def mark_processed(document_id: str, task_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    return await _db().documents.find_one_and_update(
        {"id": document_id},
        {"$set": {
            "status": DOC_STATUS_PROCESSED,
            "processed_at": _now(),
            "updated_at": _now(),
            "last_task_id": task_id,
        }},
        return_document=True,
        projection={"_id": 0},
    )


async def delete_document(document_id: str) -> bool:
    doc = await get_document(document_id)
    if not doc:
        return False
    try:
        await get_adapter().delete(doc["storage_key"])
    except Exception:
        log.warning("Failed to remove object %s", doc["storage_key"], exc_info=True)
    r = await _db().documents.delete_one({"id": document_id})
    return r.deleted_count > 0


# ---------------------------------------------------------------------------
# Upload / download helpers used by the router
# ---------------------------------------------------------------------------


def build_upload_url(base_url: str, token: str) -> str:
    base_url = base_url.rstrip("/")
    if base_url.endswith("/api"):
        return f"{base_url}/storage/upload/{token}"
    return f"{base_url}/api/storage/upload/{token}"


def build_download_url(base_url: str, token: str) -> str:
    base_url = base_url.rstrip("/")
    if base_url.endswith("/api"):
        return f"{base_url}/storage/download/{token}"
    return f"{base_url}/api/storage/download/{token}"


async def handle_upload(token: str, data: bytes, content_type: Optional[str]) -> Dict[str, Any]:
    document_id = verify_signed_token(token, expected_op="upload")
    doc = await get_document(document_id)
    if not doc:
        raise ValueError("Document not found")
    if doc["status"] in {DOC_STATUS_UPLOADED, DOC_STATUS_PROCESSED, DOC_STATUS_PROCESSING}:
        raise ValueError("Document already uploaded — mint a new URL to overwrite")
    if len(data) > STORAGE_MAX_UPLOAD_BYTES:
        raise ValueError("File exceeds size limit")

    ct = content_type or doc.get("mime_type") or "application/octet-stream"
    await get_adapter().put_bytes(doc["storage_key"], data, ct)
    sha256 = hashlib.sha256(data).hexdigest()
    updated = await mark_uploaded(document_id, actual_size=len(data), sha256=sha256, content_type=ct)
    return {"ok": True, "document": updated}


async def stream_download(token: str) -> AsyncIterator[bytes]:
    document_id = verify_signed_token(token, expected_op="download")
    doc = await get_document(document_id)
    if not doc:
        raise ValueError("Document not found")
    if doc["status"] not in {DOC_STATUS_UPLOADED, DOC_STATUS_PROCESSED, DOC_STATUS_PROCESSING}:
        raise ValueError("Document not yet available")
    async for chunk in get_adapter().stream(doc["storage_key"]):
        yield chunk


async def download_document_meta(token: str) -> Dict[str, Any]:
    document_id = verify_signed_token(token, expected_op="download")
    doc = await get_document(document_id)
    if not doc:
        raise ValueError("Document not found")
    return doc


__all__ = [
    "STORAGE_ADAPTER",
    "STORAGE_URL_TTL_SECONDS",
    "STORAGE_MAX_UPLOAD_BYTES",
    "ALLOWED_MIME_PREFIXES",
    "DOC_STATUS_PENDING",
    "DOC_STATUS_UPLOADED",
    "DOC_STATUS_PROCESSING",
    "DOC_STATUS_PROCESSED",
    "DOC_STATUS_FAILED",
    "ensure_indexes",
    "get_adapter",
    "create_document_placeholder",
    "get_document",
    "list_documents",
    "mark_uploaded",
    "mark_processed",
    "delete_document",
    "make_signed_token",
    "verify_signed_token",
    "build_upload_url",
    "build_download_url",
    "handle_upload",
    "stream_download",
    "download_document_meta",
]
