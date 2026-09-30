"""Factual reason for an empty page: coverage, filters or terms. Never rewrites the query."""


def _intersects(interval, start, end):
    return (
        interval["inicio"] is not None
        and (not end or interval["inicio"] <= end)
        and (not start or interval["fim"] >= start)
    )


def empty_reason(*, dates, intervals, filtered, unfiltered_total, term_counts):
    """Callables are evaluated only when their rule is reached, in contract order.

    intervals() lists the loaded groups that satisfy the tribunal and organ filters, with the
    date range of the requested kind; unfiltered_total() counts the same terms without any
    filter; term_counts() returns [{termo, documentos}] or None (advanced mode).
    """
    start, end = dates
    if start or end:
        loaded = intervals()
        if not any(_intersects(i, start, end) for i in loaded):
            return {"motivo": "fora_da_cobertura", "intervalos_carregados": loaded}
    if filtered:
        total = unfiltered_total()
        if total:
            return {"motivo": "filtro_restritivo", "total_sem_filtros": total}
    result = {"motivo": "sem_correspondencia"}
    counts = term_counts()
    if counts is not None:
        result["termos"] = counts
        result["termos_sem_ocorrencia"] = [c["termo"] for c in counts if not c["documentos"]]
    return result
