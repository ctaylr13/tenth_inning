import datetime as dt
from unittest.mock import Mock

import pytest

import artifact_delivery
from errors import InternalError


def test_signed_download_url_is_a_short_lived_v4_get(monkeypatch):
    monkeypatch.setenv("GCS_BUCKET", "private-artifacts")
    monkeypatch.setenv("GCS_SIGNED_URL_TTL_SECONDS", "120")

    blob = Mock()
    blob.generate_signed_url.return_value = "https://signed.example/game.pb"
    bucket = Mock()
    bucket.blob.return_value = blob
    client = Mock()
    client.bucket.return_value = bucket

    class Storage:
        Client = Mock(return_value=client)

    # Supply the optional package import without requiring credentials/network.
    import sys
    import types

    google = types.ModuleType("google")
    cloud = types.ModuleType("google.cloud")
    cloud.storage = Storage
    google.cloud = cloud
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.cloud", cloud)

    assert (
        artifact_delivery.signed_download_url("games/777/v1/game.pb")
        == "https://signed.example/game.pb"
    )
    client.bucket.assert_called_once_with("private-artifacts")
    bucket.blob.assert_called_once_with("games/777/v1/game.pb")
    blob.generate_signed_url.assert_called_once_with(
        version="v4", expiration=dt.timedelta(seconds=120), method="GET"
    )


def test_signed_download_url_requires_bucket(monkeypatch):
    monkeypatch.delenv("GCS_BUCKET", raising=False)
    with pytest.raises(InternalError, match="not configured"):
        artifact_delivery.signed_download_url("games/777/v1/game.pb")
