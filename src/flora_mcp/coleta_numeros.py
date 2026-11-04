"""Directed collection by process number, for a list from any origin. Plan by default.

TJSC: each number is one search of the portal (dataset tjsc-processo), sequential at the configured
pause; a number with no result ends as a finished search with zero documents, and the first source
failure stops the run, which the next execution resumes. STJ: the open data has no search, so the
files are read and only the selected acórdãos are loaded (see stj_selecao).

The receipt is written before the first request and after each number; the lock, the backup and the
publication are the same for both courts.
"""

import json
import os
import tempfile
from pathlib import Path

from filelock import FileLock

from . import backups
from .config import Config
from .model import FloraError, now, number
from .numeros import stj_family
from .sources import client
from .stj_selecao import collect_selection
from .store import Store, connection
from .tjsc import PROCESSO_DATASET, catalog_process, collect_process


def save(path, value):
    """Write a receipt atomically."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".retomada-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def groups(store):
    with connection(store.path) as db:
        return [
            dict(r)
            for r in db.execute(
                "SELECT tribunal,json_extract(body,'$.orgao') AS orgao,count(*) AS documentos "
                "FROM documents GROUP BY tribunal,organ ORDER BY tribunal,organ"
            )
        ]


def by_court(entries: list[dict]) -> tuple[list[dict], list[dict]]:
    """TJSC and STJ entries; an entry that names no court is of the TJSC, as the first lists were."""
    stj = [e for e in entries if e.get("tribunal") == "STJ"]
    return [e for e in entries if e.get("tribunal", "TJSC") == "TJSC"], stj


def plan(store: Store, entries: list[dict]) -> dict:
    with connection(store.path) as db:
        done = {
            r[0]
            for r in db.execute(
                "SELECT id FROM resources WHERE dataset=? AND status='ok' AND present=1", (PROCESSO_DATASET,)
            )
        }
    pending = [e for e in entries if f"{PROCESSO_DATASET}:{e['chave']}" not in done]
    return {"numeros": len(entries), "concluidos": len(entries) - len(pending), "pendentes": pending}


def _held_by_key(store: Store, entries: list[dict]) -> dict[str, int]:
    """How many acórdãos the collection already has for each STJ key (a read, for the plan)."""
    wanted = {e["chave"] for e in entries}
    counts = dict.fromkeys(wanted, 0)
    with connection(store.path) as db:
        for class_name, digits, registration in db.execute(
            "SELECT json_extract(body,'$.classe'),process,registration FROM documents WHERE tribunal='STJ'"
        ):
            for key in (
                f"{stj_family(class_name or '')}:{digits.lstrip('0')}",
                f"REGISTRO:{number(registration)}",
            ):
                if key in wanted:
                    counts[key] += 1
    return counts


def plan_stj(store: Store, entries: list[dict]) -> dict:
    """The STJ reading always covers the whole list: a process may have acórdãos in other files."""
    counts = _held_by_key(store, entries)
    return {
        "numeros": len(entries),
        "itens": [{**e, "acordaos_ja_no_acervo": counts[e["chave"]]} for e in entries],
    }


def collect_one(config, store, http, entry, run) -> dict:
    resource_id = catalog_process(store, entry["chave"])
    with connection(store.path) as db:
        saved = dict(db.execute("SELECT * FROM resources WHERE id=?", (resource_id,)).fetchone())
    try:
        content, rows = collect_process(http, config, entry["chave"])
        counts = store.ingest(saved, content, rows, run)
    except Exception as exc:
        store.failure(resource_id, run, str(exc))
        raise
    return {
        **entry,
        "registros": len(rows),
        "orgaos": sorted({body["orgao"] for body, _ in rows}),
        "documentos": [body["id"] for body, _ in rows],
        **counts,
        "fim": now(),
    }


def _print_progress(report, pending, entry, event):
    progress = {
        "feitos": len(report["eventos"]),
        "de": len(pending),
        "numero": entry["numero"],
        "registros": event["registros"],
    }
    print(json.dumps(progress), flush=True)


def collect_tjsc(config, store, http, pending, report, report_path, collect) -> None:
    """Numbers of the TJSC, in order; stops at the first source failure and keeps what was done."""
    run = store.start_run("TJSC-processo")
    report.update(execucao=run, status="running")
    save(report_path, report)
    try:
        for entry in pending:
            report["em_andamento"] = entry
            event = collect(config, store, http, entry, run)
            report["eventos"].append(event)
            report.pop("em_andamento", None)
            save(report_path, report)
            _print_progress(report, pending, entry, event)
        report["status"] = "ok"
    except BaseException as exc:
        report.update(
            status="interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "error",
            erro=f"{type(exc).__name__}: {exc}",
            codigo=getattr(exc, "code", "erro_fonte"),
        )
        raise
    finally:
        report["nao_oferecidos"] = [
            {"numero": e["numero"], "origens": e["origens"]} for e in report["eventos"] if not e["registros"]
        ]
        store.finish_run(run, report["status"], {k: v for k, v in report.items() if k != "stj"})


def execute(
    config: Config,
    store: Store,
    entries: list[dict],
    refused: list[dict],
    report_path,
    backup_root=None,
    *,
    collect=collect_one,
    scope: dict | None = None,
    http_factory=client,
) -> dict:
    report_path = Path(report_path).resolve()
    backup_root = Path(backup_root or backups.default_root(store.directory)).resolve()
    if backup_root.is_relative_to(store.directory.resolve()):
        raise ValueError("Backup deve ficar fora do acervo.")
    if report_path.exists():
        raise ValueError("Use novo recibo de execução; recibos anteriores são preservados.")
    tjsc, stj = by_court(entries)
    with FileLock(str(store.directory / "collector.lock"), timeout=0):
        store.initialize()
        work = plan(store, tjsc)
        report = {
            "inicio": now(),
            "banco": str(store.path),
            "pausa_entre_requisicoes": config.request_delay,
            "plano": work,
            "recusados": refused,
            "antes": groups(store),
            "status": "preparado",
            "eventos": [],
        }
        if stj:
            report["stj"] = {"status": "preparado", "numeros": len(stj)}
        save(report_path, report)
        if not work["pendentes"] and not stj:
            report.update(status="ok", fim=now(), depois=report["antes"])
            save(report_path, report)
            return report
        report["backup"] = backups.create(store, backup_root, "antes-coleta-por-numero")
        save(report_path, report)
        try:
            with http_factory() as http:
                if stj:
                    report["stj"] = collect_selection(config, store, http, stj, scope)
                    save(report_path, report)
                if work["pendentes"]:
                    collect_tjsc(config, store, http, work["pendentes"], report, report_path, collect)
                else:
                    report["status"] = "ok"
        finally:
            report.update(fim=now(), depois=groups(store))
            _publish(store, report)
            save(report_path, report)
        return report


def _publish(store: Store, report: dict) -> None:
    from .publication import MANIFEST, publish

    if (store.directory / MANIFEST).exists():
        report["publicacao"] = publish(store)


def summary(report: dict) -> dict:
    """What the command prints; the receipt holds the rest."""
    stj = report.get("stj") or {}
    status = report["status"]
    if stj.get("status") == "error" and status == "ok":
        status = "error"
    return {
        "status": status,
        "tjsc": {
            "consultas": len(report["eventos"]),
            "nao_oferecidos": len(report.get("nao_oferecidos") or []),
        },
        "stj": {
            "status": stj.get("status"),
            "arquivos_lidos": len(stj.get("arquivos_varridos") or []),
            "arquivos_guardados": len(stj.get("arquivos_guardados") or []),
            "selecionados": len(stj.get("selecionados") or []),
            "nao_oferecidos": len(stj.get("nao_oferecidos") or []),
            "nao_localizados_no_recorte": len(stj.get("nao_localizados_no_recorte") or []),
            "falhas": len(stj.get("falhas") or []),
        },
        "recusados": len(report["recusados"]),
    }


def read_scope(datasets: list[str] | None, desde: str | None, ate: str | None) -> dict:
    """Optional narrowing of the STJ reading; a narrowed reading proves no absence."""
    for value in (desde, ate):
        if value and not (len(value) == 8 and value.isdigit()):
            raise FloraError("recorte_invalido", "Recorte de arquivos do STJ no formato AAAAMMDD.")
    return {"datasets": datasets or None, "desde": desde, "ate": ate}
