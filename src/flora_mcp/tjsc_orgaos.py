"""TJSC organs by the exact name the portal uses in the selOrgao[] search filter.

The names were read from the portal search form on 30/09/2026 (fixture
tests/fixtures/tjsc/formulario-pesquisa.html). A numbered Civil Law Chamber keeps its original
dataset (tjsc-N-civil) and its window envelope keeps the chamber number, so windows collected
before organs were named still verify without migration.
"""

import re
import unicodedata

from bs4 import BeautifulSoup

from .model import FloraError

CIVIL = "{}ª Câmara de Direito Civil"
ESPECIAIS = tuple(f"{n}ª Câmara Especial de Enfrentamento de Acervos" for n in (1, 2, 3))
# Organs the collector accepts; a name outside the list would reach the portal as an unknown
# filter, whose answer cannot be told apart from a genuinely empty day.
ORGAOS = tuple(CIVIL.format(n) for n in range(1, 11)) + ESPECIAIS
# Atualizacao corrente: as dez Camaras de Direito Civil (decisao do operador de 30/09/2026). As
# Camaras Especiais de Enfrentamento de Acervos sao temporarias e entram so por coleta historica.
PADRAO = tuple(CIVIL.format(n) for n in range(1, 11))


def name(organ: int | str) -> str:
    """Portal name of an organ given by name or by Civil Law Chamber number."""
    value = CIVIL.format(organ) if isinstance(organ, int) else organ
    if value not in ORGAOS:
        raise FloraError("orgao_invalido", f"Órgão TJSC fora da lista do coletor: {organ}.")
    return value


def chamber(organ: int | str) -> int | None:
    """Number of a Civil Law Chamber; None for any other organ."""
    match = re.fullmatch(r"(\d+)ª Câmara de Direito Civil", name(organ))
    return int(match[1]) if match else None


def dataset(organ: int | str) -> str:
    """tjsc-N-civil for a numbered Civil Law Chamber; otherwise tjsc- and the folded name."""
    number = chamber(organ)
    if number is not None:
        return f"tjsc-{number}-civil"
    plain = unicodedata.normalize("NFKD", name(organ)).encode("ascii", "ignore").decode()
    return "tjsc-" + "-".join(re.findall(r"[a-z0-9]+", plain.lower()))


def identity(organ: int | str) -> dict:
    """Organ fields of a window envelope, event or resource: the name, and the chamber number."""
    number = chamber(organ)
    return {"orgao": name(organ), **({"camara": number} if number is not None else {})}


def envelope_organ(envelope: dict) -> str | None:
    """Organ of a stored window; envelopes from before named organs carry only the chamber."""
    if envelope.get("orgao"):
        return envelope["orgao"]
    number = envelope.get("camara")
    return CIVIL.format(number) if isinstance(number, int) else None


def portal_names(content: bytes) -> list[str]:
    """Values of the selOrgao[] options of a portal search page, as sent in the filter."""
    select = BeautifulSoup(content, "html.parser").select_one('select[name="selOrgao[]"]')
    if select is None:
        raise FloraError("formato_invalido", "Página do TJSC sem o filtro de órgão.")
    return [option["value"] for option in select.select("option") if option.get("value")]
