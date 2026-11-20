import base64
import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from xml.etree import ElementTree
from xml.sax.saxutils import escape

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

NAMESPACE = "http://uri.etsi.org/02231/v2#"
PROVIDER_ADDRESS = "https://trust.tech.ec.europa.eu/lists/age-verification/paap/"
SERVICE_TYPE = "http://uri.etsi.org/TrstSvc/Svctype/Provider/AVProvider"
STATUS = "http://uri.etsi.org/TrstSvc/TrustedList/Svcstatus/"

Names = Sequence[tuple[str | None, str]]


def certificate(
    subject: str = "Example AV Provider",
    *,
    not_before: date = date(2026, 1, 1),
    not_after: date = date(2030, 1, 1),
) -> str:
    """Return a new self-signed certificate as base64 DER."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject)])
    built = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.combine(not_before, datetime.min.time(), UTC))
        .not_valid_after(datetime.combine(not_after, datetime.min.time(), UTC))
        .sign(key, hashes.SHA256())
    )
    return base64.b64encode(built.public_bytes(serialization.Encoding.DER)).decode()


def fingerprint(encoded: str) -> str:
    """Return the SHA-256 fingerprint of a base64 DER certificate as lowercase hex."""
    loaded = x509.load_der_x509_certificate(base64.b64decode(encoded))
    return loaded.fingerprint(hashes.SHA256()).hex()


def names_xml(names: Names) -> str:
    """Render Name elements, each with its xml:lang when the pair names one."""
    return "".join(
        f'<Name xml:lang="{lang}">{escape(text)}</Name>' if lang else f"<Name>{escape(text)}</Name>"
        for lang, text in names
    )


def service_xml(
    *,
    names: Names = (("en", "Age check"),),
    type_uri: str = SERVICE_TYPE,
    status: str = "recognized",
    since: str = "2026-01-05T00:00:00Z",
    certificates: Sequence[str] = (),
    history: Sequence[tuple[str, str]] = (),
) -> str:
    """Render one TSPService element."""
    identities = "".join(
        f"<DigitalId><X509Certificate>{encoded}</X509Certificate></DigitalId>"
        for encoded in certificates
    )
    instances = "".join(
        "<ServiceHistoryInstance>"
        f"<ServiceStatus>{STATUS}{was}</ServiceStatus>"
        f"<StatusStartingTime>{when}</StatusStartingTime>"
        "</ServiceHistoryInstance>"
        for was, when in history
    )
    return (
        "<TSPService>"
        "<ServiceInformation>"
        f"<ServiceTypeIdentifier>{type_uri}</ServiceTypeIdentifier>"
        f"<ServiceName>{names_xml(names)}</ServiceName>"
        f"<ServiceDigitalIdentity>{identities}</ServiceDigitalIdentity>"
        f"<ServiceStatus>{STATUS}{status}</ServiceStatus>"
        f"<StatusStartingTime>{since}</StatusStartingTime>"
        "</ServiceInformation>"
        f"<ServiceHistory>{instances}</ServiceHistory>"
        "</TSPService>"
    )


def provider_xml(
    *services: str,
    country: str = "FI",
    names: Names = (("en", "Example Provider"),),
    addresses: Sequence[str] | None = None,
) -> str:
    """Render one TrustServiceProvider, addressed under the provider path of its country."""
    uris = (PROVIDER_ADDRESS + country,) if addresses is None else addresses
    listed = "".join(f'<URI xml:lang="en">{escape(uri)}</URI>' for uri in uris)
    return (
        "<TrustServiceProvider>"
        "<TSPInformation>"
        f"<TSPName>{names_xml(names)}</TSPName>"
        f"<TSPInformationURI>{listed}</TSPInformationURI>"
        "</TSPInformation>"
        f"<TSPServices>{''.join(services)}</TSPServices>"
        "</TrustServiceProvider>"
    )


def list_xml(
    *providers: str,
    sequence: str = "4",
    issued: str = "2026-11-01T00:00:00Z",
    next_update: str = "2027-05-01T00:00:00Z",
    scheme: Names = (("en", "EU age-verification trusted list"),),
    signing_time: str = "2026-11-01T06:00:00Z",
    signer: str | None = None,
    namespace: str | None = NAMESPACE,
) -> bytes:
    """Render a trusted list document."""
    xmlns = f' xmlns="{namespace}"' if namespace else ""
    signing_certificate = certificate("EU Trusted List Signer") if signer is None else signer
    return (
        f"<TrustServiceStatusList{xmlns}>"
        "<SchemeInformation>"
        f"<TSLSequenceNumber>{sequence}</TSLSequenceNumber>"
        f"<SchemeName>{names_xml(scheme)}</SchemeName>"
        f"<ListIssueDateTime>{issued}</ListIssueDateTime>"
        f"<NextUpdate><dateTime>{next_update}</dateTime></NextUpdate>"
        "</SchemeInformation>"
        f"<TrustServiceProviderList>{''.join(providers)}</TrustServiceProviderList>"
        "<Signature>"
        f"<X509Certificate>{signing_certificate}</X509Certificate>"
        f"<SigningTime>{signing_time}</SigningTime>"
        "</Signature>"
        "</TrustServiceStatusList>"
    ).encode()


def without(data: bytes, name: str) -> bytes:
    """Return the document with the first element of that local name removed."""
    root = ElementTree.fromstring(data)
    for parent in root.iter():
        for child in parent:
            if child.tag.rsplit("}", 1)[-1] == name:
                parent.remove(child)
                return ElementTree.tostring(root)
    raise AssertionError(f"the document has no {name} element to remove")


def archived(
    directory: Path,
    data: bytes,
    retrieved: str,
    *,
    url: str = "https://trust.tech.ec.europa.eu/lists/age-verification/av-tl.xml",
) -> None:
    """Write one archived version of a list and its sidecar into the list's directory."""
    directory.mkdir(parents=True, exist_ok=True)
    stamp = retrieved.replace(":", "")
    (directory / f"{stamp}.xml").write_bytes(data)
    sidecar = {
        "list": directory.name,
        "url": url,
        "retrieved": retrieved,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }
    (directory / f"{stamp}.json").write_text(json.dumps(sidecar, indent=2) + "\n")
