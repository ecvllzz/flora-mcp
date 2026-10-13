"""Coleta dirigida do TJSC por número de processo; padrão é plano sem escrita nem rede.

Cada número é um recurso próprio (dataset tjsc-processo) com todos os acórdãos que o portal
devolve para ele, de qualquer órgão. Número sem resultado entra como consulta concluída com zero
documentos: é a prova de que a fonte não o ofereceu. Execução sequencial, na pausa configurada;
para na primeira falha de fonte, e a próxima execução retoma só o que não está concluído.
"""

import argparse
import json
import sys
from pathlib import Path

from filelock import FileLock

from flora_mcp import backups
from flora_mcp.config import load_config
from flora_mcp.model import FloraError, now
from flora_mcp.sources import client
from flora_mcp.store import Store, connection
from flora_mcp.tjsc import PROCESSO_DATASET, catalog_process, collect_process, portal_number, process_key

# Atomic receipt writing and the before/after groups are the ones of the window resumption.
sys.path.insert(0, str(Path(__file__).parent))
from resume_tjsc import groups, save  # noqa: E402


def entries_from(insumos: Path | None, numbers: list[str]) -> tuple[list[dict], list[dict]]:
    """Numbers to search, merged by key with every origin that asked for them, and the refused."""
    asked = []
    if insumos:
        data = json.loads(Path(insumos).read_text(encoding="utf-8"))
        if data.get("schema") != "flora-r1-insumos-1":
            raise ValueError("Insumos fora do esquema flora-r1-insumos-1.")
        for item in data["biblioteca_fora_do_acervo"]:
            if item["tribunal"] == "TJSC":
                asked.append((item["numero"], "biblioteca:" + item["id"]))
        for item in data["mais_citados_ausentes"]:
            if item["chave"].startswith("TJSC:"):
                asked.append((item["chave"][5:], f"citado:{item['citado_por']}"))
    asked.extend((value, "linha_de_comando") for value in numbers)
    merged, refused = {}, []
    for value, origin in asked:
        try:
            key = process_key(value)
        except FloraError as exc:
            refused.append({"numero_informado": value, "origem": origin, "motivo": str(exc)})
            continue
        entry = merged.setdefault(key, {"chave": key, "numero": portal_number(key), "origens": []})
        entry["origens"].append(origin)
    return list(merged.values()), refused


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


def execute(config, store, entries, refused, report_path, backup_root=None, *, collect=collect_one):
    report_path = Path(report_path).resolve()
    backup_root = Path(backup_root or backups.default_root(store.directory)).resolve()
    if backup_root.is_relative_to(store.directory.resolve()):
        raise ValueError("Backup deve ficar fora do acervo.")
    if report_path.exists():
        raise ValueError("Use novo recibo de execução; recibos anteriores são preservados.")
    with FileLock(str(store.directory / "collector.lock"), timeout=0):
        store.initialize()
        work = plan(store, entries)
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
        save(report_path, report)
        if not work["pendentes"]:
            report.update(status="ok", fim=now(), depois=report["antes"])
            save(report_path, report)
            return report
        report["backup"] = backups.create(store, backup_root, "antes-coleta-por-numero-tjsc")
        run = store.start_run("TJSC-processo")
        report.update(execucao=run, status="running")
        save(report_path, report)
        try:
            with client() as http:
                for entry in work["pendentes"]:
                    report["em_andamento"] = entry
                    event = collect(config, store, http, entry, run)
                    report["eventos"].append(event)
                    report.pop("em_andamento", None)
                    save(report_path, report)
                    print(
                        json.dumps(
                            {
                                "feitos": len(report["eventos"]),
                                "de": len(work["pendentes"]),
                                "numero": entry["numero"],
                                "registros": event["registros"],
                            }
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
            report["nao_oferecidos"] = [
                {"numero": e["numero"], "origens": e["origens"]}
                for e in report["eventos"]
                if not e["registros"]
            ]
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
    parser.add_argument("--insumos", type=Path, help="Arquivo flora-r1-insumos-1")
    parser.add_argument("--numero", action="append", default=[], help="Número avulso; repita para mais")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--backup", type=Path, help="Raiz dos backups; padrão <acervo>-backups")
    args = parser.parse_args()
    if args.apply and not args.report:
        parser.error("Aplicação exige --report novo.")
    if not args.insumos and not args.numero:
        parser.error("Informe --insumos ou --numero.")
    entries, refused = entries_from(args.insumos, args.numero)
    config = load_config(data_dir=args.data_dir)
    store = Store(config.data_dir)
    if args.apply:
        result = execute(config, store, entries, refused, args.report, args.backup)
        summary = {
            "status": result["status"],
            "consultas": len(result["eventos"]),
            "report": str(args.report),
        }
        print(json.dumps(summary, ensure_ascii=True), flush=True)
    else:
        work = plan(store, entries)
        print(
            json.dumps({**work, "pendentes": len(work["pendentes"]), "recusados": refused}, ensure_ascii=True)
        )


if __name__ == "__main__":
    main()
