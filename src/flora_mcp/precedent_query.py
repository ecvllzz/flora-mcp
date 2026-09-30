"""Read admitted precedents without exposing their administrative history."""

import json
from datetime import date

from .model import FloraError, canonical, digest, folded
from .precedents import COMPONENTS, SPECIES, available
from .query import decode_cursor, encode_cursor, lexical_query
from .text import advanced_query


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


def search(  # noqa: C901
    store,
    *,
    termos="",
    tribunal=None,
    orgao=None,
    especie=None,
    numero=None,
    campo="todos",
    ordenar="mais_recentes",
    limite=8,
    cursor=None,
    detalhe="triagem",
    data_inicio=None,
    data_fim=None,
    modo_busca="simples",
):
    if campo not in {*COMPONENTS, "todos"}:
        raise FloraError("campo_indisponivel", "Precedentes: " + ", ".join(COMPONENTS) + ", todos.")
    if tribunal and tribunal.upper() not in SPECIES:
        raise FloraError("tribunal_invalido", "Tribunal suportado: STJ, STF ou TJSC.")
    if especie and especie not in set.union(*SPECIES.values()):
        raise FloraError("filtro_invalido", "Espécie fora do contrato.")
    if detalhe not in {"triagem", "completo"} or not 1 <= limite <= (8 if detalhe == "triagem" else 5):
        raise FloraError("limite_invalido", "Até oito itens em triagem ou cinco completos.")
    if ordenar not in {"mais_recentes", "mais_antigos", "relevancia"}:
        raise FloraError("filtro_invalido", "Ordenação inválida.")
    try:
        for value in (data_inicio, data_fim):
            if value and date.fromisoformat(value).isoformat() != value:
                raise ValueError()
        if data_inicio and data_fim and data_inicio > data_fim:
            raise ValueError()
    except ValueError as exc:
        raise FloraError("data_invalida", "Informe intervalo AAAA-MM-DD válido.") from exc
    if modo_busca not in {"simples", "avancado"}:
        raise FloraError("consulta_invalida", "Modo de busca: simples ou avancado.")
    query = advanced_query(termos) if modo_busca == "avancado" else lexical_query(termos)
    if ordenar == "relevancia" and not query:
        raise FloraError("consulta_invalida", "Relevância exige termos.")
    if query and campo != "todos":
        query = campo + " : (" + query + ")"
    filters, params = ["p.admission='admitido'"], []
    withdrawn = sorted(getattr(store, "withdrawn", set()))
    if withdrawn:
        filters.append("p.id NOT IN (SELECT value FROM json_each(?))")
        params.append(canonical(withdrawn))
    retired = sorted(getattr(store, "retired_versions", set()))
    if retired:
        filters.append("(p.id || ':' || p.hash) NOT IN (SELECT value FROM json_each(?))")
        params.append(canonical(retired))
    for column, value in (
        ("tribunal", tribunal.upper() if tribunal else None),
        ("organ", folded(orgao) if orgao else None),
        ("species", especie),
        ("number", numero),
    ):
        if value is not None:
            filters.append("p." + column + "=?")
            params.append(value)
    for op, value in ((">=", data_inicio), ("<=", data_fim)):
        if value:
            filters.append("p.publication" + op + "?")
            params.append(value)
    if query:
        filters.append("precedent_search MATCH ?")
        params.append(query)
    source = "precedents p JOIN precedent_texts t ON t.id=p.id"
    if query:
        source += " JOIN precedent_search ON precedent_search.rowid=t.rowid"
    where = " AND ".join(filters)
    direction = "ASC" if ordenar == "mais_antigos" else "DESC"
    order = "p.publication IS NULL,p.publication " + direction + ",p.id"
    if ordenar == "relevancia":
        order = "bm25(precedent_search,3,1,3,0.5,0.5)," + order
    fingerprint = digest(canonical([where, params, order, limite, detalhe, campo]).encode())
    with store.read() as db:
        db.execute("BEGIN")
        revision = db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]
        offset = 0
        if cursor:
            value = decode_cursor(cursor)
            if (
                value.get("consulta") != fingerprint
                or type(value.get("offset")) is not int
                or value["offset"] < 0
            ):
                raise FloraError("cursor_invalido", "Cursor de outra consulta ou posição inválida.")
            if value.get("revisao") != revision:
                raise FloraError("base_alterada", "Base alterada; reinicie a pesquisa.")
            offset = value["offset"]
        if available(db):
            total = db.execute(f"SELECT count(*) FROM {source} WHERE {where}", params).fetchone()[0]
            # First highlighted position is an offset in the original Unicode string.
            highlights = (
                "".join(
                    f",highlight(precedent_search,{i},char(1),char(2)) AS h{i}"
                    for i in range(len(COMPONENTS))
                )
                if query
                else ""
            )
            rows = db.execute(
                f"SELECT p.body,p.hash{highlights} FROM {source} WHERE {where} ORDER BY {order} LIMIT ? "
                f"OFFSET ?",
                (*params, limite, offset),
            ).fetchall()
        else:
            rows, total = [], 0
    result = {
        "status": "ok",
        "contrato": "flora-mcp-2",
        "colecao": "precedentes",
        "total_encontrado": total,
        "resultados": [],
        "campo_pesquisado": campo,
        "consulta_efetiva": query,
        "ordenacao": ordenar,
        "revisao_base": revision,
        "detalhe": detalhe,
        "proximo_cursor": None,
        "cobertura": {"integral": False, "aviso": "Busca limitada aos precedentes admitidos no acervo."},
    }
    for row in rows:
        body = json.loads(row["body"])
        item = metadata(body, row["hash"])
        if detalhe == "completo":
            item["componentes"] = body["componentes"]
            item["julgados_relacionados"] = body.get("julgados_relacionados", [])
        else:
            matches = [c for i, c in enumerate(COMPONENTS) if query and "\x01" in row[f"h{i}"]]
            component = matches[0] if matches else next(iter(body["componentes"]))
            full = body["componentes"][component]
            start = max(0, row[f"h{COMPONENTS.index(component)}"].find("\x01") - 80) if matches else 0
            snippet = full[start : start + 400]
            item.update(
                componente=component,
                campos_correspondentes=matches,
                trecho=snippet,
                offset=start,
                trecho_parcial=start > 0 or len(snippet) < len(full),
                sha256_componente=digest(full.encode()),
            )
        result["resultados"].append(item)
        following = offset + len(result["resultados"])
        result["proximo_cursor"] = (
            encode_cursor({"consulta": fingerprint, "revisao": revision, "offset": following})
            if following < total
            else None
        )
        if detalhe == "triagem" and len(canonical(result).encode()) > 7500:
            result["resultados"].pop()
            if not result["resultados"]:
                raise FloraError(
                    "referencia_excede_orcamento", "Metadados excedem 8 KiB; solicite detalhe=completo."
                )
            following -= 1
            result["proximo_cursor"] = encode_cursor(
                {"consulta": fingerprint, "revisao": revision, "offset": following}
            )
            break
    if total == 0:
        result["ausencia"] = "Nenhum precedente admitido corresponde à consulta e aos filtros nesta base."
    return result


def document(store, id, componente="enunciado", cursor=None, tamanho_bloco=16000, hash_conteudo=None):
    if id in getattr(store, "withdrawn", set()):
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
    if id + ":" + row["hash"] in getattr(store, "retired_versions", set()):
        raise FloraError("versao_retirada", "Versão retirada do uso ativo.")
    if hash_conteudo and hash_conteudo != row["hash"]:
        raise FloraError("versao_indisponivel", "Versão não disponível nesta publicação.")
    body = json.loads(row["body"])
    components = body["componentes"]
    if componente not in components:
        raise FloraError("componente_indisponivel", "Componentes disponíveis: " + ", ".join(components))
    text = components[componente]
    offset = 0
    if cursor:
        value = decode_cursor(cursor)
        if value.get("id") != id or value.get("componente") != componente or value.get("hash") != row["hash"]:
            raise FloraError("cursor_invalido", "Documento, componente ou versão diferem do cursor.")
        offset = value.get("offset")
        if type(offset) is not int or not 0 <= offset <= len(text):
            raise FloraError("cursor_invalido", "Posição inválida.")
    block = text[offset : offset + tamanho_bloco]
    following = offset + len(block)
    return {
        "status": "ok",
        "contrato": "flora-mcp-2",
        "id": id,
        "colecao": "precedentes",
        "componente": componente,
        "texto": block,
        "offset": offset,
        "total_caracteres": len(text),
        "parcial": offset > 0 or following < len(text),
        "fim": following == len(text),
        "hash_conteudo": row["hash"],
        "sha256_texto_completo": digest(text.encode()),
        "evidencia_componente": body["evidencias"].get("componente:" + componente),
        "evidencia_situacao": body["evidencias"].get("situacao"),
        "metadados": metadata(body, row["hash"]),
        "julgados_relacionados": body.get("julgados_relacionados", []),
        "proximo_cursor": encode_cursor(
            {"id": id, "componente": componente, "hash": row["hash"], "offset": following}
        )
        if following < len(text)
        else None,
    }
