from pathlib import Path

import pytest

from av_trusted_lists import __main__
from av_trusted_lists.__main__ import main
from tests.conftest import archived, list_xml, provider_xml, service_xml


def test_watch_runs_on_named_directories(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Path, Path]] = []

    def watch(archive: Path, reports: Path) -> bool:
        calls.append((archive, reports))
        return True

    monkeypatch.setattr(__main__, "watch", watch)
    main(["watch", str(tmp_path / "archive"), "--reports", str(tmp_path / "reports")])
    assert calls == [(tmp_path / "archive", tmp_path / "reports")]


def test_watch_reports_directory_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Path, Path]] = []

    def watch(archive: Path, reports: Path) -> bool:
        calls.append((archive, reports))
        return True

    monkeypatch.setattr(__main__, "watch", watch)
    main(["watch", str(tmp_path / "archive")])
    assert calls == [(tmp_path / "archive", Path("reports"))]


def test_watch_failure_exits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def watch(archive: Path, reports: Path) -> bool:
        return False

    monkeypatch.setattr(__main__, "watch", watch)
    with pytest.raises(SystemExit) as raised:
        main(["watch", str(tmp_path / "archive")])
    assert raised.value.code == 1


def test_build_writes_page(tmp_path: Path) -> None:
    archive, out = tmp_path / "archive", tmp_path / "out"
    archived(archive / "production", list_xml(provider_xml(service_xml())), "2026-11-02T03:04:05Z")
    (archive / "acceptance").mkdir(parents=True)
    main(["build", str(archive), str(out)])
    assert (out / "index.html").exists()
    assert (out / "data.json").exists()
