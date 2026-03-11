"""
Celery tasks for syncing Google Drive files to ACR Cloud.
Pipeline: list Drive files -> download new ones -> upload to ACR -> record & cleanup.
"""
import hashlib
import hmac
import logging
import os
import base64
import time
from pathlib import Path

from celery import shared_task
from django.conf import settings
from dotenv import load_dotenv

# Ensure .env is loaded when task runs (worker may have different cwd)
load_dotenv(settings.BASE_DIR / ".env")

from sync_app.models import SyncedFile

logger = logging.getLogger(__name__)

# Local directory for temporary downloads (created if missing)
DOWNLOADS_DIR = settings.BASE_DIR / "downloads"


def _default_summary(error=None):
    """Default summary dict when something fails early."""
    out = {
        "success": error is None,
        "error": str(error) if error else None,
        "message": "",
        "files_in_folder": 0,
        "files_to_process": 0,
        "downloaded": 0,
        "acr_success": 0,
        "acr_failed": 0,
        "last_acr_error": None,
    }
    return out


def _get_drive_credentials():
    """Resolve Google Drive folder ID and service account path from environment."""
    folder_id = os.environ.get("DRIVE_FOLDER_ID")
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not folder_id or not creds_path:
        raise ValueError(
            "DRIVE_FOLDER_ID and GOOGLE_APPLICATION_CREDENTIALS must be set in .env"
        )
    # If path is relative, resolve against project base (so "file.json" works)
    if not os.path.isabs(creds_path):
        creds_path = str(settings.BASE_DIR / creds_path)
    if not os.path.isfile(creds_path):
        raise FileNotFoundError(f"Google credentials file not found: {creds_path}")
    return folder_id, creds_path


def _get_acr_credentials():
    """Get ACR Cloud host, access key, and access secret from environment."""
    host = os.environ.get("ACR_HOST")
    access_key = os.environ.get("ACR_ACCESS_KEY")
    access_secret = os.environ.get("ACR_ACCESS_SECRET")
    if not all((host, access_key, access_secret)):
        raise ValueError(
            "ACR_HOST, ACR_ACCESS_KEY, and ACR_ACCESS_SECRET must be set in .env"
        )
    return host, access_key, access_secret


def _build_acr_signature(access_key: str, access_secret: str, timestamp: str) -> str:
    """
    Build HMAC-SHA1 signature for ACR Cloud API.
    String to sign: POST + newline + http_uri + newline + access_key + newline + signature_version + newline + timestamp
    """
    http_uri = "/v1/audios"
    signature_version = "1"
    string_to_sign = (
        "POST" + "\n" + http_uri + "\n" + access_key + "\n" + signature_version + "\n" + timestamp
    )
    signature_bytes = hmac.new(
        access_secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    return base64.b64encode(signature_bytes).decode("utf-8")


def _upload_file_to_acr(file_path: str, file_name: str, drive_file_id: str, bucket_id_override: str = None):
    """
    Upload a single file to ACR Cloud.
    bucket_id_override: if set, use this bucket ID for v2 upload instead of ACR_BUCKET_ID from env.
    """
    try:
        import requests
    except ImportError:
        logger.error("requests library is required for ACR upload. pip install requests")
        return False, "requests not installed", ""

    bearer_token = os.environ.get("ACR_BEARER_TOKEN", "").strip()
    bucket_id = (bucket_id_override or "").strip() or os.environ.get("ACR_BUCKET_ID", "").strip()

    # Prefer Console API v2 (required for "Audio Fingerprinting" projects; Access Key is for identify only)
    if bearer_token and bucket_id:
        return _upload_file_to_acr_v2(file_path, file_name, bearer_token, bucket_id, requests)
    # Fallback: legacy v1/audios (HMAC)
    return _upload_file_to_acr_v1(file_path, file_name, drive_file_id, requests)


def _upload_file_to_acr_v2(file_path: str, file_name: str, bearer_token: str, bucket_id: str, requests_module):
    """Console API v2: POST api-v2.acrcloud.com/api/buckets/:bucket_id/files with Bearer token."""
    url = f"https://api-v2.acrcloud.com/api/buckets/{bucket_id}/files"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {bearer_token}",
    }
    data = {"title": file_name, "data_type": "audio"}
    mime = "audio/mpeg" if file_name.lower().endswith(".mp3") else "application/octet-stream"
    with open(file_path, "rb") as f:
        response = requests_module.post(
            url,
            headers=headers,
            data=data,
            files=[("file", (file_name, f, mime))],
            timeout=120,
        )
    if response.status_code in (200, 201):
        duration = ""
        try:
            data = response.json()
            duration = str(data.get("data", {}).get("duration", ""))
        except Exception:
            pass
        return True, "success", duration
    return False, f"HTTP {response.status_code}: {response.text[:200]}", ""


def _upload_file_to_acr_v1(file_path: str, file_name: str, drive_file_id: str, requests_module):
    """Legacy v1/audios: HMAC-signed POST to api.acrcloud.com/v1/audios (bucket_name, etc.)."""
    host, access_key, access_secret = _get_acr_credentials()
    bucket_name = os.environ.get("ACR_BUCKET_NAME", "").strip()
    if not bucket_name:
        return False, "For v1 uploads set ACR_BUCKET_NAME. For Console API v2 set ACR_BEARER_TOKEN and ACR_BUCKET_ID.", ""

    upload_host = os.environ.get("ACR_UPLOAD_HOST", "").strip() or None
    if not upload_host and "identify" in host.lower():
        upload_host = "api.acrcloud.com"
    else:
        upload_host = upload_host or host

    timestamp_ms = str(int(time.time() * 1000))
    signature = _build_acr_signature(access_key, access_secret, timestamp_ms)
    base_url = upload_host if upload_host.startswith("http") else f"https://{upload_host}"
    url = f"{base_url.rstrip('/')}/v1/audios"
    headers = {
        "access-key": access_key,
        "signature": signature,
        "signature-version": "1",
        "timestamp": timestamp_ms,
    }
    data = {
        "bucket_name": bucket_name,
        "title": file_name,
        "audio_id": drive_file_id,
        "data_type": "audio",
    }
    with open(file_path, "rb") as f:
        response = requests_module.post(
            url,
            headers=headers,
            data=data,
            files={"audio_file": (file_name, f, "application/octet-stream")},
            timeout=120,
        )
    if response.status_code in (200, 201):
        return True, "success", ""
    return False, f"HTTP {response.status_code}: {response.text[:200]}", ""


def _date_to_drive_rfc3339(date_val, end_of_day=False):
    """Convert date (str YYYY-MM-DD or date) to Drive API RFC 3339 string."""
    if date_val is None:
        return None
    if hasattr(date_val, "strftime"):
        d = date_val
    else:
        from datetime import datetime
        d = datetime.strptime(str(date_val).strip()[:10], "%Y-%m-%d").date()
    if end_of_day:
        return f"{d.isoformat()}T23:59:59"
    return f"{d.isoformat()}T00:00:00"


def run_sync_drive_to_acr(from_date=None, to_date=None, bucket_id_override=None):
    """
    Run the full sync pipeline (Drive -> download -> ACR -> record & cleanup).
    from_date / to_date: optional date filter (str YYYY-MM-DD or date). Only files with
    modifiedTime >= from_date and modifiedTime <= to_date are synced.
    bucket_id_override: optional ACR bucket ID to use for this run instead of ACR_BUCKET_ID from env.
    Returns a summary dict.
    """
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseDownload
    except ImportError as e:
        logger.exception("Google API libraries missing: %s", e)
        return _default_summary(e)

    try:
        folder_id, creds_path = _get_drive_credentials()
    except Exception as e:
        logger.exception("Credentials error: %s", e)
        return _default_summary(e)

    scopes = ["https://www.googleapis.com/auth/drive.readonly"]
    credentials = service_account.Credentials.from_service_account_file(
        creds_path, scopes=scopes
    )
    drive = build("drive", "v3", credentials=credentials, cache_discovery=False)

    # ----- Phase A: List files in folder (trashed = false), optional date filter, exclude already synced -----
    existing_ids = set(SyncedFile.objects.values_list("drive_file_id", flat=True))

    query = f"'{folder_id}' in parents and trashed = false"
    if from_date:
        from_rfc = _date_to_drive_rfc3339(from_date, end_of_day=False)
        query += f" and modifiedTime >= '{from_rfc}'"
    if to_date:
        to_rfc = _date_to_drive_rfc3339(to_date, end_of_day=True)
        query += f" and modifiedTime <= '{to_rfc}'"

    fields = "files(id, name, modifiedTime)" if (from_date or to_date) else "files(id, name)"
    try:
        results = (
            drive.files()
            .list(q=query, fields=fields, pageSize=100, supportsAllDrives=True)
            .execute()
        )
    except Exception as e:
        logger.exception("Drive list failed: %s", e)
        return _default_summary(e)

    files_in_folder = results.get("files", [])
    to_process = [f for f in files_in_folder if f["id"] not in existing_ids]

    if not to_process:
        logger.info("No new Drive files to sync.")
        return {
            **_default_summary(),
            "message": "No new Drive files to sync.",
            "files_in_folder": len(files_in_folder),
            "files_to_process": 0,
        }

    logger.info("Sync started: %d new file(s) to process from Drive.", len(to_process))
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    downloaded = []  # list of (drive_file_id, file_name, local_path)

    for file_meta in to_process:
        file_id = file_meta["id"]
        file_name = file_meta.get("name", "unknown")
        safe_name = "".join(c for c in file_name if c.isalnum() or c in "._- ") or file_id
        local_path = DOWNLOADS_DIR / f"{file_id}_{safe_name}"

        try:
            request = drive.files().get_media(fileId=file_id, supportsAllDrives=True)
            with open(local_path, "wb") as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
        except Exception as e:
            logger.exception("Failed to download Drive file %s: %s", file_id, e)
            continue
        logger.info("Downloaded from Drive: %s (%s)", file_name, file_id)
        downloaded.append((file_id, file_name, str(local_path)))

    # ----- Phase B & C: Upload to ACR, then create record and cleanup -----
    acr_success = 0
    acr_failed = 0
    last_acr_error = None

    for drive_file_id, file_name, local_path in downloaded:
        logger.info("Uploading to ACR: %s", file_name)
        success, acr_status, acr_duration = _upload_file_to_acr(
            local_path, file_name, drive_file_id, bucket_id_override=bucket_id_override
        )

        try:
            if os.path.isfile(local_path):
                os.remove(local_path)
        except OSError as e:
            logger.warning("Could not remove local file %s: %s", local_path, e)

        if success:
            SyncedFile.objects.create(
                drive_file_id=drive_file_id,
                file_name=file_name,
                acr_status=acr_status,
                acr_duration=acr_duration or "",
            )
            acr_success += 1
            logger.info("Synced successfully: %s (Drive ID: %s) -> ACR, record saved.", file_name, drive_file_id)
        else:
            acr_failed += 1
            last_acr_error = acr_status
            logger.error(
                "ACR upload failed for %s (%s): %s; will retry on next run.",
                file_name,
                drive_file_id,
                acr_status,
            )

    logger.info(
        "Sync complete: %d file(s) synced successfully, %d failed.",
        acr_success,
        acr_failed,
    )
    return {
        "success": True,
        "error": None,
        "message": f"Processed {len(downloaded)} file(s).",
        "files_in_folder": len(files_in_folder),
        "files_to_process": len(to_process),
        "downloaded": len(downloaded),
        "acr_success": acr_success,
        "acr_failed": acr_failed,
        "last_acr_error": last_acr_error,
    }


@shared_task(name="sync_app.tasks.sync_drive_to_acr", bind=True)
def sync_drive_to_acr(self, from_date=None, to_date=None, bucket_id_override=None):
    """
    Celery task: sync new files from Google Drive folder to ACR Cloud.
    Optional: from_date, to_date (str YYYY-MM-DD), bucket_id_override (str).
    """
    try:
        summary = run_sync_drive_to_acr(
            from_date=from_date,
            to_date=to_date,
            bucket_id_override=bucket_id_override,
        )
        return summary
    except Exception as e:
        logger.exception("sync_drive_to_acr failed: %s", e)
        return _default_summary(e)
