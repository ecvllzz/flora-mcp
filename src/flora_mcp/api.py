"""One read interface for stdio, HTTP, panel and local callers."""

import json

from . import precedent_query, query
from .coverage import filtered_resources, summary, validate_filters
from .model import FloraError
from .model import canonical
from .precedents import available, parse_id
from .publication import Reader
from .query import CONTRATO
from .store import collection_delay


def _view(store, cursor=None, publicacao_id=None):
    """The generation a call reads: the cursor's, the requested one or the current one."""
    if cursor:
        pinned = query.decode_cursor(cursor).get("publicacao")
        if publicacao_id and publicacao_id != pinned:
            raise FloraError("cursor_invalido", "Publicação diverge do cursor.")
        publicacao_id = pinned
    if store.reader is None:
        store.reader = Reader(store)
    return store.reader.resolve(publicacao_id)


def _finish(view, result):
    result["contrato"] = CONTRATO
    if view.publication is not None:
        result["publicacao_id"] = view.publication
    return result


def search(
    store,
    termos="",
    processo=None,
    tribunal=None,
    orgao=None,
    classe=None,
    data_inicio=None,
    data_fim=None,
    tipo_data="publicacao",
    ordenar=None,
    limite=None,
    cursor=None,
    *,
    relator=None,
    detalhe="triagem",
    publicacao_id=None,
    modo_busca="simples",
):
    """Acórdãos only; temas and súmulas are in search_precedents."""
    view = _view(store, cursor, publicacao_id)
    result = query.search(
        view,
        termos,
        processo=processo,
        tribunal=tribunal,
        orgao=orgao,
        classe=classe,
        data_inicio=data_inicio,
        data_fim=data_fim,
        tipo_data=tipo_data,
        ordenar=ordenar,
        limite=limite,
        cursor=cursor,
        relator=relator,
        detalhe=detalhe,
        modo_busca=modo_busca,
    )
    return _finish(view, result)


def search_precedents(
    store,
    termos="",
    *,
    tribunal=None,
    especie=None,
    numero=None,
    orgao=None,
    materia=None,
    campo="todos",
    data_inicio=None,
    data_fim=None,
    ordenar=None,
    detalhe="triagem",
    modo_busca="simples",
    limite=None,
    cursor=None,
    publicacao_id=None,
):
    view = _view(store, cursor, publicacao_id)
    result = precedent_query.search(
        view,
        termos=termos,
        tribunal=tribunal,
        orgao=orgao,
        especie=especie,
        numero=numero,
        materia=materia,
        campo=campo,
        ordenar=ordenar,
        limite=limite,
        cursor=cursor,
        detalhe=detalhe,
        data_inicio=data_inicio,
        data_fim=data_fim,
        modo_busca=modo_busca,
    )
    return _finish(view, result)


def document(
    store,
    id,
    componente="ementa",
    cursor=None,
    tamanho_bloco=16000,
    *,
    hash_conteudo=None,
    publicacao_id=None,
):
    view = _view(store, cursor, publicacao_id)
    with view.read() as db:
        is_precedent = available(db) and db.execute("SELECT 1 FROM precedents WHERE id=?", (id,)).fetchone()
    # Qualified identities remain qualified even after removal from a published snapshot.
    if is_precedent or parse_id(id) is not None:
        result = precedent_query.document(view, id, componente, cursor, tamanho_bloco, hash_conteudo)
    else:
        result = query.document(view, id, componente, cursor, tamanho_bloco)
        if hash_conteudo and result["hash_conteudo"] != hash_conteudo:
            raise FloraError("versao_indisponivel", "Versão indisponível nesta publicação.")
    return _finish(view, result)


COVERAGE_DETAILS = ("resumo", "completo", "recursos", "execucoes")


def coverage(
    store, detalhe="resumo", cursor=None, limite=20, publicacao_id=None, tribunal=None, dataset=None
):
    view = _view(store, cursor, publicacao_id)
    validate_filters(tribunal, dataset, detalhe)
    if detalhe not in COVERAGE_DETAILS or not 1 <= limite <= 50:
        raise FloraError("filtro_invalido", "Use resumo, completo, recursos ou execucoes e limite de 1 a 50.")
    if detalhe in {"resumo", "completo"} and cursor:
        raise FloraError("cursor_invalido", "Resumo e resposta completa não usam cursor.")
    if detalhe == "completo":
        return _finish(view, view.coverage())
    with view.read() as db:
        db.execute("BEGIN")
        revision = db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]
        if detalhe == "resumo":
            result = _summary(view, db, revision)
        else:
            scope = {"tipo": detalhe, "limite": limite, "revisao": revision, "tribunal": tribunal}
            result = _history(view, db, {**scope, "dataset": dataset}, cursor)
    return _finish(view, result)


def _admitted_precedents(view, db):
    if not available(db):
        return []
    return [
        dict(r)
        for r in db.execute(
            "SELECT tribunal,species AS especie,admission AS admissao,count(*) AS documentos "
            "FROM precedents WHERE admission='admitido' AND id NOT IN (SELECT value FROM "
            "json_each(?)) AND (id || ':' || hash) NOT IN (SELECT value FROM json_each(?)) "
            "GROUP BY tribunal,species,admission ORDER BY tribunal,species,admission",
            (canonical(sorted(view.withdrawn)), canonical(sorted(view.retired_versions))),
        )
    ]


def _latest_runs(db):
    """Most recent run of each source, without detail; the history is in detalhe=execucoes."""
    return [
        dict(r)
        for r in db.execute(
            "SELECT id,source,started,finished,status FROM runs r WHERE r.id=(SELECT id FROM runs "
            "WHERE source=r.source ORDER BY started DESC,id LIMIT 1) ORDER BY source"
        )
    ]


def _summary(view, db, revision):
    admission_counts = view.admission_counts
    if admission_counts is None:
        admission_counts = (
            dict(db.execute("SELECT admission,count(*) FROM precedents GROUP BY admission"))
            if available(db)
            else {}
        )
    result = summary(view.coverage(), _latest_runs(db))
    result.update(
        {
            "revisao_base": revision,
            "precedentes": _admitted_precedents(view, db),
            "admissao_atual": admission_counts,
            "proximo_cursor": None,
        }
    )
    return result


def _history(view, db, scope, cursor):
    """detalhe=recursos or execucoes, paginated; the cursor keeps the scope and the revision."""
    offset = 0
    if cursor:
        value = query.read_cursor(view, cursor)
        if any(value.get(k) != v for k, v in scope.items()):
            raise FloraError("cursor_invalido", "Cursor de outra cobertura ou revisão.")
        offset = value.get("offset")
        if type(offset) is not int or offset < 0:
            raise FloraError("cursor_invalido", "Posição inválida.")
    limit = scope["limite"]
    if scope["tipo"] == "recursos":
        all_rows = filtered_resources(view.coverage()["recursos"], scope["tribunal"], scope["dataset"])
        total, rows = len(all_rows), all_rows[offset : offset + limit]
    else:
        total = db.execute("SELECT count(*) FROM runs").fetchone()[0]
        rows = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM runs ORDER BY started DESC,id LIMIT ? OFFSET ?", (limit, offset)
            )
        ]
        for row in rows:
            row["detail"] = json.loads(row["detail"])
    following = offset + len(rows)
    return {
        "status": "ok",
        "detalhe": scope["tipo"],
        "revisao_base": scope["revisao"],
        "total": total,
        "itens": rows,
        "proximo_cursor": query.encode_cursor(view, {**scope, "offset": following})
        if following < total
        else None,
        "coleta": collection_delay(db, view.atrasos),
    }
