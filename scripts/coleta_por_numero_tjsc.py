"""Coleta dirigida do TJSC por número de processo; padrão é plano sem escrita nem rede.

Cada número é um recurso próprio (dataset tjsc-processo) com todos os acórdãos que o portal
devolve para ele, de qualquer órgão. Número sem resultado entra como consulta concluída com zero
documentos: é a prova de que a fonte não o ofereceu. Execução sequencial, na pausa configurada;
para na primeira falha de fonte, e a próxima execução retoma só o que não está concluído.
"""

import argparse
import json
from pathlib import Path

from flora_mcp.coleta_numeros import collect_one, execute, plan
from flora_mcp.config import load_config
from flora_mcp.model import FloraError
from flora_mcp.store import Store
from flora_mcp.tjsc import portal_number, process_key

__all__ = ["collect_one", "entries_from", "execute", "main", "plan"]


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
