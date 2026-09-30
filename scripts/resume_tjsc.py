"""Retoma apenas janelas TJSC não concluídas; padrão é plano sem escrita/rede."""

import argparse
import json
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

from filelock import FileLock

from flora_mcp import backups
from flora_mcp.config import load_config
from flora_mcp.model import FloraError, digest, now
from flora_mcp.sources import client
from flora_mcp.store import Store, connection
from flora_mcp.tjsc import catalog_window, collect_window
from flora_mcp.tjsc_orgaos import ORGAOS, PADRAO, dataset, envelope_organ, identity, name


def save(path, value):
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


def plan(store, start, end, organs=PADRAO):
    """organs: portal names or Civil Law Chamber numbers, in collection order."""
    if start > end or end > date.today():
        raise ValueError("Intervalo invertido ou futuro.")
    names = list(dict.fromkeys(name(organ) for organ in organs))
    missing, done = [], []
    with connection(store.path) as db:
        for organ in names:
            records = {
                r["id"]: dict(r)
                for r in db.execute(
                    "SELECT * FROM resources WHERE dataset=? AND present=1", (dataset(organ),)
                )
            }
            day = start
            while day <= end:
                resource_id = dataset(organ) + ":" + day.isoformat()
                record = records.get(resource_id)
                entry = {**identity(organ), "dia": day.isoformat(), "recurso": resource_id}
                if record and record["status"] == "ok":
                    raw_path = record["raw_path"]
                    if not raw_path:
                        raise FloraError("original_ausente", resource_id)
                    path = (store.directory / raw_path).resolve()
                    if not path.is_relative_to(store.directory.resolve()) or not path.is_file():
                        raise FloraError("original_ausente", resource_id)
                    content = path.read_bytes()
                    if digest(content) != record["sha256"]:
                        raise FloraError("original_corrompido", resource_id)
                    envelope = json.loads(content)
                    count = db.execute(
                        "SELECT count(*) FROM observations WHERE resource_id=?", (resource_id,)
                    ).fetchone()[0]
                    if (
                        count != record["count"]
                        or envelope_organ(envelope) != organ
                        or envelope.get("data_publicacao") != str(day)
                        or envelope.get("total") != count
                    ):
                        raise FloraError("janela_inconsistente", resource_id)
                    done.append(entry)
                else:
                    missing.append({**entry, "estado_anterior": record["status"] if record else "ausente"})
                day += timedelta(days=1)
    missing.sort(key=lambda item: (item["dia"], names.index(item["orgao"])))
    return {
        "periodo_publicacao": [str(start), str(end)],
        "orgaos": names,
        "concluidas_verificadas": len(done),
        "pendentes": missing,
        "dia_atual_provisorio": end == date.today(),
    }


def execute(config, store, start, end, report_path, backup_root=None, *, fetch=collect_window, organs=PADRAO):
    """backup_root: raiz dos backups no formato novo; padrão, a pasta irmã <acervo>-backups."""
    report_path = Path(report_path).resolve()
    backup_root = Path(backup_root or backups.default_root(store.directory)).resolve()
    if backup_root.is_relative_to(store.directory.resolve()):
        raise ValueError("Backup deve ficar fora do acervo.")
    if report_path.exists():
        raise ValueError("Use novo recibo de execução; recibos anteriores são preservados.")
    with FileLock(str(store.directory / "collector.lock"), timeout=0):
        store.initialize()
        work = plan(store, start, end, organs)
        report = {
            "inicio": now(),
            "banco": str(store.path),
            "plano": work,
            "antes": groups(store),
            "status": "preparado",
            "eventos": [],
        }
        save(report_path, report)
        if not work["pendentes"]:
            report.update(status="ok", fim=now(), depois=report["antes"])
            save(report_path, report)
            return report
        report["backup"] = backups.create(store, backup_root, "antes-retomada-tjsc")
        run = store.start_run("TJSC")
        report.update(execucao=run, status="running")
        save(report_path, report)
        try:
            with client() as http:
                for entry in work["pendentes"]:
                    organ, day = entry["orgao"], date.fromisoformat(entry["dia"])
                    report["em_andamento"] = entry
                    save(report_path, report)
                    catalog_window(store, organ, day)
                    with connection(store.path) as db:
                        saved = dict(
                            db.execute("SELECT * FROM resources WHERE id=?", (entry["recurso"],)).fetchone()
                        )
                    try:
                        content, rows = fetch(http, config, organ, day)
                        counts = store.ingest(saved, content, rows, run)
                    except Exception as exc:
                        store.failure(entry["recurso"], run, str(exc))
                        raise
                    event = {
                        **identity(organ),
                        "dia": str(day),
                        "registros": len(rows),
                        **counts,
                        "fim": now(),
                    }
                    report["eventos"].append(event)
                    report.pop("em_andamento", None)
                    save(report_path, report)
                    print(
                        json.dumps(
                            {
                                "concluidas_nesta_execucao": len(report["eventos"]),
                                "total_planejado": len(work["pendentes"]),
                                **event,
                            },
                            ensure_ascii=True,
                        ),
                        flush=True,
                    )
            report["status"] = "ok"
        except BaseException as exc:
            report.update(
                status="interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "error",
                erro=f"{type(exc).__name__}: {exc}",
                codigo=getattr(exc, "code", "erro_fonte"),
            )
            raise
        finally:
            report.update(fim=now(), depois=groups(store))
            store.finish_run(run, report["status"], report)
            from flora_mcp.publication import MANIFEST, publish

            if (store.directory / MANIFEST).exists():
                report["publicacao"] = publish(store)
            save(report_path, report)
        return report


def selected_organs(camaras: str | None, orgaos: list[str]) -> tuple[str, ...]:
    """Chambers by number, then organs by name, without repeats; neither given: 9 and 10."""
    if camaras is None and not orgaos:
        return PADRAO
    numbers = [int(c) for c in camaras.split(",")] if camaras else []
    if any(not 1 <= c <= 10 for c in numbers):
        raise ValueError("Câmaras de Direito Civil: números de 1 a 10.")
    return tuple(dict.fromkeys([name(c) for c in numbers] + [name(o.strip()) for o in orgaos]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--inicio", required=True)
    parser.add_argument("--fim", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--backup", type=Path, help="Raiz dos backups; padrão <acervo>-backups")
    parser.add_argument(
        "--camaras",
        help="Câmaras de Direito Civil por número, separadas por vírgula; sem --camaras nem --orgaos, 9,10",
    )
    parser.add_argument(
        "--orgaos",
        action="append",
        default=[],
        metavar="NOME",
        help="Órgão pelo nome exato do filtro do portal; repita para mais de um. Aceitos: "
        + "; ".join(ORGAOS),
    )
    args = parser.parse_args()
    if args.apply and not args.report:
        parser.error("Aplicação exige --report novo.")
    try:
        organs = selected_organs(args.camaras, args.orgaos)
    except (ValueError, FloraError) as exc:
        parser.error(str(exc))
    config = load_config(data_dir=args.data_dir)
    store = Store(config.data_dir)
    start, end = date.fromisoformat(args.inicio), date.fromisoformat(args.fim)
    if args.apply:
        result = execute(config, store, start, end, args.report, args.backup, organs=organs)
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "janelas": len(result["eventos"]),
                    "depois": result["depois"],
                    "report": str(args.report),
                },
                ensure_ascii=True,
            ),
            flush=True,
        )
    else:
        work = plan(store, start, end, organs)
        print(json.dumps({**work, "pendentes": len(work["pendentes"])}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
