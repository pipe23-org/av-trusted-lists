import json
from pathlib import Path

import pytest

from av_trusted_lists.archive import Event, checks, events, sidecars, versions
from av_trusted_lists.lists import parse
from tests.conftest import archived, certificate, list_xml, provider_xml, service_xml


def test_sidecars_oldest_first(tmp_path: Path) -> None:
    archived(tmp_path, list_xml(provider_xml(service_xml())), "2026-11-02T03:04:05Z")
    archived(tmp_path, list_xml(provider_xml(service_xml())), "2026-11-01T03:04:05Z")
    assert [sidecar["retrieved"] for sidecar in sidecars(tmp_path)] == [
        "2026-11-01T03:04:05Z",
        "2026-11-02T03:04:05Z",
    ]


def test_sidecars_empty_directory(tmp_path: Path) -> None:
    assert sidecars(tmp_path) == []


def test_versions_oldest_first(tmp_path: Path) -> None:
    archived(tmp_path, list_xml(provider_xml(service_xml()), sequence="5"), "2026-11-02T03:04:05Z")
    archived(tmp_path, list_xml(provider_xml(service_xml()), sequence="4"), "2026-11-01T03:04:05Z")
    read = versions(tmp_path)
    assert [version.file for version in read] == [
        "2026-11-01T030405Z.xml",
        "2026-11-02T030405Z.xml",
    ]
    assert [version.content.sequence for version in read] == ["4", "5"]


def test_versions_empty_directory(tmp_path: Path) -> None:
    assert versions(tmp_path) == []


def test_version_captured_date(tmp_path: Path) -> None:
    archived(tmp_path, list_xml(provider_xml(service_xml())), "2026-11-02T03:04:05Z")
    assert versions(tmp_path)[0].captured == "2026-11-02"


def test_version_sidecar_read(tmp_path: Path) -> None:
    archived(
        tmp_path,
        list_xml(provider_xml(service_xml())),
        "2026-11-02T03:04:05Z",
        url="https://example.test/av-tl.xml",
    )
    assert versions(tmp_path)[0].sidecar["url"] == "https://example.test/av-tl.xml"


def test_unreadable_version_rejected(tmp_path: Path) -> None:
    archived(tmp_path, b"<html></html>", "2026-11-02T03:04:05Z")
    with pytest.raises(ValueError):
        versions(tmp_path)


def test_checks_oldest_first(tmp_path: Path) -> None:
    lines = [
        json.dumps({"checked": "2026-11-01T03:04:05Z", "changed": True}),
        json.dumps({"checked": "2026-11-02T03:04:05Z", "changed": False}),
    ]
    (tmp_path / "checks.jsonl").write_text("\n".join(lines) + "\n")
    assert [line["checked"] for line in checks(tmp_path)] == [
        "2026-11-01T03:04:05Z",
        "2026-11-02T03:04:05Z",
    ]


def test_checks_log_absent(tmp_path: Path) -> None:
    assert checks(tmp_path) == []


def test_service_added() -> None:
    before = parse(list_xml(provider_xml(service_xml(names=(("en", "Age check"),)), country="FI")))
    after = parse(
        list_xml(
            provider_xml(
                service_xml(names=(("en", "Age check"),)),
                service_xml(names=(("en", "Second check"),)),
                country="FI",
            )
        )
    )
    assert events(before, after) == [Event("FI", "Second check", "added")]


def test_service_removed() -> None:
    before = parse(
        list_xml(
            provider_xml(
                service_xml(names=(("en", "Age check"),)),
                service_xml(names=(("en", "Second check"),)),
                country="FI",
            )
        )
    )
    after = parse(list_xml(provider_xml(service_xml(names=(("en", "Age check"),)), country="FI")))
    assert events(before, after) == [Event("FI", "Second check", "removed")]


def test_status_changed() -> None:
    before = parse(list_xml(provider_xml(service_xml(status="recognized"), country="FI")))
    after = parse(list_xml(provider_xml(service_xml(status="withdrawn"), country="FI")))
    assert events(before, after) == [Event("FI", "Age check", "status recognized to withdrawn")]


def test_certificate_replaced() -> None:
    before = parse(
        list_xml(provider_xml(service_xml(certificates=(certificate("First"),)), country="FI"))
    )
    after = parse(
        list_xml(provider_xml(service_xml(certificates=(certificate("Second"),)), country="FI"))
    )
    assert events(before, after) == [Event("FI", "Age check", "certificate replaced")]


def test_status_time_changed() -> None:
    before = parse(list_xml(provider_xml(service_xml(since="2026-01-05T00:00:00Z"), country="FI")))
    after = parse(list_xml(provider_xml(service_xml(since="2026-06-05T00:00:00Z"), country="FI")))
    assert events(before, after) == [Event("FI", "Age check", "status time changed")]


def test_unchanged_service_no_event() -> None:
    data = list_xml(provider_xml(service_xml(certificates=(certificate(),)), country="FI"))
    assert events(parse(data), parse(data)) == []


def test_status_change_reported_over_certificate_change() -> None:
    before = parse(
        list_xml(
            provider_xml(
                service_xml(status="recognized", certificates=(certificate("First"),)),
                country="FI",
            )
        )
    )
    after = parse(
        list_xml(
            provider_xml(
                service_xml(status="withdrawn", certificates=(certificate("Second"),)),
                country="FI",
            )
        )
    )
    assert events(before, after) == [Event("FI", "Age check", "status recognized to withdrawn")]
