"""One read interface for stdio, HTTP, panel and local callers."""

from . import precedent_query, query
from .coverage import filtered_resources, summary, validate_filters
from .model import FloraError
from .model import canonical
from .precedents import available, parse_id
from .publication import Reader
from .store import collection_delay


def _view(store, cursor=None, publicacao_id=None):
    inner = cursor
    if cursor:
        decoded = query.decode_cursor(cursor)
        if "publicacao" in decoded:
            if publicacao_id and publicacao_id != decoded["publicacao"]:
                raise FloraError("cursor_invalido", "Publicação diverge do cursor.")
            publicacao_id = decoded["publicacao"]
            inner = decoded.get("continua")
            if not isinstance(inner, str):
                raise FloraError("cursor_invalido", "Continuação inválida.")
    if store.reader is None:
        store.reader = Reader(store)
    return store.reader.resolve(publicacao_id), inner


def _finish(view, result):
    if view.publication is not None:
        result["publicacao_id"] = view.publication
        result["contrato"] = "flora-mcp-2"
        if result.get("proximo_cursor"):
            result["proximo_cursor"] = query.encode_cursor(
                {"publicacao": view.publication, "continua": result["proximo_cursor"]}
            )
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
    campo="ementa",
    ordenar="mais_recentes",
    limite=None,
    cursor=None,
    *,
    relator=None,
    colecao="acordaos",
    especie=None,
    numero=None,
    detalhe="completo",
    publicacao_id=None,
    modo_busca="simples",
):
    view, inner = _view(store, cursor, publicacao_id)
    limit = limite if limite is not None else (8 if detalhe == "triagem" else 3)
    if detalhe not in {"completo", "triagem"}:
        raise FloraError("filtro_invalido", "Detalhe disponível: completo ou triagem.")
    if colecao == "precedentes":
        if processo or classe or relator or tipo_data != "publicacao":
            raise FloraError(
                "filtro_invalido",
                "Precedentes usam espécie/número e data de publicação; julgado tem filtros próprios.",
            )
        result = precedent_query.search(
            view,
            termos=termos,
            tribunal=tribunal,
            orgao=orgao,
            especie=especie,
            numero=numero,
            campo=campo,
            ordenar=ordenar,
            limite=limit,
            cursor=inner,
            detalhe=detalhe,
            data_inicio=data_inicio,
            data_fim=data_fim,
            modo_busca=modo_busca,
        )
    elif colecao == "acordaos":
        if especie or numero:
            raise FloraError("filtro_invalido", "Espécie/número de precedente exigem colecao=precedentes.")
        result = query.search(
            view,
            termos,
            processo,
            tribunal,
            orgao,
            classe,
            data_inicio,
            data_fim,
            tipo_data,
            campo,
            ordenar,
            limit,
            inner,
            relator=relator,
            detalhe=detalhe,
            modo_busca=modo_busca,
        )
    else:
        raise FloraError("colecao_invalida", "Coleções disponíveis: acordaos e precedentes.")
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
    view, inner = _view(store, cursor, publicacao_id)
    with view.read() as db:
        is_precedent = available(db) and db.execute("SELECT 1 FROM precedents WHERE id=?", (id,)).fetchone()
    # Qualified identities remain qualified even after removal from a published snapshot.
    if is_precedent or parse_id(id) is not None:
        result = precedent_query.document(view, id, componente, inner, tamanho_bloco, hash_conteudo)
    else:
        result = query.document(view, id, componente, inner, tamanho_bloco)
        if hash_conteudo and result["hash_conteudo"] != hash_conteudo:
            raise FloraError("versao_indisponivel", "Versão indisponível nesta publicação.")
    return _finish(view, result)


def coverage(
    store, detalhe="resumo", cursor=None, limite=20, publicacao_id=None, tribunal=None, dataset=None
):
    view, inner = _view(store, cursor, publicacao_id)
    validate_filters(tribunal, dataset, detalhe)
    if detalhe in {"legado", "completo"}:
        if cursor:
            raise FloraError("cursor_invalido", "Cobertura legada não usa cursor.")
        return _finish(view, view.coverage())
    if detalhe not in {"resumo", "recursos", "execucoes"} or not 1 <= limite <= 50:
        raise FloraError("filtro_invalido", "Use resumo, completo, recursos ou execucoes e limite de 1 a 50.")
    with view.read() as db:
        db.execute("BEGIN")
        revision = db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]
        if detalhe == "resumo":
            if inner:
                raise FloraError("cursor_invalido", "Resumo não usa cursor.")
            qualified = (
                [
                    dict(r)
                    for r in db.execute(
                        "SELECT tribunal,species AS especie,admission AS admissao,count(*) AS documentos "
                        "FROM precedents WHERE admission='admitido' AND id NOT IN (SELECT value FROM "
                        "json_each(?)) AND (id || ':' || hash) NOT IN (SELECT value FROM json_each(?)) "
                        "GROUP BY tribunal,species,admission ORDER BY tribunal,species,admission",
                        (
                            canonical(sorted(view.withdrawn)),
                            canonical(sorted(view.retired_versions)),
                        ),
                    )
                ]
                if available(db)
                else []
            )
            admission_counts = view.admission_counts
            if admission_counts is None:
                admission_counts = (
                    dict(db.execute("SELECT admission,count(*) FROM precedents GROUP BY admission"))
                    if available(db)
                    else {}
                )
            result = summary(view.coverage())
            result.update(
                {
                    "contrato": "flora-mcp-2",
                    "revisao_base": revision,
                    "precedentes": qualified,
                    "admissao_atual": admission_counts,
                    "proximo_cursor": None,
                }
            )
        else:
            offset = 0
            if inner:
                value = query.decode_cursor(inner)
                if (
                    value.get("tipo") != detalhe
                    or value.get("limite") != limite
                    or value.get("revisao") != revision
                    or value.get("tribunal") != tribunal
                    or value.get("dataset") != dataset
                ):
                    raise FloraError("cursor_invalido", "Cursor de outra cobertura ou revisão.")
                offset = value.get("offset")
                if type(offset) is not int or offset < 0:
                    raise FloraError("cursor_invalido", "Posição inválida.")
            table, order = (
                ("resources", "dataset,name,id") if detalhe == "recursos" else ("runs", "started DESC,id")
            )
            if detalhe == "recursos":
                all_rows = filtered_resources(view.coverage()["recursos"], tribunal, dataset)
                total = len(all_rows)
                rows = all_rows[offset : offset + limite]
            else:
                import json

                total = db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                rows = [
                    dict(r)
                    for r in db.execute(
                        f"SELECT * FROM {table} ORDER BY {order} LIMIT ? OFFSET ?", (limite, offset)
                    )
                ]
                for row in rows:
                    row["detail"] = json.loads(row["detail"])
            following = offset + len(rows)
            result = {
                "status": "ok",
                "contrato": "flora-mcp-2",
                "detalhe": detalhe,
                "revisao_base": revision,
                "total": total,
                "itens": rows,
                "proximo_cursor": query.encode_cursor(
                    {
                        "tipo": detalhe,
                        "limite": limite,
                        "revisao": revision,
                        "offset": following,
                        "tribunal": tribunal,
                        "dataset": dataset,
                    }
                )
                if following < total
                else None,
                "coleta": collection_delay(db, view.atrasos),
            }
    return _finish(view, result)
