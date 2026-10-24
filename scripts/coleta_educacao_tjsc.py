"""Coleta de educação no TJSC por consulta de tema, em três fases; o padrão só mostra o plano.

Decisões do operador de 23/10/2026: as 1ª a 5ª Câmaras de Direito Público e o Grupo de Câmaras de
Direito Público entram só assim, um subtema por vez, com filtro de ingestão (flora_mcp.tema) e
amostra julgada antes de qualquer gravação.

  candidatos  lê o portal (pausa configurada, sem paralelo) e grava cada consulta, com o original
              e a decisão do filtro, numa pasta de preparo fora do acervo; retoma o que falta.
  amostra     sorteia 50 dos que passam no filtro e grava o arquivo cego (tema e ementas, sob
              código) e, à parte, a chave dos códigos.
  aplicar     com o julgamento da amostra (90% ou mais no tema), adquire a trava, faz backup,
              ingere cada consulta com os que passam (os demais ficam como rejeitados, com o
              motivo), publica e grava o recibo. Nova execução não repete consulta concluída.
"""

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

from filelock import FileLock

from flora_mcp import backups
from flora_mcp.config import load_config
from flora_mcp.model import now
from flora_mcp.sources import client
from flora_mcp.store import Store, connection
from flora_mcp.tema import educacao
from flora_mcp.tjsc import catalog_search, collect_search, term_slug
from flora_mcp.tjsc_orgaos import PUBLICO, dataset

sys.path.insert(0, str(Path(__file__).parent))
from resume_tjsc import groups, save  # noqa: E402

TERMOS = (
    "creche",
    "pré-escola",
    "transporte escolar",
    "segundo professor",
    "professor auxiliar",
    "acompanhante terapêutico",
    "matrícula",
    "vaga escolar",
    "educação especial",
    "educação inclusiva",
    "ensino",
    "escola",
)
AMOSTRA, MINIMO = 50, 0.9
TEMA = (
    "Direito à educação: acesso, permanência e condições de ensino da criança, do adolescente e da "
    "pessoa com deficiência (vaga em creche e pré-escola, matrícula, transporte escolar, professor de "
    "apoio ou acompanhante, educação especial e inclusiva, ensino superior quando o objeto é o "
    "próprio direito ao ensino). Fora do tema: servidor público do magistério (piso, carreira, "
    "vencimentos), contrato com instituição de ensino que só discute cobrança ou consumo sem direito "
    "ao ensino, registro de imóvel (matrícula imobiliária) e qualquer outra matéria."
)


def consultas(inicio: date, fim: date) -> list[dict]:
    return [
        {"orgao": o, "termo": t, "inicio": inicio, "fim": fim, "arquivo": f"{dataset(o)}/{term_slug(t)}.json"}
        for o in PUBLICO
        for t in TERMOS
    ]


def gravar(path: Path, payload: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def candidatos(config, preparo: Path, todas: list[dict]):
    """Lê do portal cada consulta ainda ausente do preparo; para na primeira falha de fonte."""
    pendentes = [c for c in todas if not (preparo / c["arquivo"]).exists()]
    with client() as http:
        for n, c in enumerate(pendentes, 1):
            content, rows = collect_search(http, config, c["orgao"], c["termo"], c["inicio"], c["fim"])
            itens = [{"body": body, "raw": raw, "motivo": educacao(body["ementa"])} for body, raw in rows]
            envelope = preparo / c["arquivo"].replace(".json", ".envelope.json")
            gravar(envelope, content)
            registro = {
                "orgao": c["orgao"],
                "termo": c["termo"],
                "inicio": c["inicio"].isoformat(),
                "fim": c["fim"].isoformat(),
                "coletado_em": now(),
                "envelope_sha256": hashlib.sha256(content).hexdigest(),
                "itens": itens,
            }
            gravar(preparo / c["arquivo"], json.dumps(registro, ensure_ascii=False).encode())
            passam = sum(bool(i["motivo"]) for i in itens)
            print(
                json.dumps(
                    {
                        "feitas": n,
                        "de": len(pendentes),
                        **{k: c[k] for k in ("orgao", "termo")},
                        "acordaos": len(itens),
                        "passam": passam,
                    },
                    ensure_ascii=True,
                ),
                flush=True,
            )


def ler_preparo(preparo: Path, todas: list[dict]) -> list[dict]:
    faltam = [c["arquivo"] for c in todas if not (preparo / c["arquivo"]).exists()]
    if faltam:
        raise ValueError(f"Preparo incompleto: faltam {len(faltam)} consultas; rode candidatos.")
    registros = []
    for c in todas:
        registro = json.loads((preparo / c["arquivo"]).read_text(encoding="utf-8"))
        envelope = (preparo / c["arquivo"].replace(".json", ".envelope.json")).read_bytes()
        if hashlib.sha256(envelope).hexdigest() != registro["envelope_sha256"]:
            raise ValueError(f"Envelope alterado: {c['arquivo']}.")
        registros.append({**registro, "arquivo": c["arquivo"], "envelope": envelope})
    return registros


def resumo(registros: list[dict]) -> dict:
    vistos, passam = {}, {}
    for r in registros:
        for i in r["itens"]:
            vistos[i["body"]["id"]] = i
            if i["motivo"]:
                passam[i["body"]["id"]] = i
    return {"consultas": len(registros), "acordaos_unicos": len(vistos), "passam_unicos": len(passam)}, passam


def amostra(registros, semente: int, saida: Path, chave: Path) -> dict:
    _, passam = resumo(registros)
    ordem = sorted(passam, key=lambda i: hashlib.sha256(f"{semente}:{i}".encode()).hexdigest())[:AMOSTRA]
    codigos = {f"e{n:02d}": i for n, i in enumerate(ordem, 1)}
    cego = {
        "schema": "flora-amostra-tema-1",
        "tema": TEMA,
        "instrucao": "Para cada ementa, responda no_tema true ou false e uma frase de razão.",
        "itens": [{"codigo": k, "ementa": passam[i]["body"]["ementa"]} for k, i in codigos.items()],
    }
    for path, value in ((saida, cego), (chave, {"semente": semente, "codigos": codigos})):
        if path.exists():
            raise ValueError(f"Arquivo já existe: {path}.")
        path.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"amostra": len(codigos), "semente": semente}


def aprovar(julgamento: Path, chave: Path) -> dict:
    juizo = json.loads(julgamento.read_text(encoding="utf-8"))
    codigos = json.loads(chave.read_text(encoding="utf-8"))["codigos"]
    faltam = sorted(set(codigos) - set(juizo))
    if faltam:
        raise ValueError(f"Julgamento incompleto: faltam {faltam}.")
    no_tema = sum(bool(juizo[k]["no_tema"]) for k in codigos)
    taxa = no_tema / len(codigos)
    fora = [{"id": codigos[k], **juizo[k]} for k in codigos if not juizo[k]["no_tema"]]
    if taxa < MINIMO:
        raise ValueError(f"Amostra reprovada: {no_tema} de {len(codigos)} no tema ({taxa:.0%}).")
    return {"no_tema": no_tema, "de": len(codigos), "taxa": round(taxa, 3), "fora_do_tema": fora}


def ingerir(store, registro, run) -> dict:
    inicio, fim = date.fromisoformat(registro["inicio"]), date.fromisoformat(registro["fim"])
    resource_id = catalog_search(store, registro["orgao"], registro["termo"], inicio, fim)
    with connection(store.path) as db:
        saved = dict(db.execute("SELECT * FROM resources WHERE id=?", (resource_id,)).fetchone())
    rows = [(i["body"], i["raw"]) for i in registro["itens"] if i["motivo"]]
    rejected = [
        {"posicao": n, "id": i["body"]["id"], "motivo": "fora_do_tema: educacao"}
        for n, i in enumerate(registro["itens"])
        if not i["motivo"]
    ]
    counts = store.ingest(
        saved, registro["envelope"], rows, run, observed_at=registro["coletado_em"], rejected=rejected
    )
    return {
        "recurso": resource_id,
        "acordaos": len(registro["itens"]),
        "ingeridos": len(rows),
        "rejeitados": len(rejected),
        **counts,
    }


def concluidas(store) -> set:
    with connection(store.path) as db:
        return {
            r[0] for r in db.execute("SELECT id FROM resources WHERE status='ok' AND id LIKE 'tjsc-%:tema-%'")
        }


def aplicar(config, store, registros, aprovacao, report_path: Path, backup_root=None) -> dict:
    backup_root = Path(backup_root or backups.default_root(store.directory)).resolve()
    if report_path.exists():
        raise ValueError("Use novo recibo de execução; recibos anteriores são preservados.")
    with FileLock(str(store.directory / "collector.lock"), timeout=0):
        feitas = concluidas(store)
        pendentes = [
            r
            for r in registros
            if f"{dataset(r['orgao'])}:tema-{term_slug(r['termo'])}-{r['inicio']}-{r['fim']}" not in feitas
        ]
        report = {
            "inicio": now(),
            "banco": str(store.path),
            "amostra": aprovacao,
            "resumo": resumo(registros)[0],
            "pendentes": len(pendentes),
            "antes": groups(store),
            "status": "preparado",
            "eventos": [],
        }
        save(report_path, report)
        if not pendentes:
            report.update(status="ok", fim=now(), depois=report["antes"])
            save(report_path, report)
            return report
        report["backup"] = backups.create(store, backup_root, "antes-coleta-educacao-tjsc")
        run = store.start_run("TJSC-tema")
        report.update(execucao=run, status="running")
        try:
            for registro in pendentes:
                report["eventos"].append(ingerir(store, registro, run))
                save(report_path, report)
            report["status"] = "ok"
        except BaseException as exc:
            report.update(status="error", erro=f"{type(exc).__name__}: {exc}")
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
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("fase", choices=("plano", "candidatos", "amostra", "aplicar"))
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--preparo", type=Path, required=True, help="Pasta fora do acervo")
    parser.add_argument("--inicio", default="2022-01-01")
    parser.add_argument("--fim", default=date.today().isoformat())
    parser.add_argument("--semente", type=int)
    parser.add_argument("--amostra", type=Path, help="Arquivo cego da amostra")
    parser.add_argument("--chave", type=Path, help="Chave dos códigos da amostra")
    parser.add_argument("--julgamento", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    config = load_config(data_dir=args.data_dir)
    store = Store(config.data_dir)
    preparo = args.preparo.resolve()
    if preparo.is_relative_to(store.directory.resolve()):
        parser.error("O preparo fica fora do acervo.")
    todas = consultas(date.fromisoformat(args.inicio), date.fromisoformat(args.fim))
    if args.fase == "plano":
        prontas = sum((preparo / c["arquivo"]).exists() for c in todas)
        print(json.dumps({"consultas": len(todas), "no_preparo": prontas}, ensure_ascii=True))
    elif args.fase == "candidatos":
        candidatos(config, preparo, todas)
        print(json.dumps(resumo(ler_preparo(preparo, todas))[0], ensure_ascii=True))
    elif args.fase == "amostra":
        if args.semente is None or not args.amostra or not args.chave:
            parser.error("amostra exige --semente, --amostra e --chave.")
        print(json.dumps(amostra(ler_preparo(preparo, todas), args.semente, args.amostra, args.chave)))
    else:
        if not (args.julgamento and args.chave and args.report):
            parser.error("aplicar exige --julgamento, --chave e --report novo.")
        aprovacao = aprovar(args.julgamento, args.chave)
        result = aplicar(
            config, store, ler_preparo(preparo, todas), aprovacao, args.report.resolve(), args.backup
        )
        print(json.dumps({"status": result["status"], "eventos": len(result["eventos"])}, ensure_ascii=True))


if __name__ == "__main__":
    main()
