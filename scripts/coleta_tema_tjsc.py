"""Coleta de um tema no TJSC por consulta, em três fases; o padrão só mostra o plano.

Cada tema (educação, família e sucessões) vem do registro de flora_mcp.tema, com órgãos, subtemas,
período, filtro de ingestão e texto do tema para o julgamento da amostra. Decisões do operador de
23/10/2026 (educação: as Câmaras de Direito Público entram só assim) e de 24/10/2026 (família e
sucessões nas Câmaras de Direito Civil, publicação de 2022 e 2023, só o mérito): um subtema por vez,
com filtro e amostra julgada antes de qualquer gravação.

  candidatos  lê o portal (pausa configurada, sem paralelo) e grava cada consulta, com o original
              e a decisão do filtro, numa pasta de preparo fora do acervo; retoma o que falta.
  reler       refaz cada consulta do preparo a partir das páginas originais do envelope, com a
              leitura atual, sem ir ao portal; recusa diferença que não seja só de espaços.
  amostra     sorteia 50 dos que passam no filtro e grava o arquivo cego (tema e ementas, sob
              código) e, à parte, a chave dos códigos.
  aplicar     com o julgamento da amostra (90% ou mais no tema), adquire a trava, faz backup,
              ingere cada consulta com os que passam (os demais ficam como rejeitados, com o
              motivo), publica e grava o recibo. Nova execução não repete consulta concluída.
  corrigir    depois de reler, regrava só as consultas concluídas cujo acórdão gravado difere da
              releitura, com os mesmos acórdãos no filtro e diferença só de espaços: trava,
              backup, nova versão (a anterior fica no histórico), publicação e recibo com o
              diff de cada ementa.
"""

import argparse
import base64
import difflib
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

from filelock import FileLock

from flora_mcp import backups
from flora_mcp.config import load_config
from flora_mcp.model import canonical, digest, now
from flora_mcp.sources import client
from flora_mcp.publication import plan_text_copies
from flora_mcp.store import Store, connection
from flora_mcp.tema import TEMAS, Tema
from flora_mcp.tjsc import catalog_search, collect_search, parse_period_page, term_slug
from flora_mcp.tjsc_orgaos import dataset

sys.path.insert(0, str(Path(__file__).parent))
from resume_tjsc import groups, save  # noqa: E402

AMOSTRA, MINIMO = 50, 0.9


def consultas(tema: Tema, inicio: date, fim: date) -> list[dict]:
    return [
        {"orgao": o, "termo": t, "inicio": inicio, "fim": fim, "arquivo": f"{dataset(o)}/{term_slug(t)}.json"}
        for o in tema.orgaos
        for t in tema.termos
    ]


def gravar(path: Path, payload: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def candidatos(config, preparo: Path, todas: list[dict], tema: Tema):
    """Lê do portal cada consulta ainda ausente do preparo; para na primeira falha de fonte."""
    pendentes = [c for c in todas if not (preparo / c["arquivo"]).exists()]
    with client() as http:
        for n, c in enumerate(pendentes, 1):
            content, rows = collect_search(http, config, c["orgao"], c["termo"], c["inicio"], c["fim"])
            itens = [{"body": body, "raw": raw, "motivo": tema.filtro(body["ementa"])} for body, raw in rows]
            envelope = preparo / c["arquivo"].replace(".json", ".envelope.json")
            gravar(envelope, content)
            registro = {
                "tema": tema.nome,
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


def ler_preparo(preparo: Path, todas: list[dict], tema: Tema) -> list[dict]:
    faltam = [c["arquivo"] for c in todas if not (preparo / c["arquivo"]).exists()]
    if faltam:
        raise ValueError(f"Preparo incompleto: faltam {len(faltam)} consultas; rode candidatos.")
    registros = []
    for c in todas:
        registro = json.loads((preparo / c["arquivo"]).read_text(encoding="utf-8"))
        # The education staging predates the field.
        if registro.get("tema", "educacao") != tema.nome:
            raise ValueError(f"Preparo de outro tema: {c['arquivo']}.")
        envelope = (preparo / c["arquivo"].replace(".json", ".envelope.json")).read_bytes()
        if hashlib.sha256(envelope).hexdigest() != registro["envelope_sha256"]:
            raise ValueError(f"Envelope alterado: {c['arquivo']}.")
        # The decision is the current filter's, not the one recorded at collection time.
        for item in registro["itens"]:
            item["motivo"] = tema.filtro(item["body"]["ementa"])
        registros.append({**registro, "arquivo": c["arquivo"], "envelope": envelope})
    return registros


def so_espacos(antes, depois) -> bool:
    """True when two parsed values differ, if at all, only in whitespace."""
    if isinstance(antes, dict) and isinstance(depois, dict):
        return antes.keys() == depois.keys() and all(so_espacos(antes[k], depois[k]) for k in antes)
    if isinstance(antes, str) and isinstance(depois, str):
        return "".join(antes.split()) == "".join(depois.split())
    return antes == depois


def reler(preparo: Path, todas: list[dict], tema: Tema) -> dict:
    """Each staged search read again from its own envelope pages with the current parser.

    The envelope is the portal's answer as received; the items are a reading of it. When the reading
    changes (the highlight of the searched term, 24/10/2026), the items follow it without a new
    request, and only a whitespace difference is accepted.
    """
    alteradas = acordaos = 0
    for c in todas:
        registro = next(r for r in ler_preparo(preparo, [c], tema))
        envelope = json.loads(registro["envelope"])
        lidos = {}
        for parte in envelope["partes"]:
            inicio, fim = (date.fromisoformat(parte[k]) for k in ("publicacao_inicio", "publicacao_fim"))
            for pagina in parte["paginas"]:
                _, rows = parse_period_page(base64.b64decode(pagina["bytes_base64"]), c["orgao"], inicio, fim)
                lidos.update((body["id"], (body, raw)) for body, raw in rows)
        itens = registro["itens"]
        if set(lidos) != {i["body"]["id"] for i in itens}:
            raise ValueError(f"Releitura com outros acórdãos: {c['arquivo']}.")
        novos = []
        for item in itens:
            body, raw = lidos[item["body"]["id"]]
            if not (so_espacos(item["body"], body) and so_espacos(item["raw"], raw)):
                raise ValueError(f"Releitura mudou mais que espaços: {item['body']['id']}.")
            acordaos += (body, raw) != (item["body"], item["raw"])
            novos.append({**item, "body": body, "raw": raw, "motivo": tema.filtro(body["ementa"])})
        if novos != itens:
            alteradas += 1
            gravado = json.loads((preparo / c["arquivo"]).read_text(encoding="utf-8"))
            gravado.update(itens=novos, relido_em=now())
            gravar(preparo / c["arquivo"], json.dumps(gravado, ensure_ascii=False).encode())
    return {"consultas": len(todas), "consultas_alteradas": alteradas, "acordaos_alterados": acordaos}


def resumo(registros: list[dict]) -> dict:
    vistos, passam = {}, {}
    for r in registros:
        for i in r["itens"]:
            vistos[i["body"]["id"]] = i
            if i["motivo"]:
                passam[i["body"]["id"]] = i
    return {"consultas": len(registros), "acordaos_unicos": len(vistos), "passam_unicos": len(passam)}, passam


def amostra(
    registros, tema: Tema, semente: int, saida: Path, chave: Path, excluir: tuple[Path, ...] = ()
) -> dict:
    """Sorteio dos que passam no filtro; os ids das chaves de amostras anteriores ficam de fora,
    para que um filtro apertado pela leitura de uma amostra não seja medido nela mesma."""
    _, passam = resumo(registros)
    vistos = {i for path in excluir for i in json.loads(path.read_text(encoding="utf-8"))["codigos"].values()}
    candidatos = [i for i in passam if i not in vistos]
    ordem = sorted(candidatos, key=lambda i: hashlib.sha256(f"{semente}:{i}".encode()).hexdigest())[:AMOSTRA]
    codigos = {f"e{n:02d}": i for n, i in enumerate(ordem, 1)}
    cego = {
        "schema": "flora-amostra-tema-1",
        "filtro": tema.versao,
        "tema": tema.texto,
        "instrucao": "Para cada ementa, responda no_tema true ou false e uma frase de razão.",
        "itens": [{"codigo": k, "ementa": passam[i]["body"]["ementa"]} for k, i in codigos.items()],
    }
    chave_valor = {"semente": semente, "filtro": tema.versao, "excluidos": len(vistos), "codigos": codigos}
    for path, value in ((saida, cego), (chave, chave_valor)):
        if path.exists():
            raise ValueError(f"Arquivo já existe: {path}.")
        path.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {
        "amostra": len(codigos),
        "semente": semente,
        "filtro": tema.versao,
        "passam": len(passam),
        "excluidos": len(vistos),
    }


def aprovar(julgamento: Path, chave: Path, tema: Tema) -> dict:
    juizo = json.loads(julgamento.read_text(encoding="utf-8"))
    chave_valor = json.loads(chave.read_text(encoding="utf-8"))
    if chave_valor["filtro"] != tema.versao:
        raise ValueError(f"A amostra mediu o filtro {chave_valor['filtro']}, não {tema.versao}.")
    codigos = chave_valor["codigos"]
    faltam = sorted(set(codigos) - set(juizo))
    if faltam:
        raise ValueError(f"Julgamento incompleto: faltam {faltam}.")
    no_tema = sum(bool(juizo[k]["no_tema"]) for k in codigos)
    taxa = no_tema / len(codigos)
    fora = [{"id": codigos[k], **juizo[k]} for k in codigos if not juizo[k]["no_tema"]]
    if taxa < MINIMO:
        raise ValueError(f"Amostra reprovada: {no_tema} de {len(codigos)} no tema ({taxa:.0%}).")
    return {"no_tema": no_tema, "de": len(codigos), "taxa": round(taxa, 3), "fora_do_tema": fora}


def ingerir(store, registro, run, tema: Tema) -> dict:
    inicio, fim = date.fromisoformat(registro["inicio"]), date.fromisoformat(registro["fim"])
    resource_id = catalog_search(store, registro["orgao"], registro["termo"], inicio, fim)
    with connection(store.path) as db:
        saved = dict(db.execute("SELECT * FROM resources WHERE id=?", (resource_id,)).fetchone())
    rows = [(i["body"], i["raw"]) for i in registro["itens"] if i["motivo"]]
    rejected = [
        {"posicao": n, "id": i["body"]["id"], "motivo": "fora_do_tema: " + tema.versao}
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


def recurso(registro) -> str:
    """Resource id of a staged search, as catalog_search names it."""
    chave = f"tema-{term_slug(registro['termo'])}-{registro['inicio']}-{registro['fim']}"
    return f"{dataset(registro['orgao'])}:{chave}"


def concluidas(store) -> set:
    with connection(store.path) as db:
        return {
            r[0] for r in db.execute("SELECT id FROM resources WHERE status='ok' AND id LIKE 'tjsc-%:tema-%'")
        }


def aplicar(config, store, registros, aprovacao, report_path: Path, tema: Tema, backup_root=None) -> dict:
    backup_root = Path(backup_root or backups.default_root(store.directory)).resolve()
    if report_path.exists():
        raise ValueError("Use novo recibo de execução; recibos anteriores são preservados.")
    with FileLock(str(store.directory / "collector.lock"), timeout=0):
        feitas = concluidas(store)
        pendentes = [r for r in registros if recurso(r) not in feitas]
        report = {
            "inicio": now(),
            "banco": str(store.path),
            "tema": tema.nome,
            "amostra": aprovacao,
            "filtro": tema.versao,
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
        report["backup"] = backups.create(store, backup_root, tema.rotulo_backup)
        run = store.start_run("TJSC-tema")
        report.update(execucao=run, status="running")
        try:
            for registro in pendentes:
                report["eventos"].append(ingerir(store, registro, run, tema))
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


def divergentes(db, registro) -> list[str]:
    """Ids whose staged reading is not the version this concluded search holds; refuses a search whose
    acórdãos in the filter are not the ones it holds."""
    gravados = dict(
        db.execute(
            "SELECT document_id,hash FROM observations WHERE resource_id=?", (recurso(registro),)
        ).fetchall()
    )
    passam = {i["body"]["id"]: i for i in registro["itens"] if i["motivo"]}
    if set(passam) != set(gravados):
        raise ValueError(f"Outros acórdãos no filtro que os gravados: {recurso(registro)}.")
    return [i for i, item in passam.items() if digest(canonical(item["raw"]).encode()) != gravados[i]]


def ementas(db, ids) -> dict:
    marcas = ",".join("?" * len(ids))
    rows = db.execute(f"SELECT id,body FROM documents WHERE id IN ({marcas})", list(ids)).fetchall()
    return {r[0]: json.loads(r[1])["ementa"] for r in rows}


def copias(db, ids) -> dict:
    """Text-copy group of each id (its first id), over every document, as the publication applies it."""
    grupos = plan_text_copies((r[0], json.loads(r[1])) for r in db.execute("SELECT id,body FROM documents"))
    primeiro = {c["id"]: k for k, itens in grupos.items() for c in itens} | {k: k for k in grupos}
    return {i: primeiro.get(i) for i in ids}


def alteracao(antes: str, depois: str) -> dict:
    """Character diff of one ementa: what changed, where, and whether it is only whitespace."""
    trechos = [
        {"antes": antes[a:b], "depois": depois[c:d], "contexto": depois[max(0, c - 30) : d + 10]}
        for op, a, b, c, d in difflib.SequenceMatcher(None, antes, depois, autojunk=False).get_opcodes()
        if op != "equal"
    ]
    return {
        "caracteres_alterados": sum(len(t["antes"]) + len(t["depois"]) for t in trechos),
        "so_espacos": so_espacos(antes, depois),
        "trechos": trechos,
    }


def corrigir(config, store, registros, report_path: Path, tema: Tema, backup_root=None) -> dict:
    backup_root = Path(backup_root or backups.default_root(store.directory)).resolve()
    if report_path.exists():
        raise ValueError("Use novo recibo de execução; recibos anteriores são preservados.")
    with FileLock(str(store.directory / "collector.lock"), timeout=0):
        feitas = concluidas(store)
        with connection(store.path) as db:
            alvo = {recurso(r): (r, divergentes(db, r)) for r in registros if recurso(r) in feitas}
            alvo = {k: v for k, v in alvo.items() if v[1]}
            ids = sorted({i for _, d in alvo.values() for i in d})
            antes, grupos_antes = ementas(db, ids), copias(db, ids)
        report = {
            "inicio": now(),
            "banco": str(store.path),
            "tema": tema.nome,
            "filtro": tema.versao,
            "correcao": "leitura do cartão sem o destaque do termo pesquisado (reler)",
            "consultas": len(alvo),
            "acordaos": len(ids),
            "antes": groups(store),
            "status": "preparado",
            "eventos": [],
        }
        save(report_path, report)
        if not alvo:
            report.update(status="ok", fim=now(), depois=report["antes"])
            save(report_path, report)
            return report
        report["backup"] = backups.create(
            store, backup_root, tema.rotulo_backup.replace("coleta", "correcao")
        )
        run = store.start_run("TJSC-tema-correcao")
        report.update(execucao=run, status="running")
        try:
            for registro, _ in alvo.values():
                report["eventos"].append(ingerir(store, registro, run, tema))
                save(report_path, report)
            with connection(store.path) as db:
                depois, grupos_depois = ementas(db, ids), copias(db, ids)
            report["documentos"] = [
                {"id": i, "copia_de_texto": grupos_depois[i], **alteracao(antes[i], depois[i])} for i in ids
            ]
            report["grupos_de_copia_iguais"] = grupos_antes == grupos_depois
            if not all(d["so_espacos"] for d in report["documentos"]) or not report["grupos_de_copia_iguais"]:
                raise ValueError("A correção mudou mais que espaços ou os grupos de cópia.")
            report["status"] = "ok"
        except BaseException as exc:
            report.update(status="error", erro=f"{type(exc).__name__}: {exc}")
            raise
        finally:
            report.update(fim=now(), depois=groups(store))
            store.finish_run(run, report["status"], report)
            from flora_mcp.publication import MANIFEST, publish

            if report["status"] == "ok" and (store.directory / MANIFEST).exists():
                report["publicacao"] = publish(store)
            save(report_path, report)
        return report


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("fase", choices=("plano", "candidatos", "reler", "amostra", "aplicar", "corrigir"))
    parser.add_argument("--tema", choices=sorted(TEMAS), required=True)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--preparo", type=Path, required=True, help="Pasta fora do acervo")
    parser.add_argument("--inicio", help="Padrão: o do tema")
    parser.add_argument("--fim", help="Padrão: o do tema, ou hoje")
    parser.add_argument("--semente", type=int)
    parser.add_argument("--amostra", type=Path, help="Arquivo cego da amostra")
    parser.add_argument("--chave", type=Path, help="Chave dos códigos da amostra")
    parser.add_argument(
        "--excluir-chave", type=Path, action="append", default=[], help="Chave de amostra anterior"
    )
    parser.add_argument("--julgamento", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    tema = TEMAS[args.tema]
    config = load_config(data_dir=args.data_dir)
    store = Store(config.data_dir)
    preparo = args.preparo.resolve()
    if preparo.is_relative_to(store.directory.resolve()):
        parser.error("O preparo fica fora do acervo.")
    inicio = date.fromisoformat(args.inicio or tema.inicio)
    fim = date.fromisoformat(args.fim or tema.fim or date.today().isoformat())
    todas = consultas(tema, inicio, fim)
    if args.fase == "plano":
        prontas = sum((preparo / c["arquivo"]).exists() for c in todas)
        print(
            json.dumps(
                {
                    "tema": tema.nome,
                    "inicio": inicio.isoformat(),
                    "fim": fim.isoformat(),
                    "consultas": len(todas),
                    "no_preparo": prontas,
                },
                ensure_ascii=True,
            )
        )
    elif args.fase == "corrigir":
        if not args.report:
            parser.error("corrigir exige --report novo.")
        result = corrigir(
            config, store, ler_preparo(preparo, todas, tema), args.report.resolve(), tema, args.backup
        )
        print(json.dumps({k: result[k] for k in ("status", "consultas", "acordaos")}, ensure_ascii=True))
    elif args.fase == "reler":
        print(json.dumps(reler(preparo, todas, tema), ensure_ascii=True))
    elif args.fase == "candidatos":
        candidatos(config, preparo, todas, tema)
        print(json.dumps(resumo(ler_preparo(preparo, todas, tema))[0], ensure_ascii=True))
    elif args.fase == "amostra":
        if args.semente is None or not args.amostra or not args.chave:
            parser.error("amostra exige --semente, --amostra e --chave.")
        print(
            json.dumps(
                amostra(
                    ler_preparo(preparo, todas, tema),
                    tema,
                    args.semente,
                    args.amostra,
                    args.chave,
                    tuple(args.excluir_chave),
                )
            )
        )
    else:
        if not (args.julgamento and args.chave and args.report):
            parser.error("aplicar exige --julgamento, --chave e --report novo.")
        aprovacao = aprovar(args.julgamento, args.chave, tema)
        result = aplicar(
            config,
            store,
            ler_preparo(preparo, todas, tema),
            aprovacao,
            args.report.resolve(),
            tema,
            args.backup,
        )
        print(json.dumps({"status": result["status"], "eventos": len(result["eventos"])}, ensure_ascii=True))


if __name__ == "__main__":
    main()
