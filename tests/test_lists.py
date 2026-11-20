from datetime import date

import pytest

from av_trusted_lists.lists import Status, parse
from tests.conftest import (
    PROVIDER_ADDRESS,
    certificate,
    fingerprint,
    list_xml,
    provider_xml,
    service_xml,
    without,
)

REQUIRED = (
    "SchemeInformation",
    "TSLSequenceNumber",
    "SchemeName",
    "ListIssueDateTime",
    "NextUpdate",
    "dateTime",
    "TSPInformation",
    "TSPName",
    "TSPInformationURI",
    "ServiceInformation",
    "ServiceTypeIdentifier",
    "ServiceName",
    "ServiceDigitalIdentity",
    "ServiceStatus",
    "StatusStartingTime",
    "Signature",
    "SigningTime",
)
COUNTRIES = (
    ("FI", "FI"),
    ("EL", "GR"),
    ("UK", "GB"),
)

REQUIRED_PARAMS = [pytest.param(name, id=f"{name}-absent") for name in REQUIRED]
COUNTRY_PARAMS = [
    pytest.param(listed, expected, id=f"{listed}-country-{expected}")
    for listed, expected in COUNTRIES
]


def test_list_fields_read() -> None:
    signer = certificate("EU Trusted List Signer")
    data = list_xml(
        provider_xml(service_xml()),
        sequence="12",
        issued="2026-11-01T00:00:00Z",
        next_update="2027-05-01T00:00:00Z",
        scheme=(("en", "EU age-verification trusted list"),),
        signing_time="2026-11-01T06:00:00Z",
        signer=signer,
    )
    listed = parse(data)
    assert listed.sequence == "12"
    assert listed.issued == "2026-11-01T00:00:00Z"
    assert listed.next_update == "2027-05-01T00:00:00Z"
    assert listed.scheme_name == "EU age-verification trusted list"
    assert listed.signing_time == "2026-11-01T06:00:00Z"
    assert listed.signer == "CN=EU Trusted List Signer"


def test_service_fields_read() -> None:
    data = list_xml(
        provider_xml(
            service_xml(
                names=(("en", "Age check"),),
                type_uri="http://uri.etsi.org/TrstSvc/Svctype/Provider/AVProvider",
                status="recognized",
                since="2026-01-05T00:00:00Z",
            ),
            country="FI",
            names=(("en", "Example Provider"),),
        )
    )
    service = parse(data).services[0]
    assert service.country == "FI"
    assert service.provider == "Example Provider"
    assert service.name == "Age check"
    assert service.type == "AVProvider"
    assert service.current == Status("recognized", "2026-01-05T00:00:00Z")


def test_certificate_fields_read() -> None:
    encoded = certificate(
        "Example AV Provider", not_before=date(2026, 2, 3), not_after=date(2029, 4, 5)
    )
    data = list_xml(provider_xml(service_xml(certificates=(encoded,))))
    listed = parse(data).services[0].certificates[0]
    assert listed.sha256 == fingerprint(encoded)
    assert listed.subject == "CN=Example AV Provider"
    assert listed.not_before == "2026-02-03"
    assert listed.not_after == "2029-04-05"


def test_certificates_listed() -> None:
    first = certificate("First AV Provider")
    second = certificate("Second AV Provider")
    data = list_xml(provider_xml(service_xml(certificates=(first, second))))
    listed = parse(data).services[0].certificates
    assert {entry.sha256 for entry in listed} == {fingerprint(first), fingerprint(second)}


def test_certificates_absent() -> None:
    data = list_xml(provider_xml(service_xml(certificates=())))
    assert parse(data).services[0].certificates == ()


def test_services_of_every_provider() -> None:
    data = list_xml(
        provider_xml(
            service_xml(names=(("en", "Age check"),)),
            service_xml(names=(("en", "Second check"),)),
            country="FI",
        ),
        provider_xml(service_xml(names=(("en", "Idade"),)), country="PT"),
    )
    listed = parse(data).services
    assert [(service.country, service.name) for service in listed] == [
        ("FI", "Age check"),
        ("FI", "Second check"),
        ("PT", "Idade"),
    ]


def test_english_name_preferred() -> None:
    data = list_xml(
        provider_xml(
            service_xml(names=(("fi", "Ikätarkistus"), ("en", "Age check"))),
            names=(("fi", "Esimerkki"), ("en", "Example Provider")),
        ),
        scheme=(("fi", "Luottamuslista"), ("en", "Trusted list")),
    )
    listed = parse(data)
    assert listed.scheme_name == "Trusted list"
    assert listed.services[0].provider == "Example Provider"
    assert listed.services[0].name == "Age check"


def test_first_name_used_without_english() -> None:
    data = list_xml(
        provider_xml(
            service_xml(names=(("fi", "Ikätarkistus"), ("sv", "Ålderskontroll"))),
            names=((None, "Esimerkki"), ("sv", "Exempel")),
        ),
        scheme=(("fi", "Luottamuslista"), ("sv", "Förtroendelista")),
    )
    listed = parse(data)
    assert listed.scheme_name == "Luottamuslista"
    assert listed.services[0].provider == "Esimerkki"
    assert listed.services[0].name == "Ikätarkistus"


@pytest.mark.parametrize(("listed", "expected"), COUNTRY_PARAMS)
def test_country_from_provider_address(listed: str, expected: str) -> None:
    data = list_xml(provider_xml(service_xml(), country=listed))
    assert parse(data).services[0].country == expected


def test_country_from_provider_address_among_others() -> None:
    data = list_xml(
        provider_xml(
            service_xml(),
            addresses=("https://example.test/about", PROVIDER_ADDRESS + "PT"),
        )
    )
    assert parse(data).services[0].country == "PT"


def test_provider_without_provider_address_rejected() -> None:
    data = list_xml(provider_xml(service_xml(), addresses=("https://example.test/about",)))
    with pytest.raises(ValueError):
        parse(data)


def test_status_and_type_from_last_uri_segment() -> None:
    data = list_xml(
        provider_xml(
            service_xml(
                type_uri="http://uri.etsi.org/TrstSvc/Svctype/Provider/AVProvider",
                status="withdrawn",
            )
        )
    )
    service = parse(data).services[0]
    assert service.type == "AVProvider"
    assert service.current.status == "withdrawn"


def test_history_oldest_first() -> None:
    data = list_xml(
        provider_xml(
            service_xml(
                history=(
                    ("withdrawn", "2026-03-01T00:00:00Z"),
                    ("recognized", "2026-01-05T00:00:00Z"),
                    ("granted", "2026-02-01T00:00:00Z"),
                )
            )
        )
    )
    assert parse(data).services[0].history == (
        Status("recognized", "2026-01-05T00:00:00Z"),
        Status("granted", "2026-02-01T00:00:00Z"),
        Status("withdrawn", "2026-03-01T00:00:00Z"),
    )


def test_history_absent() -> None:
    data = list_xml(provider_xml(service_xml(history=())))
    assert parse(data).services[0].history == ()


def test_undeclared_namespace_read() -> None:
    data = list_xml(provider_xml(service_xml()), namespace=None)
    listed = parse(data)
    assert listed.sequence == "4"
    assert listed.services[0].country == "FI"


def test_non_list_root_rejected() -> None:
    with pytest.raises(ValueError):
        parse(b'<TrustStatusList xmlns="http://uri.etsi.org/02231/v2#"></TrustStatusList>')


@pytest.mark.parametrize("name", REQUIRED_PARAMS)
def test_required_element_absent_rejected(name: str) -> None:
    data = list_xml(provider_xml(service_xml(certificates=(certificate(),))))
    with pytest.raises(ValueError):
        parse(without(data, name))


def test_malformed_xml_rejected() -> None:
    data = list_xml(provider_xml(service_xml()))
    with pytest.raises(ValueError):
        parse(data[:200])


def test_name_element_absent_rejected() -> None:
    data = list_xml(provider_xml(service_xml()))
    with pytest.raises(ValueError):
        parse(without(data, "Name"))
