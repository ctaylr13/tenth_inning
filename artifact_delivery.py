"""Private GCS delivery for generated game artifacts."""

import datetime as dt
import os

from errors import InternalError

DEFAULT_SIGNED_URL_TTL_SECONDS = 15 * 60


def signed_download_url(gcs_key: str) -> str:
    """Mint a short-lived V4 GET URL without proxying artifact bytes.

    The import is local so schema-only commands and tests that do not exercise
    artifact delivery can run without initializing Google credentials.
    """
    bucket_name = os.environ.get("GCS_BUCKET")
    if not bucket_name:
        raise InternalError("Artifact delivery is not configured.")

    try:
        ttl_seconds = int(
            os.environ.get(
                "GCS_SIGNED_URL_TTL_SECONDS", str(DEFAULT_SIGNED_URL_TTL_SECONDS)
            )
        )
    except ValueError as exc:
        raise InternalError("Artifact delivery is not configured correctly.") from exc
    if ttl_seconds <= 0:
        raise InternalError("Artifact delivery is not configured correctly.")

    try:
        from google.cloud import storage

        client = storage.Client()
        blob = client.bucket(bucket_name).blob(gcs_key)
        return blob.generate_signed_url(
            version="v4",
            expiration=dt.timedelta(seconds=ttl_seconds),
            method="GET",
        )
    except InternalError:
        raise
    except Exception as exc:
        # Credentials, IAM signing permissions, and client construction are all
        # server configuration failures. Keep those details out of the response.
        raise InternalError("The game artifact URL could not be created.") from exc
