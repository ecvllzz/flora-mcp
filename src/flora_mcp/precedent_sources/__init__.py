"""Adapters from official structured sources to flora-precedentes-1 packages.

Each adapter is a pure function over bytes already collected, with their receipt (URL, time
with offset, SHA-256). Nothing here opens a network connection or the collection database.

A source is ``estruturada`` only when its URL is one registered below; any other source is a
``documento`` and its records keep requiring individual review.
"""

import importlib
import re

CLASSES = ("estruturada", "documento")
# Matter an adapter declares when the source branch is known and outside the approved scope.
OUT_OF_SCOPE = "fora_do_recorte"
STRUCTURED = {
    # Open data catalog of qualified precedents (temas.csv and processos.csv).
    "stj_temas": r"https://dadosabertos\.web\.stj\.jus\.br/dataset/[^/?#]+/resource/[^/?#]+"
    r"/download/(temas|processos)\.csv",
    # SCON listing of the STJ summaries.
    "stj_sumulas": r"https://processo\.stj\.jus\.br/SCON/sumstj/toc\.jsp\?[^#]*",
    # STF summaries, ordinary (base=30) and binding (base=26): index and one page per summary.
    "stf_sumulas": r"https://portal\.stf\.jus\.br/jurisprudencia/sumariosumulas\.asp\?base=(26|30)"
    r"(&sumula=[0-9]+)?",
}
ADAPTERS = tuple(STRUCTURED)


def structured_url(url: str) -> str | None:
    """Name of the registered structured source serving this URL, if any."""
    for name, pattern in STRUCTURED.items():
        if isinstance(url, str) and re.fullmatch(pattern, url):
            return name
    return None


def adapter(name: str):
    if name not in STRUCTURED:
        raise ValueError(f"Fonte desconhecida: {name}")
    return importlib.import_module(f"{__name__}.{name}")
