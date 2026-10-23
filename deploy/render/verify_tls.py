"""Fail the image build unless both HTTP clients reject the eMudhra test chains."""

import ssl
from importlib.metadata import version
from urllib.error import HTTPError
from urllib.request import urlopen

import httpx

TEST_HOSTS = (
    "dv-g3b-emudhra.we-have-a-problem.com",
    "dv-g3b-aaa-emudhra.we-have-a-problem.com",
)


def certificate_error(error):
    """Network/DNS failures must not count as evidence of certificate rejection."""
    seen = set()
    while isinstance(error, BaseException) and id(error) not in seen:
        if isinstance(error, ssl.SSLCertVerificationError):
            return True
        seen.add(id(error))
        error = getattr(error, "reason", None) or error.__cause__ or error.__context__
    return False


def urllib_get(url):
    try:
        with urlopen(url, timeout=20) as response:
            return response.status
    except HTTPError as error:
        return error.code


def check_client(name, get):
    # A valid control must work: a broken network is not a successful TLS test.
    get("https://github.com/")
    for host in TEST_HOSTS:
        try:
            get(f"https://{host}/")
        except Exception as error:
            if not certificate_error(error):
                raise RuntimeError(f"TLS check inconclusive: {name} {host}") from error
        else:
            raise RuntimeError(f"Unsafe certificate accepted: {name} {host}")
        print(f"TLS verified: {name} rejected {host}", flush=True)


def main():
    certifi_version = version("certifi")
    if tuple(map(int, certifi_version.split("."))) < (2026, 10, 19):
        raise RuntimeError("Certifi is older than the required security release")
    print(f"TLS packages: certifi={certifi_version} httpx={version('httpx')}", flush=True)
    check_client("urllib/system", urllib_get)
    with httpx.Client(timeout=20) as client:
        check_client("httpx", client.get)


if __name__ == "__main__":
    main()
