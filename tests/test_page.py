import json
from datetime import date
from pathlib import Path

from av_trusted_lists.page import build
from tests.conftest import archived, certificate, list_xml, provider_xml, service_xml

TODAY = date(2026, 11, 2)


def test_page_files_written(tmp_path: Path) -> None:
    archive, out = tmp_path / "archive", tmp_path / "out"
    archived(archive / "production", list_xml(provider_xml(service_xml())), "2026-11-02T03:04:05Z")
    (archive / "acceptance").mkdir(parents=True)
    build(archive, out, today=TODAY)
    exported = json.loads((out / "data.json").read_text())
    assert (out / "index.html").read_text().startswith("<!doctype html>")
    assert exported["built"] == "2026-11-02"
    assert exported["lists"]["production"]["label"] == "Trusted list"
    assert exported["lists"]["acceptance"]["label"] == "Test list"


def test_list_text_escaped_in_table(tmp_path: Path) -> None:
    archive, out = tmp_path / "archive", tmp_path / "out"
    archived(
        archive / "production",
        list_xml(
            provider_xml(
                service_xml(names=(("en", 'Age <check> "now"'),)),
                names=(("en", "Bar & <Grill>"),),
            )
        ),
        "2026-11-02T03:04:05Z",
    )
    (archive / "acceptance").mkdir(parents=True)
    build(archive, out, today=TODAY)
    page = (out / "index.html").read_text()
    assert "<td>Bar &amp; &lt;Grill&gt;</td>" in page
    assert "<td>Age &lt;check&gt; &quot;now&quot;</td>" in page


def test_embedded_data_escapes_angle_bracket(tmp_path: Path) -> None:
    archive, out = tmp_path / "archive", tmp_path / "out"
    archived(
        archive / "production",
        list_xml(provider_xml(service_xml(names=(("en", "Age</script>check"),)))),
        "2026-11-02T03:04:05Z",
    )
    (archive / "acceptance").mkdir(parents=True)
    build(archive, out, today=TODAY)
    page = (out / "index.html").read_text()
    assert "Age\\u003c/script>check" in page
    assert "Age</script>check" not in page


def test_recognized_production_country_prod(tmp_path: Path) -> None:
    archive, out = tmp_path / "archive", tmp_path / "out"
    archived(
        archive / "production",
        list_xml(provider_xml(service_xml(status="recognized"), country="FI")),
        "2026-11-02T03:04:05Z",
    )
    (archive / "acceptance").mkdir(parents=True)
    build(archive, out, today=TODAY)
    page = (out / "index.html").read_text()
    assert '<use href="#c-FI" class="prod" data-cc="FI"><title>Finland</title></use>' in page


def test_recognized_acceptance_country_test(tmp_path: Path) -> None:
    archive, out = tmp_path / "archive", tmp_path / "out"
    archived(
        archive / "acceptance",
        list_xml(provider_xml(service_xml(status="recognized"), country="PT")),
        "2026-11-02T03:04:05Z",
    )
    (archive / "production").mkdir(parents=True)
    build(archive, out, today=TODAY)
    page = (out / "index.html").read_text()
    assert '<use href="#c-PT" class="test" data-cc="PT"><title>Portugal</title></use>' in page


def test_expired_certificate_marked(tmp_path: Path) -> None:
    archive, out = tmp_path / "archive", tmp_path / "out"
    encoded = certificate(not_before=date(2026, 1, 1), not_after=date(2026, 1, 2))
    archived(
        archive / "production",
        list_xml(provider_xml(service_xml(certificates=(encoded,)))),
        "2026-11-02T03:04:05Z",
    )
    (archive / "acceptance").mkdir(parents=True)
    build(archive, out, today=TODAY)
    page = (out / "index.html").read_text()
    assert "<td class=nw>2026-01-01</td><td class=nw>2026-01-02</td><td>expired</td>" in page


def test_unexpired_certificate_valid(tmp_path: Path) -> None:
    archive, out = tmp_path / "archive", tmp_path / "out"
    encoded = certificate(not_before=date(2026, 1, 1), not_after=date(2030, 1, 2))
    archived(
        archive / "production",
        list_xml(provider_xml(service_xml(certificates=(encoded,)))),
        "2026-11-02T03:04:05Z",
    )
    (archive / "acceptance").mkdir(parents=True)
    build(archive, out, today=TODAY)
    page = (out / "index.html").read_text()
    assert "<td class=nw>2026-01-01</td><td class=nw>2030-01-02</td><td>valid</td>" in page


def test_service_without_certificate_listed(tmp_path: Path) -> None:
    archive, out = tmp_path / "archive", tmp_path / "out"
    archived(
        archive / "production",
        list_xml(
            provider_xml(
                service_xml(
                    names=(("en", "Age check"),), since="2026-01-05T00:00:00Z", certificates=()
                )
            )
        ),
        "2026-11-02T03:04:05Z",
    )
    (archive / "acceptance").mkdir(parents=True)
    build(archive, out, today=TODAY)
    page = (out / "index.html").read_text()
    assert "<td>Age check</td>" in page
    assert "<td class=nw>2026-01-05</td><td class=nw></td><td class=nw></td><td></td></tr>" in page


def test_list_without_archived_version_built(tmp_path: Path) -> None:
    archive, out = tmp_path / "archive", tmp_path / "out"
    archived(
        archive / "production",
        list_xml(provider_xml(service_xml(), country="FI")),
        "2026-11-02T03:04:05Z",
    )
    (archive / "acceptance").mkdir(parents=True)
    build(archive, out, today=TODAY)
    exported = json.loads((out / "data.json").read_text())
    assert (out / "index.html").exists()
    assert exported["lists"]["acceptance"]["countries"] == {}
    assert list(exported["lists"]["production"]["countries"]) == ["FI"]


def test_changes_section_lists_events(tmp_path: Path) -> None:
    archive, out = tmp_path / "archive", tmp_path / "out"
    archived(
        archive / "production",
        list_xml(provider_xml(service_xml(names=(("en", "Age check"),)), country="FI")),
        "2026-11-02T03:04:05Z",
    )
    archived(
        archive / "production",
        list_xml(
            provider_xml(
                service_xml(names=(("en", "Age check"),)),
                service_xml(names=(("en", "Second check"),)),
                country="FI",
            )
        ),
        "2026-11-03T03:04:05Z",
    )
    (archive / "acceptance").mkdir(parents=True)
    build(archive, out, today=TODAY)
    page = (out / "index.html").read_text()
    assert "<li>2026-11-03, trusted list: Finland, Second check, added</li>" in page


def test_last_change_dates(tmp_path: Path) -> None:
    archive, out = tmp_path / "archive", tmp_path / "out"
    unchanged = provider_xml(service_xml(names=(("en", "Age check"),)), country="FI")
    archived(
        archive / "production",
        list_xml(
            unchanged,
            provider_xml(service_xml(names=(("en", "Idade"),), status="recognized"), country="PT"),
        ),
        "2026-11-02T03:04:05Z",
    )
    archived(
        archive / "production",
        list_xml(
            unchanged,
            provider_xml(service_xml(names=(("en", "Idade"),), status="withdrawn"), country="PT"),
        ),
        "2026-11-03T03:04:05Z",
    )
    (archive / "acceptance").mkdir(parents=True)
    build(archive, out, today=TODAY)
    countries = json.loads((out / "data.json").read_text())["lists"]["production"]["countries"]
    assert countries["FI"]["last_change"] == "2026-11-02"
    assert countries["PT"]["last_change"] == "2026-11-03"


def test_first_seen_dates(tmp_path: Path) -> None:
    archive, out = tmp_path / "archive", tmp_path / "out"
    archived(
        archive / "production",
        list_xml(provider_xml(service_xml(names=(("en", "Age check"),)), country="FI")),
        "2026-11-02T03:04:05Z",
    )
    archived(
        archive / "production",
        list_xml(
            provider_xml(
                service_xml(names=(("en", "Age check"),)),
                service_xml(names=(("en", "Second check"),)),
                country="FI",
            )
        ),
        "2026-11-03T03:04:05Z",
    )
    (archive / "acceptance").mkdir(parents=True)
    build(archive, out, today=TODAY)
    countries = json.loads((out / "data.json").read_text())["lists"]["production"]["countries"]
    seen: dict[str, str] = {
        service["name"]: service["first_seen"] for service in countries["FI"]["services"]
    }
    assert seen == {"Age check": "2026-11-02", "Second check": "2026-11-03"}


def test_list_facts_stated(tmp_path: Path) -> None:
    archive, out = tmp_path / "archive", tmp_path / "out"
    signer = certificate("EU Trusted List Signer")
    archived(
        archive / "production",
        list_xml(provider_xml(service_xml()), sequence="12", signer=signer),
        "2026-11-02T03:04:05Z",
        url="https://example.test/av-tl.xml",
    )
    (archive / "production" / "checks.jsonl").write_text(
        json.dumps({"checked": "2026-11-02T03:04:05Z", "changed": True})
        + "\n"
        + json.dumps({"checked": "2026-11-03T03:04:05Z", "error": "connection refused"})
        + "\n"
    )
    (archive / "acceptance").mkdir(parents=True)
    build(archive, out, today=TODAY)
    page = (out / "index.html").read_text()
    assert "<th>Address</th><td>https://example.test/av-tl.xml</td>" in page
    assert "<th>Sequence number</th><td>12</td>" in page
    assert "<th>Signer</th><td>CN=EU Trusted List Signer</td>" in page
    assert "<th>Last checked</th><td>2026-11-02T03:04:05Z</td>" in page
