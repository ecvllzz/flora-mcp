import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

LOCAL_CONFIG = Path(__file__).resolve().parents[2] / "flora.local.toml"

@dataclass
class Config:
    data_dir: Path
    resource_from: str = "20250101"
    max_resources: int = 2  # por dataset por execução; pendências permanecem visíveis
    recheck_days: int = 7
    max_download_bytes: int = 64 * 1024 * 1024
    request_delay: float = 1.0
    datasets: list[str] = field(
        default_factory=lambda: [
            "espelhos-de-acordaos-terceira-turma",
            "espelhos-de-acordaos-quarta-turma",
            "espelhos-de-acordaos-segunda-secao",
        ]
    )

    @property
    def db_path(self) -> Path:
        return self.data_dir / "acervo.sqlite"


def load_config(path: str | None = None, data_dir: str | None = None) -> Config:
    values = {}
    config_path = Path(path) if path else LOCAL_CONFIG
    if path or config_path.is_file():
        with config_path.open("rb") as f:
            values = tomllib.load(f).get("flora", {})
    directory = data_dir or os.environ.get("FLORA_MCP_DATA_DIR") or values.pop("data_dir", None)
    values.pop("data_dir", None)
    if not directory or not str(directory).strip():
        raise ValueError("Pasta do acervo não configurada. Defina --data-dir, FLORA_MCP_DATA_DIR "
                         "ou data_dir em flora.local.toml. AppData não é usado como padrão.")
    if not Path(directory).expanduser().is_absolute():
        raise ValueError("A pasta do acervo deve ser um caminho absoluto.")
    config = Config(data_dir=Path(directory).expanduser().resolve(), **values)
    from datetime import datetime

    datetime.strptime(config.resource_from, "%Y%m%d")
    if config.max_resources < 1 or config.recheck_days < 1 or config.max_download_bytes < 1024:
        raise ValueError("Limites de coleta devem ser positivos.")
    if config.request_delay < 0:
        raise ValueError("Intervalo entre requisições inválido.")
    return config
