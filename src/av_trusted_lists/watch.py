"""Fetch both lists, archive a list whose bytes changed, and log every check."""

import hashlib
import json
import os
import sys
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from av_trusted_lists.archive import LISTS, events, sidecars, versions


@dataclass(frozen=True)
class Response:
    """What a fetch returned.

    Attributes:
        data: The response body.
        last_modified: The ``Last-Modified`` header, if any.
        etag: The ``ETag`` header, if any.
        content_type: The ``Content-Type`` header, if any.
    """

    data: bytes
    last_modified: str | None
    etag: str | None
    content_type: str | None


Fetch = Callable[[str], Response]


def fetch(url: str) -> Response:
    """GET a list over https."""
    with urllib.request.urlopen(url, timeout=60) as response:
        return Response(
            data=response.read(),
            last_modified=response.headers.get("Last-Modified"),
            etag=response.headers.get("ETag"),
            content_type=response.headers.get("Content-Type"),
        )


def watch(archive: Path, reports: Path, fetch: Fetch = fetch, now: datetime | None = None) -> bool:
    """Check every list once.

    A list whose bytes differ from its newest archived version is archived with
    a sidecar, and a report of the change is written to ``reports/<list>.md``:
    a title line, a blank line, then a Markdown body. Every check appends a line
    to the list's ``checks.jsonl``; the line of a failed check holds the time
    and the error. ``reports/summary.txt`` gets one line that names the outcome
    for each list.

    Args:
        archive: The archive directory.
        reports: Directory the reports are written to.
        fetch: Retrieves a list by its address.
        now: The time of the check. Defaults to the current time.

    Returns:
        Whether every list was fetched and read as a trusted list.
    """
    moment = (now or datetime.now(UTC)).replace(microsecond=0)
    reports.mkdir(parents=True, exist_ok=True)
    outcomes = []
    for name, url in LISTS.items():
        try:
            changed = _check(name, url, archive / name, reports, fetch, moment)
            outcomes.append(f"{name} {'changed' if changed else 'unchanged'}")
        except Exception as error:  # noqa: BLE001 - one list failing must not hide the other
            print(f"{name}: {error}", file=sys.stderr)
            outcomes.append(f"{name} failed")
            failed = {"checked": moment.strftime("%Y-%m-%dT%H:%M:%SZ"), "error": str(error)}
            _log(archive / name, failed)
    summary = f"{moment.date().isoformat()}: " + ", ".join(outcomes)
    (reports / "summary.txt").write_text(summary + "\n")
    print(summary)
    return not any(outcome.endswith("failed") for outcome in outcomes)


def _check(
    name: str, url: str, directory: Path, reports: Path, fetch: Fetch, moment: datetime
) -> bool:
    """Check one list. Return whether a new version was archived.

    Raises:
        ValueError: The response is not a trusted list. A response that begins
            as one but cannot be read in full is archived first.
    """
    response = fetch(url)
    if b"TrustServiceStatusList" not in response.data[:2000]:
        raise ValueError("the response is not a trusted list")
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(response.data).hexdigest()
    earlier = sidecars(directory)
    previous = earlier[-1]["sha256"] if earlier else None
    changed = previous != digest
    stamp = moment.strftime("%Y-%m-%dT%H%M%SZ")
    retrieved = moment.strftime("%Y-%m-%dT%H:%M:%SZ")
    if changed:
        (directory / f"{stamp}.xml").write_bytes(response.data)
        sidecar = {
            "list": name,
            "url": url,
            "retrieved": retrieved,
            "sha256": digest,
            "bytes": len(response.data),
            "last_modified": response.last_modified,
            "etag": response.etag,
            "content_type": response.content_type,
            "previous_sha256": previous,
            "repository": os.environ.get("GITHUB_REPOSITORY"),
            "commit": os.environ.get("GITHUB_SHA"),
            "run": os.environ.get("GITHUB_RUN_ID"),
        }
        (directory / f"{stamp}.json").write_text(json.dumps(sidecar, indent=2) + "\n")
    line = {
        "checked": retrieved,
        "sha256": digest,
        "last_modified": response.last_modified,
        "etag": response.etag,
        "changed": changed,
    }
    _log(directory, line)
    if changed:
        (reports / f"{name}.md").write_text(_report(name, directory))
    return changed


def _log(directory: Path, line: Mapping[str, object]) -> None:
    """Append one line to a list's check log."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "checks.jsonl").open("a") as log:
        log.write(json.dumps(line) + "\n")


def _report(name: str, directory: Path) -> str:
    """Describe the newest archived version of a list against the one before it.

    Raises:
        ValueError: An archived version cannot be read as a trusted list.
    """
    archived = versions(directory)
    newest = archived[-1]
    content = newest.content
    lines = [
        f"{name} list: sequence {content.sequence}, issued {content.issued}",
        "",
        f"- Address: {newest.sidecar['url']}",
        f"- Retrieved: {newest.sidecar['retrieved']}",
        f"- File: `{name}/{newest.file}`",
        f"- SHA-256: `{newest.sidecar['sha256']}`",
        f"- Sequence number: {content.sequence}",
        f"- Issued: {content.issued}",
        f"- Next update: {content.next_update}",
        f"- Signing time: {content.signing_time}",
        "",
    ]
    if len(archived) == 1:
        lines.append("First archived version.")
    else:
        before = archived[-2].content
        lines.append(
            f"Previous version: sequence {before.sequence}, issued {before.issued}, "
            f"SHA-256 `{archived[-2].sidecar['sha256']}`."
        )
        lines.append("")
        changes = events(before, content)
        lines += [f"- {e.country}, {e.service}: {e.change}" for e in changes]
        if not changes:
            lines.append("No service was added, removed or changed.")
    return "\n".join(lines) + "\n"
