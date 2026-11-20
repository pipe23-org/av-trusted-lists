# av-trusted-lists

av-trusted-lists archives the two age-verification trusted lists the European Commission
publishes and builds a static page of providers by country from the archive. The project is
independent of the European Commission. It is experimental and unstable.

[![CI](https://github.com/pipe23-org/av-trusted-lists/actions/workflows/ci.yml/badge.svg)](https://github.com/pipe23-org/av-trusted-lists/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

## Usage

The commands run from a checkout under `uv run`. `watch` fetches both lists and archives a
list whose bytes differ from its newest archived version. Every check appends one line to the
list's `checks.jsonl`. A changed list gets a report at `<reports>/<list>.md`, and
`<reports>/summary.txt` gets the line the command prints. `--reports` names the directory the
reports are written to, `reports` by default. The exit status is 1 when a list could not be
fetched or read as a trusted list. `build` writes the page from the archive.

```
$ uv run av-trusted-lists watch archive --reports reports
2026-11-20: production changed, acceptance changed
$ uv run av-trusted-lists watch archive --reports reports
2026-11-20: production unchanged, acceptance unchanged
$ uv run av-trusted-lists build archive site
$ ls site
data.json  index.html
```

The report from the first check begins:

```
production list: sequence 5, issued 2026-11-05T16:00:00Z

- Address: https://trust.tech.ec.europa.eu/lists/age-verification/av-tl.xml
- Retrieved: 2026-11-20T11:43:16Z
- File: `production/2026-11-20T114316Z.xml`
```

## Lists

The Age Verification Trusted List is archived as `production`:
<https://trust.tech.ec.europa.eu/lists/age-verification/av-tl.xml>

Its test list is archived as `acceptance`:
<https://acceptance.trust.tech.ec.europa.eu/lists/age-verification/av-tl.xml>

Both are ETSI TS 119 612 trusted lists with the additional requirements of the Commission's
"AV Trusted List Specifications". A list names the Proof of Age Attestation Providers that EU
member states have notified to the Commission. A provider has one or more Proof of Age
Services on a list. A service has a status and the certificates the list gives for it.

The lists are the European Commission's, reused under CC BY 4.0 as the Commission's
[legal notice](https://commission.europa.eu/legal-notice_en) provides.

## Archive

The archive directory holds one subdirectory per list.

```
<list>/<retrieved>.xml     a version of the list, the bytes as served
<list>/<retrieved>.json    its sidecar, the facts of the retrieval
<list>/checks.jsonl        one line per check, changed or not
```

`<retrieved>` is the retrieval time as `YYYY-MM-DDTHHMMSSZ`, so names sort by time.

A sidecar holds `list`, `url`, `retrieved`, `sha256`, `bytes`, `last_modified`, `etag`,
`content_type`, `previous_sha256`, `repository`, `commit` and `run`. A line in `checks.jsonl`
holds `checked`, `sha256`, `last_modified`, `etag` and `changed`. The line of a failed check
holds `checked` and `error`.

## Page

`build` writes `index.html` and `data.json` to its output directory. `index.html` carries its
CSS, its SVG map and its script inline, and a browser renders the page from that one file.

The map of Europe colours a country with a recognized provider on the trusted list, a country
with a recognized provider on the test list only, and an EU member state on neither. A table
lists every service in the newest version of each list. A list of changes gives the differences between consecutive archived versions. A table of list facts
gives the address, scheme name, sequence number, issue time, next update, signing time,
signer and SHA-256 of each list's newest version.

`data.json` holds `built` and `lists`. Each entry under `lists` holds `label`, `first_capture`
and `countries`.

The country outlines and country names come from `src/av_trusted_lists/data/basemap.json`.
`tools/bake_map.py` regenerates that file from the Natural Earth 1:50m "Admin 0 - Countries"
GeoJSON, which is public domain.

## Nightly workflow

The `nightly` workflow runs at 04:23 UTC and on manual dispatch. The archive is the `archive`
branch, which the first run creates. Each check is committed to it. A changed list gets a
comment on the open issue labelled `list-change`. The workflow opens that issue when none is
open. The workflow builds the page and uploads it as the `page` workflow artifact.

## Configuration

`DEPLOY_PAGES` is a repository variable, unset by default. The `nightly` workflow deploys the
page to GitHub Pages when its value is `true`.

## Development

```
uv sync
uv run pytest --cov
uv run ruff check
uv run ruff format --check
uv run mypy
```

## Status

You should not rely on this code.

- The XML signature of a list is not verified.
- The archive begins at the project's first capture.
- Versions of the lists published before that capture are absent from it.
- A service is identified across versions by its country and its name, so a renamed service
  appears as one removed and one added.
- The map omits overseas territories.

## License

The code is Apache-2.0.
