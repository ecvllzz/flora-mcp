"""STJ repetitive themes and IAC, from the open data CSV files temas.csv and processos.csv.

Each field comes from one column of one logical CSV record; the evidence locator names the
file, the logical line (header = 1) and the column, and the excerpt is the cell text.
"""

import csv
import io
import re

from .common import Original, Result, branch_matter, section_flag

CLASSE = "estruturada"
TIPOS = {"Tema": "tema_repetitivo", "IAC": "iac"}
# Source situation to (situacao, pendencia). A value outside the table becomes "desconhecido".
SITUACOES = {
    "Trânsito em Julgado": ("vigente", None),
    "Acórdão Publicado": ("vigente", None),
    "Acórdão Publicado - RE Pendente": ("vigente", "recurso_extraordinario_pendente"),
    "Afetado - Possível Revisão de Tese": ("vigente", "revisao_de_tese_pendente"),
    "Afetado": ("pendente", None),
    "Admitido": ("pendente", None),
    "Em Julgamento": ("pendente", None),
    "Mérito Julgado": ("pendente", None),
    "Sobrestado": ("pendente", None),
    "Cancelado": ("cancelado", None),
    "Cancelada": ("cancelado", None),
    "Revisado": ("superado", None),
}
# Branches of the CNJ unified subject table (column Assuntos), code and name as printed.
# Family, successions and business law are subjects under 899 in that table. The table has no
# banking branch: bank contracts (9607, 4960) are subjects under civil or consumer law.
RAMOS = {
    "899- DIREITO CIVIL": "civil",
    "1156- DIREITO DO CONSUMIDOR": "civil",
    "8826- DIREITO PROCESSUAL CIVIL E DO TRABALHO": "processual_civil",
}
# Organ codes (S1, S2, S3, CE) stay literal: the catalog dictionary has no table for them.
ORGAOS: dict[str, str] = {}
COMPONENTES = {"questao_submetida": "questaoSubmetidaAJulgamento", "tese_firmada": "teseFirmada"}
# Columns read from temas.csv; repeated rows of one theme must agree on all of them.
USADAS = (
    "sequencialPrecedente",
    "tipoPrecedente",
    "numeroPrecedente",
    "orgaoJulgador",
    "situacao",
    "dataPublicacaoAcordao",
    "Assuntos",
    "questaoSubmetidaAJulgamento",
    "teseFirmada",
)
LEADING = ("Processo", "numeroRegistro", "leadingCase", "ministroRelator", "dataJulgamento")


def role(url: str) -> str | None:
    match = re.search(r"/download/(temas|processos)\.csv$", url)
    return match.group(1) if match else None


def rows(original: Original):
    """(logical line, record) pairs; the header is logical line 1."""
    reader = csv.DictReader(io.StringIO(original.content.decode("utf-8-sig"), newline=""))
    for index, row in enumerate(reader):
        yield index + 2, row


def branches(subjects: str) -> list[str]:
    """Top branches among the subjects: segments whose name is uppercase and starts with DIREITO."""
    parts = [part.strip() for part in re.split(r",\s*(?=\d+-\s)", subjects) if part.strip()]
    return [p for p in parts if re.fullmatch(r"\d+- DIREITO[^a-z]*", p)]


def brazilian(value: str) -> str:
    return "/".join(reversed(value.split("-"))) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else value


class Row:
    """One theme row with its locator."""

    def __init__(self, original: Original, line: int, row: dict):
        self.original, self.line, self.row = original, line, row

    def evidence(self, column: str, trecho: str | None = None) -> dict:
        return self.original.evidence(
            self.row[column].strip() if trecho is None else trecho,
            f"{self.original.arquivo}, CSV linha lógica {self.line} (cabeçalho = 1), "
            f"sequencialPrecedente={self.row['sequencialPrecedente']}, coluna {column}",
        )


def leading_cases(processes: Original | None) -> dict[str, dict]:
    """Leading cases of each theme, by sequencialPrecedente; one per registration number."""
    found = {}
    if processes is None:
        return found
    for line, row in rows(processes):
        if row.get("leadingCase") != "S" or not row.get("numeroRegistro", "").strip():
            continue
        values = [row.get(column, "").strip() for column in LEADING]
        key = "vinculo:" + row["numeroRegistro"].strip()
        found.setdefault(row["sequencialPrecedente"], {}).setdefault(key, (line, row, values))
    return found


def link(processes: Original, organ: str, key: str, line: int, row: dict, values: list):
    judged, published = row.get("dataJulgamento", "").strip(), row.get("dataPbulicacaoAcordao", "").strip()
    reference = f"STJ, {row['Processo'].strip()}"
    reference += f", rel. {row['ministroRelator'].strip()}" if row.get("ministroRelator", "").strip() else ""
    reference += f", {organ}" + (f", j. {brazilian(judged)}" if judged else "")
    reference += f", publ. {brazilian(published)}" if published else ""
    evidence = processes.evidence(
        " | ".join(values),
        f"{processes.arquivo}, CSV linha lógica {line} (cabeçalho = 1), colunas {' | '.join(LEADING)}",
    )
    related = {
        "id": f"STJ:registro:{row['numeroRegistro'].strip()}:{judged}",
        "referencia": reference,
        "evidencia_vinculo": key,
    }
    return related, evidence


def record(item: Row, species: str, organ: str) -> dict:
    row = item.row
    status, flag = SITUACOES.get(row["situacao"].strip(), ("desconhecido", None))
    publication = row["dataPublicacaoAcordao"].strip()
    evidence = {"situacao": item.evidence("situacao")}
    if publication:
        evidence["publicacao"] = item.evidence("dataPublicacaoAcordao")
    if branches(row["Assuntos"]):
        evidence["materia"] = item.evidence("Assuntos")
    components = {}
    for name, column in COMPONENTES.items():
        if row[column].strip():
            components[name] = row[column].strip()
            evidence["componente:" + name] = item.evidence(column)
    return {
        "tribunal": "STJ",
        "especie": species,
        "numero": row["numeroPrecedente"].strip(),
        "orgao": organ,
        "materia": branch_matter(branches(row["Assuntos"]), RAMOS),
        "data_publicacao": publication or None,
        "tipo_publicacao": "acordao_merito",
        "situacao": status,
        "pendencias": [f for f in (flag, section_flag(organ)) if f],
        "componentes": components,
        "fontes": [item.original.source()],
        "evidencias": evidence,
        "julgados_relacionados": [],
    }


def skip_reason(row: dict) -> str | None:
    if row["tipoPrecedente"].strip() not in TIPOS:
        return "tipo_fora_do_contrato:" + row["tipoPrecedente"].strip()
    if not re.fullmatch(r"[1-9][0-9]{0,6}", row["numeroPrecedente"].strip()):
        return "numero_invalido"
    if not row["orgaoJulgador"].strip():
        return "orgao_ausente"
    return None


def unique_rows(themes: Original, result: Result):
    """One row per theme. The file repeats a theme once per related STF theme; the repeated
    rows must agree on every column read here, or the theme is left out as ambiguous."""
    groups = {}
    for line, row in rows(themes):
        reason = skip_reason(row)
        if reason:
            result.ignore(f"linha lógica {line}, {row['tipoPrecedente']} {row['numeroPrecedente']}", reason)
            continue
        identity = (row["tipoPrecedente"].strip(), row["numeroPrecedente"].strip())
        groups.setdefault(identity, []).append((line, row))
    for (kind, number), items in groups.items():
        first = [items[0][1][column] for column in USADAS]
        if any([row[column] for column in USADAS] != first for _, row in items[1:]):
            result.ignore(f"{kind} {number}", "identidade_ambigua")
            continue
        for line, _ in items[1:]:
            result.ignore(f"linha lógica {line}, {kind} {number}", "linha_repetida")
        yield items[0]


def adapt(originals: list[Original]) -> Result:
    by_role = {role(o.url): o for o in originals}
    themes, processes = by_role.get("temas"), by_role.get("processos")
    if themes is None:
        raise ValueError("Falta o original temas.csv.")
    result, links = Result(), leading_cases(processes)
    for line, row in unique_rows(themes, result):
        organ = ORGAOS.get(row["orgaoJulgador"].strip(), row["orgaoJulgador"].strip())
        body = record(Row(themes, line, row), TIPOS[row["tipoPrecedente"].strip()], organ)
        for key, (link_line, link_row, values) in links.get(row["sequencialPrecedente"], {}).items():
            related, evidence = link(processes, organ, key, link_line, link_row, values)
            body["julgados_relacionados"].append(related)
            body["evidencias"][key] = evidence
        if body["julgados_relacionados"]:
            body["fontes"].append(processes.source())
        result.registros.append(body)
    return result
