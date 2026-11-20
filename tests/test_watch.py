import hashlib
import json
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pytest

from av_trusted_lists.archive import LISTS
from av_trusted_lists.watch import Response, fetch, watch
from tests.conftest import certificate, list_xml, provider_xml, service_xml

MOMENT = datetime(2026, 11, 2, 3, 4, 5, tzinfo=UTC)
LAST_MODIFIED = "Sat, 01 Nov 2026 06:00:00 GMT"


def test_first_check_archives_bytes(tmp_path: Path) -> None:
    data = list_xml(provider_xml(service_xml(certificates=(certificate(),))))

    def serve(url: str) -> Response:
        return Response(
            data=data, last_modified=LAST_MODIFIED, etag='"a1"', content_type="application/xml"
        )

    assert watch(tmp_path / "archive", tmp_path / "reports", fetch=serve, now=MOMENT) is True
    archived = tmp_path / "archive" / "production" / "2026-11-02T030405Z.xml"
    assert archived.read_bytes() == data


def test_first_check_sidecar_records_retrieval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "pipe23-org/av-trusted-lists")
    monkeypatch.setenv("GITHUB_SHA", "9f1c2d3e")
    monkeypatch.setenv("GITHUB_RUN_ID", "4242")
    data = list_xml(provider_xml(service_xml()))

    def serve(url: str) -> Response:
        return Response(
            data=data, last_modified=LAST_MODIFIED, etag='"a1"', content_type="application/xml"
        )

    watch(tmp_path / "archive", tmp_path / "reports", fetch=serve, now=MOMENT)
    sidecar = tmp_path / "archive" / "production" / "2026-11-02T030405Z.json"
    assert json.loads(sidecar.read_text()) == {
        "list": "production",
        "url": LISTS["production"],
        "retrieved": "2026-11-02T03:04:05Z",
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "last_modified": LAST_MODIFIED,
        "etag": '"a1"',
        "content_type": "application/xml",
        "previous_sha256": None,
        "repository": "pipe23-org/av-trusted-lists",
        "commit": "9f1c2d3e",
        "run": "4242",
    }


def test_sidecar_workflow_fields_absent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_RUN_ID"):
        monkeypatch.delenv(name, raising=False)
    data = list_xml(provider_xml(service_xml()))

    def serve(url: str) -> Response:
        return Response(
            data=data, last_modified=LAST_MODIFIED, etag='"a1"', content_type="application/xml"
        )

    watch(tmp_path / "archive", tmp_path / "reports", fetch=serve, now=MOMENT)
    sidecar = tmp_path / "archive" / "production" / "2026-11-02T030405Z.json"
    recorded = json.loads(sidecar.read_text())
    assert recorded["repository"] is None
    assert recorded["commit"] is None
    assert recorded["run"] is None


def test_sidecar_headers_absent(tmp_path: Path) -> None:
    data = list_xml(provider_xml(service_xml()))

    def serve(url: str) -> Response:
        return Response(data=data, last_modified=None, etag=None, content_type=None)

    watch(tmp_path / "archive", tmp_path / "reports", fetch=serve, now=MOMENT)
    sidecar = tmp_path / "archive" / "production" / "2026-11-02T030405Z.json"
    recorded = json.loads(sidecar.read_text())
    assert recorded["last_modified"] is None
    assert recorded["etag"] is None
    assert recorded["content_type"] is None


def test_first_check_logged(tmp_path: Path) -> None:
    data = list_xml(provider_xml(service_xml()))

    def serve(url: str) -> Response:
        return Response(
            data=data, last_modified=LAST_MODIFIED, etag='"a1"', content_type="application/xml"
        )

    watch(tmp_path / "archive", tmp_path / "reports", fetch=serve, now=MOMENT)
    log = (tmp_path / "archive" / "production" / "checks.jsonl").read_text()
    assert [json.loads(line) for line in log.splitlines()] == [
        {
            "checked": "2026-11-02T03:04:05Z",
            "sha256": hashlib.sha256(data).hexdigest(),
            "last_modified": LAST_MODIFIED,
            "etag": '"a1"',
            "changed": True,
        }
    ]


def test_first_check_report_titled(tmp_path: Path) -> None:
    data = list_xml(provider_xml(service_xml()), sequence="12", issued="2026-11-01T00:00:00Z")

    def serve(url: str) -> Response:
        return Response(data=data, last_modified=None, etag=None, content_type=None)

    watch(tmp_path / "archive", tmp_path / "reports", fetch=serve, now=MOMENT)
    report = (tmp_path / "reports" / "production.md").read_text().splitlines()
    assert report[0] == "production list: sequence 12, issued 2026-11-01T00:00:00Z"
    assert report[1] == ""


def test_repeated_bytes_no_new_version(tmp_path: Path) -> None:
    data = list_xml(provider_xml(service_xml()))

    def serve(url: str) -> Response:
        return Response(data=data, last_modified=None, etag=None, content_type=None)

    archive, reports = tmp_path / "archive", tmp_path / "reports"
    watch(archive, reports, fetch=serve, now=MOMENT)
    first_report = (reports / "production.md").read_text()
    watch(archive, reports, fetch=serve, now=datetime(2026, 11, 3, 3, 4, 5, tzinfo=UTC))
    assert sorted(path.name for path in (archive / "production").glob("*.xml")) == [
        "2026-11-02T030405Z.xml"
    ]
    assert (reports / "production.md").read_text() == first_report


def test_repeated_bytes_logged(tmp_path: Path) -> None:
    data = list_xml(provider_xml(service_xml()))

    def serve(url: str) -> Response:
        return Response(data=data, last_modified=None, etag=None, content_type=None)

    archive, reports = tmp_path / "archive", tmp_path / "reports"
    watch(archive, reports, fetch=serve, now=MOMENT)
    watch(archive, reports, fetch=serve, now=datetime(2026, 11, 3, 3, 4, 5, tzinfo=UTC))
    log = (archive / "production" / "checks.jsonl").read_text()
    lines = [json.loads(line) for line in log.splitlines()]
    assert [(line["checked"], line["changed"]) for line in lines] == [
        ("2026-11-02T03:04:05Z", True),
        ("2026-11-03T03:04:05Z", False),
    ]


def test_changed_bytes_second_version(tmp_path: Path) -> None:
    first = list_xml(provider_xml(service_xml(names=(("en", "Age check"),))))
    second = list_xml(
        provider_xml(
            service_xml(names=(("en", "Age check"),)),
            service_xml(names=(("en", "Second check"),)),
        )
    )
    served = [first]

    def serve(url: str) -> Response:
        return Response(data=served[-1], last_modified=None, etag=None, content_type=None)

    archive, reports = tmp_path / "archive", tmp_path / "reports"
    watch(archive, reports, fetch=serve, now=MOMENT)
    served.append(second)
    watch(archive, reports, fetch=serve, now=datetime(2026, 11, 3, 3, 4, 5, tzinfo=UTC))
    assert sorted(path.name for path in (archive / "production").glob("*.xml")) == [
        "2026-11-02T030405Z.xml",
        "2026-11-03T030405Z.xml",
    ]
    sidecar = json.loads((archive / "production" / "2026-11-03T030405Z.json").read_text())
    assert sidecar["previous_sha256"] == hashlib.sha256(first).hexdigest()


def test_change_report_names_previous_version(tmp_path: Path) -> None:
    first = list_xml(provider_xml(service_xml(names=(("en", "Age check"),)), country="FI"))
    second = list_xml(
        provider_xml(
            service_xml(names=(("en", "Age check"),)),
            service_xml(names=(("en", "Second check"),)),
            country="FI",
        )
    )
    served = [first]

    def serve(url: str) -> Response:
        return Response(data=served[-1], last_modified=None, etag=None, content_type=None)

    archive, reports = tmp_path / "archive", tmp_path / "reports"
    watch(archive, reports, fetch=serve, now=MOMENT)
    served.append(second)
    watch(archive, reports, fetch=serve, now=datetime(2026, 11, 3, 3, 4, 5, tzinfo=UTC))
    assert hashlib.sha256(first).hexdigest() in (reports / "production.md").read_text()


def test_change_report_lists_events(tmp_path: Path) -> None:
    first = list_xml(provider_xml(service_xml(names=(("en", "Age check"),)), country="FI"))
    second = list_xml(
        provider_xml(
            service_xml(names=(("en", "Age check"),)),
            service_xml(names=(("en", "Second check"),)),
            country="FI",
        )
    )
    served = [first]

    def serve(url: str) -> Response:
        return Response(data=served[-1], last_modified=None, etag=None, content_type=None)

    archive, reports = tmp_path / "archive", tmp_path / "reports"
    watch(archive, reports, fetch=serve, now=MOMENT)
    served.append(second)
    watch(archive, reports, fetch=serve, now=datetime(2026, 11, 3, 3, 4, 5, tzinfo=UTC))
    assert "- FI, Second check: added" in (reports / "production.md").read_text()


def test_change_report_without_events(tmp_path: Path) -> None:
    first = list_xml(provider_xml(service_xml()), sequence="4")
    second = list_xml(provider_xml(service_xml()), sequence="5")
    served = [first]

    def serve(url: str) -> Response:
        return Response(data=served[-1], last_modified=None, etag=None, content_type=None)

    archive, reports = tmp_path / "archive", tmp_path / "reports"
    watch(archive, reports, fetch=serve, now=MOMENT)
    served.append(second)
    watch(archive, reports, fetch=serve, now=datetime(2026, 11, 3, 3, 4, 5, tzinfo=UTC))
    assert "No service was added, removed or changed." in (reports / "production.md").read_text()


def test_summary_names_each_outcome(tmp_path: Path) -> None:
    data = list_xml(provider_xml(service_xml()))

    def serve(url: str) -> Response:
        return Response(data=data, last_modified=None, etag=None, content_type=None)

    watch(tmp_path / "archive", tmp_path / "reports", fetch=serve, now=MOMENT)
    summary = (tmp_path / "reports" / "summary.txt").read_text()
    assert summary == "2026-11-02: production changed, acceptance changed\n"


def test_fetch_error_leaves_other_list_processed(tmp_path: Path) -> None:
    data = list_xml(provider_xml(service_xml()))

    def serve(url: str) -> Response:
        if url == LISTS["production"]:
            raise OSError("connection refused")
        return Response(data=data, last_modified=None, etag=None, content_type=None)

    archive, reports = tmp_path / "archive", tmp_path / "reports"
    assert watch(archive, reports, fetch=serve, now=MOMENT) is False
    assert (archive / "acceptance" / "2026-11-02T030405Z.xml").read_bytes() == data
    assert (reports / "summary.txt").read_text() == (
        "2026-11-02: production failed, acceptance changed\n"
    )


def test_non_list_response_rejected(tmp_path: Path) -> None:
    data = list_xml(provider_xml(service_xml()))

    def serve(url: str) -> Response:
        if url == LISTS["production"]:
            return Response(
                data=b"<html></html>", last_modified=None, etag=None, content_type="text/html"
            )
        return Response(data=data, last_modified=None, etag=None, content_type=None)

    archive, reports = tmp_path / "archive", tmp_path / "reports"
    assert watch(archive, reports, fetch=serve, now=MOMENT) is False
    assert list((archive / "production").glob("*.xml")) == []
    assert json.loads((archive / "production" / "checks.jsonl").read_text()) == {
        "checked": "2026-11-02T03:04:05Z",
        "error": "the response is not a trusted list",
    }
    assert "production failed" in (reports / "summary.txt").read_text()


def test_unreadable_list_archived_and_failed(tmp_path: Path) -> None:
    truncated = list_xml(provider_xml(service_xml()))[:200]

    def serve(url: str) -> Response:
        return Response(data=truncated, last_modified=None, etag=None, content_type=None)

    archive, reports = tmp_path / "archive", tmp_path / "reports"
    assert watch(archive, reports, fetch=serve, now=MOMENT) is False
    assert (archive / "production" / "2026-11-02T030405Z.xml").read_bytes() == truncated
    assert (reports / "summary.txt").read_text() == (
        "2026-11-02: production failed, acceptance failed\n"
    )


def test_check_time_defaults_to_now(tmp_path: Path) -> None:
    data = list_xml(provider_xml(service_xml()))

    def serve(url: str) -> Response:
        return Response(data=data, last_modified=None, etag=None, content_type=None)

    before = datetime.now(UTC).replace(microsecond=0)
    watch(tmp_path / "archive", tmp_path / "reports", fetch=serve)
    after = datetime.now(UTC)
    sidecar = next((tmp_path / "archive" / "production").glob("*.json"))
    retrieved = datetime.strptime(
        json.loads(sidecar.read_text())["retrieved"], "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=UTC)
    assert before <= retrieved <= after


def test_fetch_reads_response(monkeypatch: pytest.MonkeyPatch) -> None:
    class Opened:
        headers = {
            "Last-Modified": LAST_MODIFIED,
            "ETag": '"a1"',
            "Content-Type": "application/xml",
        }

        def __enter__(self) -> "Opened":
            return self

        def __exit__(self, *arguments: object) -> None:
            return None

        def read(self) -> bytes:
            return b"<TrustServiceStatusList/>"

    requested: list[str] = []

    def urlopen(url: str, timeout: int = 0) -> Opened:
        requested.append(url)
        return Opened()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    response = fetch(LISTS["production"])
    assert response == Response(
        data=b"<TrustServiceStatusList/>",
        last_modified=LAST_MODIFIED,
        etag='"a1"',
        content_type="application/xml",
    )
    assert requested == [LISTS["production"]]
