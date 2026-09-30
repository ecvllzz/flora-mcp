"""One bounded update of the collection: backup, STJ batches, TJSC window, publication and log. No LLM."""

import json
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path

from filelock import FileLock

from . import backups
from .config import Config
from .model import FloraError, local_date, now
from .publication import MANIFEST, publish
from .sources import client, sync_stj
from .store import Store
from .tjsc import sync_tjsc


def tjsc_window(days: int, today: date | None = None) -> tuple[date, date]:
    """Moving window of publication days ending today in São Paulo."""
    if not 1 <= days <= 31:
        raise FloraError("limite_invalido", "A janela do TJSC vai de 1 a 31 dias.")
    end = today or local_date()
    return end - timedelta(days=days - 1), end


def collect(report: dict, source: str, run) -> None:
    """Run one source; a failure is recorded and does not stop the other source."""
    try:
        report["execucoes"].append(run())
    except Exception as exc:
        report["execucoes"].append(
            {
                "fonte": source,
                "status": "error",
                "codigo": getattr(exc, "code", "erro_fonte"),
                "erro": f"{type(exc).__name__}: {exc}",
            }
        )


def final_status(report: dict) -> str:
    statuses = {r["status"] for r in report["execucoes"]}
    if report.get("publicacao", {}).get("status") == "error":
        statuses.add("error")
    return "error" if "error" in statuses else "partial" if "partial" in statuses else "ok"


def write_log(config: Config, report: dict) -> Path:
    logs = config.data_dir / "logs"
    logs.mkdir(exist_ok=True)
    path = logs / (datetime.now().strftime("%Y%m%d-%H%M%S") + ".json")
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def update(
    config: Config,
    store: Store,
    *,
    stj_lotes: int = 2,
    tjsc_dias: int = 7,
    stj: bool = True,
    tjsc: bool = True,
    precedents_package: Path | None = None,
    backup_root: Path | None = None,
    http_client=client,
    today: date | None = None,
) -> dict:
    if stj_lotes < 1:
        raise FloraError("limite_invalido", "Informe ao menos um lote do STJ por dataset.")
    if not stj and not tjsc:
        raise FloraError("fonte_invalida", "Escolha ao menos uma fonte.")
    start, end = tjsc_window(tjsc_dias, today)
    if not config.db_path.is_file():
        raise FloraError(
            "base_nao_inicializada",
            "Banco não encontrado na pasta configurada. Confira o caminho; nenhum acervo é criado.",
        )
    report = {
        "inicio": now(),
        "rotina": "atualizar",
        "parametros": {
            "stj_lotes": stj_lotes if stj else None,
            "tjsc_janela": [str(start), str(end)] if tjsc else None,
        },
        "execucoes": [],
    }
    try:
        with FileLock(str(config.data_dir / "collector.lock"), timeout=0):
            store.initialize()
            if precedents_package:
                from .precedents import import_package

                # Validation first: an invalid package stops before any write.
                import_package(store, precedents_package.resolve())
            root = backup_root or backups.default_root(config.data_dir)
            report["backup"] = backups.create(store, root, "antes-atualizacao")
            if precedents_package:
                report["execucoes"].append(import_package(store, precedents_package.resolve(), apply=True))
            batches = replace(config, max_resources=stj_lotes)
            with http_client() as http:
                if stj:
                    collect(report, "STJ", lambda: sync_stj(batches, store, http))
                if tjsc:
                    collect(report, "TJSC", lambda: sync_tjsc(config, store, http, start, end))
            if (config.data_dir / MANIFEST).exists():
                try:
                    report["publicacao"] = publish(store)
                except FloraError as exc:
                    report["publicacao"] = {"status": "error", "codigo": exc.code, "erro": str(exc)}
        report["status"] = final_status(report)
    except BaseException as exc:
        interrupted = isinstance(exc, (KeyboardInterrupt, SystemExit))
        report.update(
            status="interrupted" if interrupted else "error",
            codigo=getattr(exc, "code", type(exc).__name__),
            erro=str(exc),
        )
        raise
    finally:
        report["fim"] = now()
        if "backup" in report or report["execucoes"]:
            report["log"] = str(write_log(config, report))
    return report
