"""Build the static page from the archive."""

import html
import json
from datetime import UTC, date, datetime
from importlib import resources
from pathlib import Path
from typing import Any

from av_trusted_lists.archive import LISTS, Version, checks, events, versions
from av_trusted_lists.lists import Service

_LABEL = {"production": "Trusted list", "acceptance": "Test list"}
_ACTIVE = "recognized"


def build(archive: Path, out: Path, today: date | None = None) -> None:
    """Write ``index.html`` and ``data.json`` to ``out``.

    Args:
        archive: The archive directory.
        out: Directory the page is written to. Created if absent.
        today: The build date. Defaults to the current UTC date.

    Raises:
        ValueError: An archived version cannot be read as a trusted list.
    """
    built = (today or datetime.now(UTC).date()).isoformat()
    data = resources.files("av_trusted_lists") / "data"
    basemap = json.loads((data / "basemap.json").read_text(encoding="utf-8"))
    template = (data / "template.html").read_text(encoding="utf-8")
    names = {code: country["name"] for code, country in basemap["countries"].items()}

    lists: dict[str, dict[str, Any]] = {}
    for name in LISTS:
        archived = versions(archive / name)
        lists[name] = {
            "label": _LABEL[name],
            "versions": archived,
            "checks": checks(archive / name),
            "first_capture": archived[0].captured if archived else "",
            "countries": _countries(archived, built),
        }

    active = {
        name: {code for code, entry in lists[name]["countries"].items() if entry["active"]}
        for name in LISTS
    }
    fills = {code: "prod" for code in active["production"]}
    fills |= {code: "test" for code in active["acceptance"] - active["production"]}
    listed = {code for name in LISTS for code in lists[name]["countries"]}
    page_data = {
        "names": names,
        "lists": {
            name: {key: lists[name][key] for key in ("label", "first_capture", "countries")}
            for name in LISTS
        },
    }
    replacements = {
        "{{DEFS}}": _defs(basemap),
        "{{MAP}}": _map(basemap, fills, listed),
        "{{ROWS}}": _rows(lists, names),
        "{{EVENTS}}": _events(lists, names),
        "{{FACTS}}": "".join(_facts(lists[name]) for name in LISTS),
        "{{BUILT}}": built,
        # "<" is written as an escape so no list text can end or alter the script element.
        "{{DATA}}": json.dumps(page_data, ensure_ascii=False, separators=(",", ":")).replace(
            "<", "\\u003c"
        ),
    }
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(template, encoding="utf-8")
    export = {"built": built, "lists": page_data["lists"]}
    (out / "data.json").write_text(json.dumps(export, ensure_ascii=False, indent=1) + "\n")


def _countries(archived: list[Version], built: str) -> dict[str, dict[str, Any]]:
    """Describe each country in the newest version, with dates from the archive.

    ``first_seen`` is the date of the oldest archived version a service is in.
    ``last_change`` is the date of the newest archived version in which the
    country's services differ from the version before it.
    """
    first_seen: dict[tuple[str, str], str] = {}
    last_change: dict[str, str] = {}
    previous: dict[str, set[tuple[Any, ...]]] = {}
    for version in archived:
        current: dict[str, set[tuple[Any, ...]]] = {}
        for service in version.content.services:
            first_seen.setdefault((service.country, service.name), version.captured)
            current.setdefault(service.country, set()).add(_state(service))
        for country in current.keys() | previous.keys():
            if current.get(country) != previous.get(country):
                last_change[country] = version.captured
        previous = current
    out: dict[str, dict[str, Any]] = {}
    for service in archived[-1].content.services if archived else ():
        entry = out.setdefault(
            service.country,
            {"services": [], "last_change": last_change[service.country], "active": False},
        )
        entry["active"] = entry["active"] or service.current.status == _ACTIVE
        entry["services"].append(
            {
                "provider": service.provider,
                "name": service.name,
                "status": service.current.status,
                "since": service.current.since,
                "first_seen": first_seen[(service.country, service.name)],
                "certificates": [
                    {
                        "not_before": certificate.not_before,
                        "not_after": certificate.not_after,
                        "expired": certificate.not_after < built,
                    }
                    for certificate in service.certificates
                ],
            }
        )
    return out


def _state(service: Service) -> tuple[Any, ...]:
    """Return what a change to a service would alter."""
    fingerprints = tuple(certificate.sha256 for certificate in service.certificates)
    return service.name, service.current.status, service.current.since, fingerprints


def _defs(basemap: dict[str, Any]) -> str:
    """Return a hidden SVG that defines one path per country."""
    paths = "".join(
        f'<path id="c-{code}" d="{country["d"]}"/>'
        for code, country in basemap["countries"].items()
    )
    return (
        '<svg width="0" height="0" style="position:absolute" aria-hidden="true">'
        f"<defs>{paths}</defs></svg>"
    )


def _map(basemap: dict[str, Any], fills: dict[str, str], listed: set[str]) -> str:
    """Return the map. A country is selectable when it is an EU member state or is listed."""
    eu27 = set(basemap["eu27"])
    layers: dict[str, list[str]] = {"ctx": [], "eu": [], "on": []}
    for code, country in basemap["countries"].items():
        if code in fills:
            layer, css = "on", fills[code]
        elif code in eu27:
            layer, css = "eu", "eu"
        else:
            layer, css = "ctx", "ctx"
        select = f' data-cc="{code}"' if code in eu27 or code in listed else ""
        title = html.escape(country["name"])
        layers[layer].append(
            f'<use href="#c-{code}" class="{css}"{select}><title>{title}</title></use>'
        )
    body = "".join("".join(layers[layer]) for layer in ("ctx", "eu", "on"))
    return (
        f'<svg class="map" viewBox="0 0 {basemap["width"]:.0f} {basemap["height"]:.0f}" '
        'role="img" aria-label="Map of Europe, countries coloured by list">'
        f'{body}<use class="outline"/></svg>'
    )


def _rows(lists: dict[str, dict[str, Any]], names: dict[str, str]) -> str:
    """Return the table rows: one per certificate of each service of each list."""
    codes = sorted(
        {code for entry in lists.values() for code in entry["countries"]},
        key=lambda code: names.get(code, code),
    )
    rows = []
    for code in codes:
        for entry in lists.values():
            for service in entry["countries"].get(code, {"services": []})["services"]:
                for certificate in service["certificates"] or [None]:
                    start, end, state = "", "", ""
                    if certificate:
                        start, end = certificate["not_before"], certificate["not_after"]
                        state = "expired" if certificate["expired"] else "valid"
                    cells = [
                        (names.get(code, code), ""),
                        (entry["label"], " class=nw"),
                        (service["provider"], ""),
                        (service["name"], ""),
                        (service["status"], ""),
                        (service["since"][:10], " class=nw"),
                        (start, " class=nw"),
                        (end, " class=nw"),
                        (state, ""),
                    ]
                    rows.append(
                        "<tr>"
                        + "".join(f"<td{css}>{html.escape(text)}</td>" for text, css in cells)
                        + "</tr>"
                    )
    return "\n".join(rows)


def _events(lists: dict[str, dict[str, Any]], names: dict[str, str]) -> str:
    """Return the differences between consecutive archived versions, newest first."""
    items = []
    for entry in lists.values():
        archived: list[Version] = entry["versions"]
        for before, after in zip(archived, archived[1:], strict=False):
            for event in events(before.content, after.content):
                text = (
                    f"{after.captured}, {entry['label'].lower()}: "
                    f"{names.get(event.country, event.country)}, {event.service}, {event.change}"
                )
                items.append((after.captured, f"<li>{html.escape(text)}</li>"))
    if not items:
        return "<p>No change between archived versions.</p>"
    items.sort(key=lambda item: item[0], reverse=True)
    return "<ul>" + "".join(item for _, item in items) + "</ul>"


def _facts(entry: dict[str, Any]) -> str:
    """Return the table of list-level facts for the newest version of one list."""
    archived: list[Version] = entry["versions"]
    if not archived:
        return f"<h3>{entry['label']}</h3><p>No archived version.</p>"
    newest = archived[-1]
    log = [line for line in entry["checks"] if "error" not in line]
    rows = [
        ("Address", newest.sidecar["url"]),
        ("Scheme name", newest.content.scheme_name),
        ("Sequence number", newest.content.sequence),
        ("Issued", newest.content.issued),
        ("Next update", newest.content.next_update),
        ("Signing time", newest.content.signing_time),
        ("Signer", newest.content.signer),
        ("Signature", "not verified by this site"),
        ("SHA-256", newest.sidecar["sha256"]),
        ("This version first retrieved", newest.sidecar["retrieved"]),
        ("Versions in the archive", str(len(archived))),
        ("Last checked", log[-1]["checked"] if log else "no check recorded"),
    ]
    body = "".join(
        f"<tr><th>{html.escape(key)}</th><td>{html.escape(value)}</td></tr>" for key, value in rows
    )
    return f"<h3>{entry['label']}</h3><table class='facts'>{body}</table>"
