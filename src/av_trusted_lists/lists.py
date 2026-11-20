"""Read an EU age-verification trusted list.

The lists are ETSI TS 119 612 trusted lists with the additional requirements of the
Commission's "AV Trusted List Specifications". The list's signature is not verified here.
"""

import base64
from dataclasses import dataclass
from xml.etree import ElementTree
from xml.etree.ElementTree import Element

from cryptography import x509
from cryptography.hazmat.primitives import hashes

_XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
# The provider's country is the last segment of this address in its TSPInformationURI.
_PROVIDER_URI = "/lists/age-verification/paap/"
# ETSI TS 119 612 clause 5.1.5 uses these two codes where ISO 3166-1 has GR and GB.
_COUNTRY_ALIAS = {"EL": "GR", "UK": "GB"}


@dataclass(frozen=True)
class Certificate:
    """A certificate listed for a service.

    Attributes:
        sha256: SHA-256 fingerprint as lowercase hex.
        subject: Subject name in RFC 4514 form.
        not_before: First day of validity, as a UTC date.
        not_after: Last day of validity, as a UTC date.
    """

    sha256: str
    subject: str
    not_before: str
    not_after: str


@dataclass(frozen=True)
class Status:
    """A service status and the time the list states it began.

    Attributes:
        status: Last segment of the status URI, e.g. ``recognized``.
        since: The status starting time as the list writes it.
    """

    status: str
    since: str


@dataclass(frozen=True)
class Service:
    """One service of one provider.

    Attributes:
        country: ISO 3166-1 alpha-2 code of the member state the provider is established in.
        provider: Provider name, in English when the list has one.
        name: Service name, in English when the list has one.
        type: Last segment of the service type URI.
        current: The current status.
        certificates: The certificates under the service's digital identity.
        history: Earlier statuses the list records for the service, oldest first.
    """

    country: str
    provider: str
    name: str
    type: str
    current: Status
    certificates: tuple[Certificate, ...]
    history: tuple[Status, ...]


@dataclass(frozen=True)
class TrustedList:
    """What one version of a list states.

    Attributes:
        sequence: The TSL sequence number.
        issued: The list issue time as the list writes it.
        next_update: The next update time as the list writes it.
        scheme_name: The scheme name, in English when the list has one.
        signing_time: The signing time in the list's signature.
        signer: Subject name of the certificate in the list's signature.
        services: Every service of every provider.
    """

    sequence: str
    issued: str
    next_update: str
    scheme_name: str
    signing_time: str
    signer: str
    services: tuple[Service, ...]


def parse(data: bytes) -> TrustedList:
    """Read a trusted list from its XML bytes.

    Args:
        data: The list as served.

    Returns:
        The fields this project uses.

    Raises:
        ValueError: The document is not well-formed XML or not a trusted list,
            or a field this project reads is absent.
    """
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as error:
        raise ValueError(f"not well-formed XML: {error}") from error
    if _local(root.tag) != "TrustServiceStatusList":
        raise ValueError(f"root element is {_local(root.tag)}, not TrustServiceStatusList")
    scheme = _one(root, "SchemeInformation")
    signature = _one(root, "Signature")
    services = []
    for provider in _all(root, "TrustServiceProvider"):
        information = _one(provider, "TSPInformation")
        country = _country(information)
        provider_name = _english(_one(information, "TSPName"))
        for service in _all(provider, "TSPService"):
            services.append(_service(service, country, provider_name))
    return TrustedList(
        sequence=_text(_one(scheme, "TSLSequenceNumber")),
        issued=_text(_one(scheme, "ListIssueDateTime")),
        next_update=_text(_one(_one(scheme, "NextUpdate"), "dateTime")),
        scheme_name=_english(_one(scheme, "SchemeName")),
        signing_time=_text(_one(signature, "SigningTime")),
        signer=_certificate(_one(signature, "X509Certificate")).subject,
        services=tuple(services),
    )


def _service(service: Element, country: str, provider: str) -> Service:
    """Read one TSPService element."""
    information = _one(service, "ServiceInformation")
    identity = _one(information, "ServiceDigitalIdentity")
    history = [_status(instance) for instance in _all(service, "ServiceHistoryInstance")]
    return Service(
        country=country,
        provider=provider,
        name=_english(_one(information, "ServiceName")),
        type=_last_segment(_one(information, "ServiceTypeIdentifier")),
        current=_status(information),
        certificates=tuple(_certificate(c) for c in _all(identity, "X509Certificate")),
        history=tuple(sorted(history, key=lambda status: status.since)),
    )


def _status(element: Element) -> Status:
    """Read the status and its starting time from a service or history element."""
    return Status(
        status=_last_segment(_one(element, "ServiceStatus")),
        since=_text(_one(element, "StatusStartingTime")),
    )


def _country(information: Element) -> str:
    """Return the member state a provider's TSPInformationURI names."""
    for uri in _all(_one(information, "TSPInformationURI"), "URI"):
        address = _text(uri)
        if _PROVIDER_URI in address:
            code = address.rsplit("/", 1)[-1].upper()
            return _COUNTRY_ALIAS.get(code, code)
    raise ValueError("a provider has no age-verification provider address naming its country")


def _certificate(element: Element) -> Certificate:
    """Read a base64 X509Certificate element."""
    certificate = x509.load_der_x509_certificate(base64.b64decode(_text(element)))
    return Certificate(
        sha256=certificate.fingerprint(hashes.SHA256()).hex(),
        subject=certificate.subject.rfc4514_string(),
        not_before=certificate.not_valid_before_utc.date().isoformat(),
        not_after=certificate.not_valid_after_utc.date().isoformat(),
    )


def _english(container: Element) -> str:
    """Return the English Name under a multilingual element, or its first Name.

    Raises:
        ValueError: The element has no Name.
    """
    for name in _all(container, "Name"):
        if name.get(_XML_LANG) == "en":
            return _text(name)
    return _text(_one(container, "Name"))


def _local(tag: str) -> str:
    """Return an XML tag without its namespace."""
    return tag.rsplit("}", 1)[-1]


def _all(element: Element, name: str) -> list[Element]:
    """Return every descendant with the given local name."""
    return [e for e in element.iter() if _local(e.tag) == name]


def _one(element: Element, name: str) -> Element:
    """Return the first descendant with the given local name.

    Raises:
        ValueError: There is none.
    """
    found = _all(element, name)
    if not found:
        raise ValueError(f"{_local(element.tag)} has no {name}")
    return found[0]


def _text(element: Element) -> str:
    """Return an element's text with whitespace runs collapsed."""
    return " ".join((element.text or "").split())


def _last_segment(element: Element) -> str:
    """Return the last path segment of a URI-valued element."""
    return _text(element).rsplit("/", 1)[-1]
