"""Read admitted precedents without exposing their administrative history."""

import json
import sqlite3

from .ausencia import empty_reason
from .model import FloraError, canonical, digest, folded
from .precedents import COMPONENTS, SPECIES, available
from .query import (
    CONTRATO,
    block_offset,
    check_dates,
    compile_terms,
    database_error,
    date_filters,
    encode_cursor,
    fit_triage,
    lexical_terms,
    page_limit,
    page_offset,
    quoted,
    resolve_order,
)

MARK = chr(1)  # highlight() opening mark


def metadata(body, sha):
    return {
        k: body.get(k)
        for k in (
            "id",
            "tribunal",
            "especie",
            "numero",
            "orgao",
            "data_publicacao",
            "referencia",
            "referencia_completa",
            "referencia_pendencias",
            "situacao",
            "admissao",
            "tipo_publicacao",
        )
    } | {
        "hash_conteudo": sha,
        "componentes_disponiveis": list(body["componentes"]),
        "fontes": [{k: s.get(k) for k in ("url", "sha256", "coletado_em")} for s in body["fontes"]],
    }


class PrecedentSearch:
    """One search over admitted precedents: validated parameters, SQL plan and one page."""

    def __init__(self, view, termos, *, campo, detalhe, limite, ordenar, modo_busca):
        if campo not in {*COMPONENTS, "todos"}:
            raise FloraError("campo_indisponivel", "Precedentes: " + ", ".join(COMPONENTS) + ", todos.")
        self.view, self.termos, self.campo, self.detalhe = view, termos, campo, detalhe
        self.modo_busca = modo_busca
        self.limit = page_limit(detalhe, limite)
        self.query = compile_terms(termos, modo_busca)
        self.ordenar = resolve_order(ordenar, self.query)
        self.base, self.base_params = self.admitted(view)
        self.groups, self.filters, self.params = [], [], []
        self.offset = 0

    @staticmethod
    def admitted(view):
        filters, params = ["p.admission='admitido'"], []
        if view.withdrawn:
            filters.append("p.id NOT IN (SELECT value FROM json_each(?))")
            params.append(canonical(sorted(view.withdrawn)))
        if view.retired_versions:
            filters.append("(p.id || ':' || p.hash) NOT IN (SELECT value FROM json_each(?))")
            params.append(canonical(sorted(view.retired_versions)))
        return filters, params

    def restrict(self, *, tribunal, orgao, especie, numero, data_inicio, data_fim):
        # Tribunal and organ also delimit the loaded groups used by the empty-page reason.
        self.groups = [
            (c, v)
            for c, v in (("tribunal", tribunal and tribunal.upper()), ("organ", orgao and folded(orgao)))
            if v
        ]
        exact = self.groups + [(c, v) for c, v in (("species", especie), ("number", numero)) if v is not None]
        dated, dated_params = date_filters("p.publication", data_inicio, data_fim)
        self.filters = ["p." + column + "=?" for column, _ in exact] + dated
        self.params = [value for _, value in exact] + dated_params

    def scoped(self, expression):
        if not expression or self.campo == "todos":
            return expression
        return self.campo + " : (" + expression + ")"

    def plan(self, *, filtered=True, expression=None):
        expression = self.scoped(self.query) if expression is None else expression
        filters = self.base + (self.filters if filtered else [])
        params = self.base_params + (self.params if filtered else [])
        source = "precedents p JOIN precedent_texts t ON t.id=p.id"
        if expression:
            source += " JOIN precedent_search ON precedent_search.rowid=t.rowid"
            filters, params = filters + ["precedent_search MATCH ?"], params + [expression]
        return source, " AND ".join(filters), params

    def order(self):
        direction = "ASC" if self.ordenar == "mais_antigos" else "DESC"
        order = "p.publication IS NULL,p.publication " + direction + ",p.id"
        if self.ordenar == "relevancia":
            order = "bm25(precedent_search,3,1,3,0.5,0.5)," + order
        return order

    def count(self, db, **options):
        source, where, params = self.plan(**options)
        try:
            return db.execute(f"SELECT count(*) FROM {source} WHERE {where}", params).fetchone()[0]
        except sqlite3.OperationalError as exc:
            raise database_error(exc) from exc

    def page(self, db, cursor, revision):
        source, where, params = self.plan()
        order = self.order()
        fingerprint = digest(canonical([where, params, order, self.limit, self.detalhe, self.campo]).encode())
        self.offset = page_offset(self.view, cursor, fingerprint, revision)
        if not available(db):
            return 0, [], fingerprint
        total = self.count(db)
        # First highlighted position is an offset in the original Unicode string.
        highlights = (
            "".join(
                f",highlight(precedent_search,{i},char(1),char(2)) AS h{i}" for i in range(len(COMPONENTS))
            )
            if self.query
            else ""
        )
        try:
            rows = db.execute(
                f"SELECT p.body,p.hash{highlights} FROM {source} WHERE {where} ORDER BY {order} LIMIT ? "
                f"OFFSET ?",
                (*params, self.limit, self.offset),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            raise database_error(exc) from exc
        return total, rows, fingerprint

    def item(self, row):
        body = json.loads(row["body"])
        item = metadata(body, row["hash"])
        if self.detalhe == "completo":
            item["componentes"] = body["componentes"]
            item["julgados_relacionados"] = body.get("julgados_relacionados", [])
            return item
        matches = [c for i, c in enumerate(COMPONENTS) if self.query and MARK in row[f"h{i}"]]
        component = matches[0] if matches else next(iter(body["componentes"]))
        full = body["componentes"][component]
        start = max(0, row[f"h{COMPONENTS.index(component)}"].find(MARK) - 80) if matches else 0
        snippet = full[start : start + 400]
        item.update(
            componente=component,
            campos_correspondentes=matches,
            trecho=snippet,
            offset=start,
            trecho_parcial=start > 0 or len(snippet) < len(full),
            sha256_componente=digest(full.encode()),
        )
        return item

    def intervals(self, db):
        source, where, params = self.plan(filtered=False, expression="")
        where += "".join(f" AND p.{column}=?" for column, _ in self.groups)
        return [
            dict(r)
            for r in db.execute(
                f"SELECT p.tribunal,json_extract(p.body,'$.orgao') AS orgao,min(p.publication) AS inicio,"
                f"max(p.publication) AS fim FROM {source} WHERE {where} GROUP BY p.tribunal,p.organ "
                "ORDER BY p.tribunal,p.organ",
                params + [value for _, value in self.groups],
            )
        ]

    def term_counts(self, db):
        if self.modo_busca != "simples":
            return None
        return [
            {"termo": t, "documentos": self.count(db, filtered=False, expression=self.scoped(quoted(t)))}
            for t in lexical_terms(self.termos)
        ]

    def reason(self, db, dates):
        loaded = available(db)
        try:
            return empty_reason(
                dates=dates,
                intervals=lambda: self.intervals(db) if loaded else [],
                filtered=bool(self.filters),
                unfiltered_total=lambda: self.count(db, filtered=False) if loaded else 0,
                term_counts=lambda: self.term_counts(db) if loaded else None,
            )
        except sqlite3.OperationalError as exc:
            raise database_error(exc) from exc


def search(
    store,
    *,
    termos="",
    tribunal=None,
    orgao=None,
    especie=None,
    numero=None,
    campo="todos",
    ordenar=None,
    limite=None,
    cursor=None,
    detalhe="triagem",
    data_inicio=None,
    data_fim=None,
    modo_busca="simples",
):
    plan = PrecedentSearch(
        store, termos, campo=campo, detalhe=detalhe, limite=limite, ordenar=ordenar, modo_busca=modo_busca
    )
    if tribunal and tribunal.upper() not in SPECIES:
        raise FloraError("tribunal_invalido", "Tribunal suportado: STJ, STF ou TJSC.")
    if especie and especie not in set.union(*SPECIES.values()):
        raise FloraError("filtro_invalido", "Espécie fora do contrato.")
    check_dates(data_inicio, data_fim)
    plan.restrict(
        tribunal=tribunal,
        orgao=orgao,
        especie=especie,
        numero=numero,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )
    with store.read() as db:
        db.execute("BEGIN")
        revision = db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]
        total, rows, fingerprint = plan.page(db, cursor, revision)
        reason = plan.reason(db, (data_inicio, data_fim)) if total == 0 else {}

    def following(n):
        return encode_cursor(store, {"consulta": fingerprint, "revisao": revision, "offset": plan.offset + n})

    result = {
        "status": "ok",
        "contrato": CONTRATO,
        "total_encontrado": total,
        "resultados": [plan.item(row) for row in rows],
        "campo_pesquisado": campo,
        "modo_busca": modo_busca,
        "consulta_efetiva": plan.scoped(plan.query),
        "ordenacao": plan.ordenar,
        "revisao_base": revision,
        "detalhe": detalhe,
        "proximo_cursor": following(len(rows)) if plan.offset + len(rows) < total else None,
        "cobertura": {"integral": False, "aviso": "Busca limitada aos precedentes admitidos no acervo."},
        **reason,
    }
    if detalhe == "triagem":
        fit_triage(result, following)
    if total == 0:
        result["ausencia"] = "Nenhum precedente admitido corresponde à consulta e aos filtros nesta base."
    return result


def document(store, id, componente="enunciado", cursor=None, tamanho_bloco=16000, hash_conteudo=None):
    if id in store.withdrawn:
        raise FloraError("documento_nao_encontrado", "Precedente retirado do uso ativo.")
    if not 100 <= tamanho_bloco <= 32000:
        raise FloraError("limite_invalido", "Blocos devem ter entre 100 e 32000 caracteres.")
    with store.read() as db:
        row = (
            db.execute("SELECT * FROM precedents WHERE id=? AND admission='admitido'", (id,)).fetchone()
            if available(db)
            else None
        )
    if not row:
        raise FloraError("documento_nao_encontrado", "Precedente ausente ou não admitido para uso.")
    if id + ":" + row["hash"] in store.retired_versions:
        raise FloraError("versao_retirada", "Versão retirada do uso ativo.")
    if hash_conteudo and hash_conteudo != row["hash"]:
        raise FloraError("versao_indisponivel", "Versão não disponível nesta publicação.")
    body = json.loads(row["body"])
    components = body["componentes"]
    if componente not in components:
        raise FloraError("componente_indisponivel", "Componentes disponíveis: " + ", ".join(components))
    text = components[componente]
    offset = block_offset(store, cursor, id, componente, row["hash"], len(text))
    block = text[offset : offset + tamanho_bloco]
    following = offset + len(block)
    result = {
        "status": "ok",
        "contrato": CONTRATO,
        "id": id,
        "componente": componente,
        "texto": block,
        "offset": offset,
        "total_caracteres": len(text),
        "parcial": offset > 0 or following < len(text),
        "fim": following == len(text),
        "hash_conteudo": row["hash"],
        "sha256_texto_completo": digest(text.encode()),
        "referencia": body.get("referencia"),
        "referencia_pendencias": body.get("referencia_pendencias"),
        "proximo_cursor": encode_cursor(
            store, {"id": id, "componente": componente, "hash": row["hash"], "offset": following}
        )
        if following < len(text)
        else None,
    }
    if offset == 0:
        # Complete metadata once, in the first block; later blocks carry the reference only.
        result.update(
            evidencia_componente=body["evidencias"].get("componente:" + componente),
            evidencia_situacao=body["evidencias"].get("situacao"),
            metadados=metadata(body, row["hash"]),
            julgados_relacionados=body.get("julgados_relacionados", []),
        )
    return result
