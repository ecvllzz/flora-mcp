import runpy
import ssl
from pathlib import Path
from urllib.error import URLError

import pytest

CHECK = runpy.run_path(str(Path(__file__).resolve().parents[1] / "deploy/render/verify_tls.py"))


@pytest.mark.parametrize("status", [200, 403, 500])
def test_any_http_response_from_compromised_chain_is_rejected(status):
    with pytest.raises(RuntimeError, match="Unsafe certificate accepted"):
        CHECK["check_client"]("test", lambda url: status)


@pytest.mark.parametrize("error", [TimeoutError(), URLError("DNS failure")])
def test_network_failure_is_inconclusive(error):
    def get(url):
        if url == "https://github.com/":
            return 200
        raise error

    with pytest.raises(RuntimeError, match="inconclusive"):
        CHECK["check_client"]("test", get)


def test_both_chains_must_fail_certificate_verification():
    visited = []

    def get(url):
        visited.append(url)
        if url == "https://github.com/":
            return 200
        raise URLError(ssl.SSLCertVerificationError("untrusted certificate"))

    CHECK["check_client"]("test", get)
    assert visited == ["https://github.com/", *[f"https://{host}/" for host in CHECK["TEST_HOSTS"]]]
