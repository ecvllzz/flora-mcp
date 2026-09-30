"""Pieces shared by the adapters: the collected original, evidence and the adapter result."""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

from . import OUT_OF_SCOPE


@dataclass(frozen=True)
class Original:
    """Bytes of an official original and its collection receipt.

    ``arquivo`` is the path of the copy relative to the package that will cite it.
    """

    arquivo: str
    content: bytes
    url: str
    coletado_em: str
    sha256: str
    content_type: str | None = None

    def text(self) -> str:
        """Decoded with the charset the server declared; UTF-8 when it declared none."""
        match = re.search(r"charset=([\w-]+)", self.content_type or "", re.I)
        return self.content.decode(match.group(1) if match else "utf-8")

    def source(self) -> dict:
        return {
            "url": self.url,
            "sha256": self.sha256,
            "arquivo": self.arquivo,
            "coletado_em": self.coletado_em,
            "classe": "estruturada",
        }

    def evidence(self, trecho: str, localizador: str) -> dict:
        return {"fonte_sha256": self.sha256, "trecho": trecho, "localizador": localizador}


@dataclass
class Result:
    """Records of one adapter run and the source entries it left out, each with a reason."""

    registros: list = field(default_factory=list)
    ignorados: list = field(default_factory=list)

    def ignore(self, referencia: str, motivo: str):
        self.ignorados.append({"referencia": referencia, "motivo": motivo})


def iso_date(day: str, month: str, year: str) -> str | None:
    """Day, month and year as printed by the source to AAAA-MM-DD; None when not a date."""
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        return None


# STJ sections of public law (Primeira) and criminal law (Terceira). There the source's
# "processual civil" branch is procedure of public or criminal law (tax enforcement, fees
# against the State), outside the civil scope decided on 30/09/2026; kept pending for the operator.
SECOES_FORA_DO_RECORTE = {"S1", "S3", "PRIMEIRA SECAO", "TERCEIRA SECAO"}
SECAO_PENDENCIA = "secao_fora_do_recorte_civil"


def section_flag(organ: str) -> str | None:
    """Pending reason for a record judged by the STJ public or criminal law section; None otherwise."""
    name = "".join(c for c in unicodedata.normalize("NFKD", organ.upper()) if not unicodedata.combining(c))
    return SECAO_PENDENCIA if " ".join(name.split()) in SECOES_FORA_DO_RECORTE else None


# One matter per record; with mixed branches, the first of this order present (civil prevails).
PRIORIDADE = ("civil", "processual_civil", "bancario")


def branch_matter(branches: list[str], table: dict[str, str]) -> str | None:
    """Matter of a record from the literal source branches, by an explicit table.

    No branch: None (matter not confirmed). Any branch outside the table: out of scope.
    Otherwise the first matter of PRIORIDADE among the branches: banking with civil is civil.
    """
    if not branches:
        return None
    matters = {table.get(branch) for branch in branches}
    if None in matters:
        return OUT_OF_SCOPE
    return next(matter for matter in PRIORIDADE if matter in matters)
