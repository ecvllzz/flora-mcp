"""Compact collection diagnostics, with lossless detail available explicitly."""

from collections import Counter

from .model import FloraError


def tribunal_for(dataset):
    if dataset.startswith("espelhos-de-acordaos-"):
        return "STJ"
    if dataset.startswith("tjsc-"):
        return "TJSC"
    return None


def filtered_resources(resources, tribunal=None, dataset=None):
    return [
        r
        for r in resources
        if (not dataset or r["dataset"] == dataset)
        and (not tribunal or tribunal_for(r["dataset"]) == tribunal)
    ]


def validate_filters(tribunal, dataset, detalhe):
    if tribunal is not None and tribunal not in {"STJ", "STF", "TJSC"}:
        raise FloraError("filtro_invalido", "Tribunal disponível: STJ, STF ou TJSC.")
    if dataset is not None and (not isinstance(dataset, str) or not dataset.strip()):
        raise FloraError("filtro_invalido", "Dataset deve ser um identificador não vazio.")
    if (tribunal or dataset) and detalhe != "recursos":
        raise FloraError("filtro_invalido", "Filtros tribunal/dataset são usados com detalhe=recursos.")


def summary(legacy):
    result = {k: v for k, v in legacy.items() if k not in {"recursos", "execucoes_recentes"}}
    groups = {}
    for resource in legacy["recursos"]:
        dataset = resource["dataset"]
        group = groups.setdefault(
            dataset,
            {
                "tribunal": tribunal_for(dataset),
                "dataset": dataset,
                "total": 0,
                "por_status": Counter(),
                "pendentes": 0,
                "primeiro_lote_pendente": None,
                "ultimo_lote_pendente": None,
                "erros": Counter(),
            },
        )
        group["total"] += 1
        group["por_status"][resource["status"]] += 1
        if resource["pendente"] or resource["status"] == "pending":
            group["pendentes"] += 1
            name = resource["name"]
            group["primeiro_lote_pendente"] = min(group["primeiro_lote_pendente"] or name, name)
            group["ultimo_lote_pendente"] = max(group["ultimo_lote_pendente"] or name, name)
        if resource.get("error"):
            group["erros"][resource["error"]] += 1
    result["recursos"] = [{k: v for k, v in group.items() if k != "erros" or v} for group in groups.values()]
    result["execucoes_recentes"] = []
    for run in legacy["execucoes_recentes"]:
        compact = {k: v for k, v in run.items() if k != "detail"}
        detail = run["detail"]
        # Keep explicit reasons/failures and recorded before/after totals verbatim.
        compact["detail"] = {
            k: detail[k]
            for k in ("motivo", "falhas", "erro", "error", "antes", "depois", "modo")
            if k in detail and (k != "falhas" or detail[k])
        }
        result["execucoes_recentes"].append(compact)
    result["detalhe"] = "resumo"
    result["detalhes_disponiveis"] = {
        "completo": "Resposta integral anterior, incluindo eventos e janelas.",
        "recursos": "Lista paginada; filtros opcionais tribunal e dataset.",
        "execucoes": "Execuções com detail integral; use limite=1 e proximo_cursor.",
    }
    return result
