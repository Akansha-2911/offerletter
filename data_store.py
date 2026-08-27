import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    from pymongo import MongoClient, DESCENDING
except Exception:  # pragma: no cover - optional until requirements are installed
    MongoClient = None
    DESCENDING = -1

BASE_DIR = Path(__file__).resolve().parent
LOCAL_LOG_FILE = BASE_DIR / "data" / "document_logs.json"
_LOCK = threading.Lock()
_MONGO_COLLECTION = None
_MONGO_ATTEMPTED = False

DOCUMENT_TYPES = {
    "employment_offer": "Employment Offers",
    "bda_offer": "BDA Offer Letters",
    "live_project_offer": "Live Project Offers",
    "certificates": "Certificates",
    "software_developer": "Software Developer Documents",
}


def _now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _mongo_collection():
    global _MONGO_COLLECTION, _MONGO_ATTEMPTED
    if _MONGO_ATTEMPTED:
        return _MONGO_COLLECTION
    _MONGO_ATTEMPTED = True
    uri = (os.environ.get("MONGO_URI") or os.environ.get("MONGODB_URI") or "").strip()
    if not uri or MongoClient is None:
        return None
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=2500, connectTimeoutMS=2500)
        client.admin.command("ping")
        db_name = (os.environ.get("MONGO_DB_NAME") or "aparaitech_document_portal").strip()
        collection = client[db_name]["document_logs"]
        collection.create_index([("created_at", DESCENDING)])
        collection.create_index([("document_type", 1), ("created_at", DESCENDING)])
        collection.create_index("email")
        _MONGO_COLLECTION = collection
        return _MONGO_COLLECTION
    except Exception:
        return None


def storage_backend():
    return "MongoDB" if _mongo_collection() is not None else "Local JSON fallback"


def _read_local():
    if not LOCAL_LOG_FILE.exists():
        return []
    try:
        return json.loads(LOCAL_LOG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _write_local(records):
    LOCAL_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = LOCAL_LOG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(LOCAL_LOG_FILE)


def save_document_log(document_type, data, *, admin_user="ADMIN", email_status="skipped",
                      email_error="", filename="", extra=None):
    """Persist an audit record without ever blocking the user's document download."""
    safe_data = {}
    for key, value in dict(data or {}).items():
        if value is None:
            value = ""
        if isinstance(value, (str, int, float, bool)):
            safe_data[str(key)] = value
        else:
            safe_data[str(key)] = str(value)

    name = (
        safe_data.get("employee_name")
        or safe_data.get("candidate_name")
        or safe_data.get("name")
        or ""
    )
    record = {
        "record_id": uuid.uuid4().hex,
        "document_type": document_type,
        "document_label": DOCUMENT_TYPES.get(document_type, document_type.replace("_", " ").title()),
        "name": str(name),
        "email": str(safe_data.get("email", "")),
        "filename": filename,
        "email_status": email_status,
        "email_error": re.sub(r"[\r\n]+", " ", str(email_error or ""))[:1000],
        "admin_user": admin_user,
        "created_at": _now_iso(),
        "data": safe_data,
    }
    if extra:
        record["extra"] = {str(k): str(v) for k, v in extra.items()}

    collection = _mongo_collection()
    if collection is not None:
        try:
            collection.insert_one(dict(record))
            return True, "MongoDB"
        except Exception:
            pass

    try:
        with _LOCK:
            records = _read_local()
            records.append(record)
            _write_local(records)
        return True, "Local JSON fallback"
    except Exception as exc:
        return False, str(exc)


def list_document_logs(document_type=None, limit=500):
    limit = max(1, min(int(limit or 500), 5000))
    collection = _mongo_collection()
    if collection is not None:
        query = {"document_type": document_type} if document_type else {}
        try:
            records = list(collection.find(query, {"_id": 0}).sort("created_at", DESCENDING).limit(limit))
            return records
        except Exception:
            pass

    records = _read_local()
    if document_type:
        records = [r for r in records if r.get("document_type") == document_type]
    records.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return records[:limit]


def dashboard_counts():
    counts = {key: 0 for key in DOCUMENT_TYPES}
    total = 0
    sent = 0
    failed = 0
    for row in list_document_logs(limit=5000):
        total += 1
        dtype = row.get("document_type")
        if dtype in counts:
            counts[dtype] += 1
        status = row.get("email_status")
        if status == "sent":
            sent += 1
        elif status == "failed":
            failed += 1
    return {"by_type": counts, "total": total, "sent": sent, "failed": failed}
