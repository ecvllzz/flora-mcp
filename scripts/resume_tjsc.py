"""Retoma apenas janelas TJSC não concluídas; padrão é plano sem escrita/rede."""

import argparse
import json
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

from filelock import FileLock

from flora_mcp.config import load_config
from flora_mcp.model import FloraError, digest, now
from flora_mcp.sources import TJSC_SEARCH, client
from flora_mcp.store import Store, connection
from flora_mcp.tjsc import collect_window


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
        return [dict(r) for r in db.execute(
            "SELECT tribunal,json_extract(body,'$.orgao') AS orgao,count(*) AS documentos "
            "FROM documents GROUP BY tribunal,organ ORDER BY tribunal,organ"
        )]


def plan(store, start, end, chambers=(9, 10)):
    if start > end or end > date.today():
        raise ValueError("Intervalo invertido ou futuro.")
    missing, done = [], []
    with connection(store.path) as db:
        for chamber in chambers:
            dataset = f"tjsc-{chamber}-civil"
            records = {r["id"]: dict(r) for r in db.execute(
                "SELECT * FROM resources WHERE dataset=? AND present=1", (dataset,)
            )}
            day = start
            while day <= end:
                resource_id = dataset + ":" + day.isoformat()
                record = records.get(resource_id)
                entry = {"camara": chamber, "dia": day.isoformat(), "recurso": resource_id}
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
                    if (count != record["count"] or envelope.get("camara") != chamber
                            or envelope.get("data_publicacao") != str(day)
                            or envelope.get("total") != count):
                        raise FloraError("janela_inconsistente", resource_id)
                    done.append(entry)
                else:
                    missing.append({**entry, "estado_anterior": record["status"] if record else "ausente"})
                day += timedelta(days=1)
    missing.sort(key=lambda item: (item["dia"], item["camara"]))
    return {"periodo_publicacao": [str(start), str(end)], "camaras": list(chambers),
            "concluidas_verificadas": len(done), "pendentes": missing,
            "dia_atual_provisorio": end == date.today()}


def execute(config, store, start, end, report_path, backup, *, fetch=collect_window):
    report_path, backup = Path(report_path).resolve(), Path(backup).resolve()
    if backup.is_relative_to(store.directory.resolve()):
        raise ValueError("Backup deve ficar fora do acervo.")
    if report_path.exists():
        raise ValueError("Use novo recibo de execução; recibos anteriores são preservados.")
    with FileLock(str(store.directory / "collector.lock"), timeout=0):
        work = plan(store, start, end)
        report = {"inicio": now(), "banco": str(store.path), "plano": work,
                  "antes": groups(store), "status": "preparado", "eventos": []}
        save(report_path, report)
        if not work["pendentes"]:
            report.update(status="ok", fim=now(), depois=report["antes"])
            save(report_path, report)
            return report
        report["backup"] = store.backup(backup)
        run = store.start_run("TJSC")
        report.update(execucao=run, status="running")
        save(report_path, report)
        try:
            with client() as http:
                for entry in work["pendentes"]:
                    chamber, day = entry["camara"], date.fromisoformat(entry["dia"])
                    report["em_andamento"] = entry
                    save(report_path, report)
                    resource = {"id": str(day), "name": day.strftime("%Y%m%d") + ".json",
                                "url": TJSC_SEARCH, "last_modified": now(), "publication_day": str(day),
                                "chamber": chamber, "tipo": "janela_publicacao"}
                    store.catalog(f"tjsc-{chamber}-civil", {"fonte": TJSC_SEARCH, "tipo": "janela_publicacao"},
                                  [resource], complete_listing=False)
                    with connection(store.path) as db:
                        saved = dict(db.execute("SELECT * FROM resources WHERE id=?", (entry["recurso"],)).fetchone())
                    try:
                        content, rows = fetch(http, config, chamber, day)
                        counts = store.ingest(saved, content, rows, run)
                    except Exception as exc:
                        store.failure(entry["recurso"], run, str(exc))
                        raise
                    event = {"camara": chamber, "dia": str(day), "registros": len(rows), **counts, "fim": now()}
                    report["eventos"].append(event)
                    report.pop("em_andamento", None)
                    save(report_path, report)
                    print(json.dumps({"concluidas_nesta_execucao": len(report["eventos"]),
                                      "total_planejado": len(work["pendentes"]), **event}, ensure_ascii=True), flush=True)
            report["status"] = "ok"
        except BaseException as exc:
            report.update(status="interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "error",
                          erro=f"{type(exc).__name__}: {exc}", codigo=getattr(exc, "code", "erro_fonte"))
            raise
        finally:
            report.update(fim=now(), depois=groups(store))
            store.finish_run(run, report["status"], report)
            from flora_mcp.publication import MANIFEST, publish
            if (store.directory / MANIFEST).exists():
                report["publicacao"] = publish(store)
            save(report_path, report)
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--inicio", required=True)
    parser.add_argument("--fim", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    if args.apply and (not args.report or not args.backup):
        parser.error("Aplicação exige --report e --backup novos.")
    config = load_config(data_dir=args.data_dir)
    store = Store(config.data_dir)
    start, end = date.fromisoformat(args.inicio), date.fromisoformat(args.fim)
    if args.apply:
        result = execute(config, store, start, end, args.report, args.backup)
        print(json.dumps({"status": result["status"], "janelas": len(result["eventos"]),
                          "depois": result["depois"], "report": str(args.report)}, ensure_ascii=True), flush=True)
    else:
        print(json.dumps(plan(store, start, end), ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
