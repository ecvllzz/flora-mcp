import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone


class FloraError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def folded(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c)).upper()


def number(value: str) -> str:
    return re.sub(r"\D", "", value)


def normalize_stj(raw: dict) -> dict:
    if not isinstance(raw, dict) or not raw.get("id") or not isinstance(raw.get("ementa"), str):
        raise FloraError("formato_invalido", "Espelho STJ sem identificador ou ementa textual.")
    organ = raw.get("nomeOrgaoJulgador")
    if not isinstance(organ, str) or not organ.strip():
        raise FloraError("formato_invalido", "Órgão julgador ausente no espelho STJ.")
    judgment = raw.get("dataDecisao")
    if judgment:
        try:
            judgment = datetime.strptime(str(judgment), "%Y%m%d").date().isoformat()
        except ValueError as exc:
            raise FloraError("formato_invalido", "Data de julgamento STJ inválida.") from exc
    publication_raw = raw.get("dataPublicacao") or ""
    dates = re.findall(r"\b\d{2}/\d{2}/\d{4}\b", publication_raw)
    # Mais de uma data não permite escolher uma silenciosamente.
    publication = None
    if len(set(dates)) == 1:
        try:
            publication = datetime.strptime(dates[0], "%d/%m/%Y").date().isoformat()
        except ValueError:
            pass
    process_number = str(raw.get("numeroProcesso") or "")
    class_name = raw.get("siglaClasse") or ""
    return {
        "id": "STJ:" + str(raw["id"]),
        "id_origem": str(raw["id"]),
        "tribunal": "STJ",
        "orgao": organ,
        "classe": class_name,
        "processo": f"{class_name} {process_number}".strip(),
        "numero_processo": process_number,
        "numero_registro": str(raw.get("numeroRegistro") or ""),
        "data_julgamento": judgment or None,
        "data_publicacao": publication,
        "publicacao_original": publication_raw,
        "ementa": raw["ementa"],
        "url_documento": None,
        "inteiro_teor_disponivel": False,
        "tipo_conteudo": "espelho_de_acordao",
        "extrator": "stj-json-v1",
        "atribuicao": "Superior Tribunal de Justiça — dados abertos; licença informada pelo catálogo.",
    }
