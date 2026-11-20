"""The archive directory: one subdirectory per list.

    <list>/<retrieved>.xml     a version of the list, the bytes as served
    <list>/<retrieved>.json    its sidecar, the facts of the retrieval
    <list>/checks.jsonl        one line per check, changed or not

``<retrieved>`` is the retrieval time as ``YYYY-MM-DDTHHMMSSZ``, so names sort by time.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from av_trusted_lists.lists import Service, TrustedList, parse

LISTS = {
    "production": "https://trust.tech.ec.europa.eu/lists/age-verification/av-tl.xml",
    "acceptance": "https://acceptance.trust.tech.ec.europa.eu/lists/age-verification/av-tl.xml",
}


@dataclass(frozen=True)
class Version:
    """One archived version of a list.

    Attributes:
        file: Name of the XML file within the list's directory.
        sidecar: The sidecar as written at retrieval.
        content: What the version states.
    """

    file: str
    sidecar: dict[str, Any]
    content: TrustedList

    @property
    def captured(self) -> str:
        """The UTC date the version was retrieved."""
        return str(self.sidecar["retrieved"])[:10]


@dataclass(frozen=True)
class Event:
    """A difference between two consecutive versions of a list.

    Attributes:
        country: The provider's country code.
        service: The service name.
        change: What changed, e.g. ``added`` or ``status recognized to deprecated``.
    """

    country: str
    service: str
    change: str


def sidecars(directory: Path) -> list[dict[str, Any]]:
    """Return the sidecars in a list's directory, oldest first."""
    return [json.loads(path.read_text()) for path in sorted(directory.glob("*.json"))]


def versions(directory: Path) -> list[Version]:
    """Read every archived version in a list's directory, oldest first.

    Raises:
        ValueError: An archived file cannot be read as a trusted list.
    """
    out = []
    for path in sorted(directory.glob("*.json")):
        xml = path.with_suffix(".xml")
        out.append(Version(xml.name, json.loads(path.read_text()), parse(xml.read_bytes())))
    return out


def checks(directory: Path) -> list[dict[str, Any]]:
    """Return the check log of a list's directory, oldest first."""
    log = directory / "checks.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines()]


def events(before: TrustedList, after: TrustedList) -> list[Event]:
    """List the differences between two versions of a list.

    A service is identified by its country and name. A service present in both
    versions yields at most one event: a status change, else a certificate
    replacement, else a changed status time.
    """
    old = {_key(service): service for service in before.services}
    new = {_key(service): service for service in after.services}
    out = [Event(*key, "added") for key in sorted(new.keys() - old.keys())]
    out += [Event(*key, "removed") for key in sorted(old.keys() - new.keys())]
    for key in sorted(new.keys() & old.keys()):
        was, now = old[key], new[key]
        if was.current.status != now.current.status:
            change = f"status {was.current.status} to {now.current.status}"
        elif _fingerprints(was) != _fingerprints(now):
            change = "certificate replaced"
        elif was.current.since != now.current.since:
            change = "status time changed"
        else:
            continue
        out.append(Event(*key, change))
    return out


def _key(service: Service) -> tuple[str, str]:
    """Return what identifies a service across versions."""
    return service.country, service.name


def _fingerprints(service: Service) -> tuple[str, ...]:
    """Return the fingerprints of a service's certificates."""
    return tuple(certificate.sha256 for certificate in service.certificates)
