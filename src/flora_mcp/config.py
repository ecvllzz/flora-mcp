import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .model import FloraError
from .tjsc_orgaos import PADRAO, window_name

LOCAL_CONFIG = Path(__file__).resolve().parents[2] / "flora.local.toml"
# Dias sem coleta bem-sucedida a partir dos quais a fonte aparece em atraso na cobertura.
ATRASO_PADRAO = {"STJ": 45, "TJSC": 7}
# Ferramentas MCP que aceitam orientação da instalação ao fim da descrição ([flora.orientacoes]).
FERRAMENTAS = (
    "pesquisar_jurisprudencia",
    "pesquisar_precedentes",
    "obter_documento",
    "consultar_cobertura",
    "conferir_referencias",
)


@dataclass
class Config:
    data_dir: Path
    resource_from: str = "20250101"
    max_resources: int = 2  # por dataset por execução; pendências permanecem visíveis
    recheck_days: int = 7
    max_download_bytes: int = 64 * 1024 * 1024
    request_delay: float = 1.0
    atraso_stj_dias: int = ATRASO_PADRAO["STJ"]  # o lote do STJ é mensal
    atraso_tjsc_dias: int = ATRASO_PADRAO["TJSC"]
    datasets: list[str] = field(
        default_factory=lambda: [
            "espelhos-de-acordaos-terceira-turma",
            "espelhos-de-acordaos-quarta-turma",
            "espelhos-de-acordaos-segunda-secao",
        ]
    )
    # Órgãos do TJSC coletados por janela de dia de publicação, pelo nome do filtro do portal.
    tjsc_orgaos: list[str] = field(default_factory=lambda: list(PADRAO))
    # Texto por ferramenta, acrescentado ao fim da descrição que o cliente MCP recebe.
    orientacoes: dict[str, str] = field(default_factory=dict)
    # Nota que o atalho do painel abre; sem ela, o atalho abre o painel no navegador.
    painel_nota: str | None = None

    @property
    def atrasos(self) -> dict:
        return {"STJ": self.atraso_stj_dias, "TJSC": self.atraso_tjsc_dias}

    @property
    def db_path(self) -> Path:
        return self.data_dir / "acervo.sqlite"


def check_orientacoes(orientacoes: dict | None) -> dict[str, str]:
    """Guidance per tool, or ValueError naming the key: an unknown tool would be silently ignored."""
    orientacoes = orientacoes or {}
    if not isinstance(orientacoes, dict) or any(
        name not in FERRAMENTAS or not isinstance(text, str) for name, text in orientacoes.items()
    ):
        raise ValueError("orientacoes: um texto por ferramenta, entre " + ", ".join(FERRAMENTAS) + ".")
    return {name: text.strip() for name, text in orientacoes.items() if text.strip()}


def check_tjsc_orgaos(orgaos) -> list[str]:
    """Organs collected by day window: non-empty, each a portal name the window collector accepts."""
    if not isinstance(orgaos, list) or not orgaos or any(not isinstance(o, str) for o in orgaos):
        raise ValueError("tjsc_orgaos: lista com ao menos um nome de órgão do filtro do portal.")
    try:
        return [window_name(organ) for organ in orgaos]
    except FloraError as exc:
        raise ValueError(f"tjsc_orgaos: {exc}") from exc


def load_config(path: str | None = None, data_dir: str | None = None) -> Config:
    values = {}
    path = path or os.environ.get("FLORA_MCP_CONFIG") or None
    config_path = Path(path) if path else LOCAL_CONFIG
    if path or config_path.is_file():
        with config_path.open("rb") as f:
            values = tomllib.load(f).get("flora", {})
    directory = data_dir or os.environ.get("FLORA_MCP_DATA_DIR") or values.pop("data_dir", None)
    values.pop("data_dir", None)
    if not directory or not str(directory).strip():
        raise ValueError(
            "Pasta do acervo não configurada. Defina --data-dir, FLORA_MCP_DATA_DIR "
            "ou data_dir em flora.local.toml. AppData não é usado como padrão."
        )
    if not Path(directory).expanduser().is_absolute():
        raise ValueError("A pasta do acervo deve ser um caminho absoluto.")
    config = Config(data_dir=Path(directory).expanduser().resolve(), **values)
    from datetime import datetime

    datetime.strptime(config.resource_from, "%Y%m%d")
    if (
        config.max_resources < 1
        or config.recheck_days < 1
        or config.max_download_bytes < 1024
        or config.atraso_stj_dias < 1
        or config.atraso_tjsc_dias < 1
    ):
        raise ValueError("Limites de coleta devem ser positivos.")
    if config.request_delay < 0:
        raise ValueError("Intervalo entre requisições inválido.")
    config.tjsc_orgaos = check_tjsc_orgaos(config.tjsc_orgaos)
    config.orientacoes = check_orientacoes(config.orientacoes)
    if config.painel_nota is not None and not isinstance(config.painel_nota, str):
        raise ValueError("painel_nota: caminho da nota, em texto.")
    return config
