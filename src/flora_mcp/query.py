import base64
import json
import re
import sqlite3
from datetime import date

from .citation import citation_metadata
from .model import FloraError, canonical, digest, folded, number
from .store import Store
from .text import advanced_query, sections


def encode_cursor(value: dict) -> str:
    return base64.urlsafe_b64encode(canonical(value).encode()).decode()


def decode_cursor(value: str) -> dict:
    try:
        if len(value) > 2048:
            raise ValueError()
        result = json.loads(base64.b64decode(value, altchars=b"-_", validate=True))
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except (ValueError, UnicodeError) as exc:
        raise FloraError("cursor_invalido", "Cursor inválido; reinicie a consulta.") from exc


def lexical_query(terms: str) -> str:
    # Plain words are ANDed; quoted phrases are preserved. No raw FTS/SQL operators.
    if len(terms) > 500 or terms.count('"') % 2:
        raise FloraError("consulta_invalida", "Consulta muito longa ou aspas sem fechamento.")
    tokens = re.findall(r'"([^"]+)"|(\S+)', terms)
    values = [phrase or token for phrase, token in tokens]
    if len(values) > 30:
        raise FloraError("consulta_invalida", "Use até 30 termos ou expressões.")
    return " AND ".join('"' + v.replace('"', '""') + '"' for v in values)


def search(
    store: Store,
    termos: str = "",
    processo: str | None = None,
    tribunal: str | None = None,
    orgao: str | None = None,
    classe: str | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
    tipo_data: str = "publicacao",
    campo: str = "ementa",
    ordenar: str = "mais_recentes",
    limite: int = 3,
    cursor: str | None = None,
    *,
    relator: str | None = None,
    detalhe: str = "completo",
    modo_busca: str = "simples",
) -> dict:
    if campo != "ementa":
        raise FloraError(
            "campo_indisponivel", "Esta versão indexa ementas; inteiro teor ainda não foi incorporado."
        )
    if tipo_data not in {"publicacao", "julgamento"} or ordenar not in {
        "mais_recentes",
        "mais_antigos",
        "relevancia",
    }:
        raise FloraError("filtro_invalido", "Tipo de data ou ordenação inválido.")
    if detalhe not in {"completo", "triagem"}:
        raise FloraError("filtro_invalido", "Detalhe disponível: completo ou triagem.")
    if not 1 <= limite <= (8 if detalhe == "triagem" else 5):
        raise FloraError("limite_invalido", "Use de 1 a 5 resultados por página, com ementas completas.")
    if tribunal and tribunal.upper() not in {"STJ", "TJSC"}:
        raise FloraError("tribunal_invalido", "Tribunal suportado: STJ ou TJSC.")
    try:
        for value in (data_inicio, data_fim):
            if value and date.fromisoformat(value).isoformat() != value:
                raise ValueError()
    except ValueError as exc:
        raise FloraError("data_invalida", "Datas devem usar AAAA-MM-DD.") from exc
    if data_inicio and data_fim and data_inicio > data_fim:
        raise FloraError("data_invalida", "Data inicial posterior à final.")
    filters, params = [], []
    if modo_busca not in {"simples", "avancado"}:
        raise FloraError("consulta_invalida", "Modo de busca: simples ou avancado.")
    query = advanced_query(termos) if modo_busca == "avancado" else lexical_query(termos)
    ranked = ordenar == "relevancia"
    if ranked and not query:
        raise FloraError("consulta_invalida", "Ordenação por relevância exige termos de pesquisa.")
    source = "documents d JOIN search ON search.id=d.id" if ranked else "documents d"
    if query:
        filters.append("search MATCH ?" if ranked else "d.id IN (SELECT id FROM search WHERE search MATCH ?)")
        params.append(query)
    if processo:
        digits = number(processo)
        if not digits:
            raise FloraError(
                "processo_invalido", "Informe o número do processo ou registro; classe tem filtro próprio."
            )
        filters.append("(d.process=? OR d.registration=?)")
        params.extend([digits, digits])
    for key, value in (("tribunal", tribunal), ("organ", orgao), ("class", classe)):
        if value:
            filters.append(f"d.{key}=?")
            params.append(folded(value))
    if relator:
        if len(relator) > 150:
            raise FloraError("filtro_invalido", "Relatoria deve ter até 150 caracteres.")
        if getattr(store, "publication", None):
            filters.append("instr((SELECT relator_fold FROM document_details WHERE id=d.id),?)>0")
        else:
            filters.append("""instr(flora_fold(COALESCE((SELECT COALESCE(
            json_extract(v.raw,'$.ministroRelator'), json_extract(v.raw,'$.campos.RELATOR'),
            json_extract(v.raw,'$.campos.RELATORA')) FROM versions v
            WHERE v.document_id=d.id AND v.hash=d.hash),'')),?)>0""")
        params.append(folded(relator))
    date_column = "publication" if tipo_data == "publicacao" else "judgment"
    for operation, value in ((">=", data_inicio), ("<=", data_fim)):
        if value:
            filters.append(f"d.{date_column}{operation}?")
            params.append(value)
    where = " AND ".join(filters) or "1=1"
    fingerprint = digest(canonical([where, params, date_column, ordenar, limite, detalhe]).encode())
    direction = "ASC" if ordenar == "mais_antigos" else "DESC"
    order = f"d.{date_column} IS NULL,d.{date_column} {direction},d.id"
    if ranked:
        # FTS5 BM25: lower scores first; dates/ID break lexical ties deterministically.
        order = "bm25(search)," + order
    with store.read() as db:
        db.create_function("flora_fold", 1, lambda value: folded(value or ""), deterministic=True)
        db.execute("BEGIN")  # Revision and rows belong to the same read snapshot.
        revision = db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]
        offset = 0
        if cursor:
            decoded = decode_cursor(cursor)
            if decoded.get("consulta") != fingerprint:
                raise FloraError("cursor_invalido", "O cursor pertence a outra consulta.")
            if decoded.get("revisao") != revision:
                raise FloraError("base_alterada", "A base mudou entre páginas. Reinicie a consulta.")
            offset = decoded.get("offset")
            if type(offset) is not int or offset < 0:
                raise FloraError("cursor_invalido", "Posição do cursor inválida.")
        try:
            total = db.execute(f"SELECT count(*) FROM {source} WHERE {where}", params).fetchone()[0]
            rows = db.execute(
                f"""SELECT d.body,
                (SELECT v.raw FROM versions v WHERE v.document_id=d.id AND v.hash=d.hash) AS original
                FROM {source} WHERE {where}
                ORDER BY {order}
                LIMIT ? OFFSET ?""",
                (*params, limite, offset),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            raise FloraError("consulta_invalida", "Consulta lexical inválida.") from exc
        groups = [
            dict(r)
            for r in db.execute("""SELECT tribunal,json_extract(body,'$.orgao') AS orgao,
            count(*) AS documentos FROM documents GROUP BY tribunal,organ""")
        ]
    results = []
    for row in rows:
        body = json.loads(row["body"])
        original = json.loads(row["original"]) if row["original"] else None
        item = {**body, **citation_metadata(body, original)}
        if detalhe == "triagem":
            full = item["ementa"]
            item = {
                k: item.get(k)
                for k in (
                    "id",
                    "tribunal",
                    "processo",
                    "relator",
                    "referencia",
                    "referencia_completa",
                    "referencia_pendencias",
                    "hash_conteudo",
                )
            }
            item.update(
                componente="ementa",
                trecho=full[:400],
                offset=0,
                trecho_parcial=len(full) > 400,
                sha256_componente=digest(full.encode()),
                campos_correspondentes=["ementa"] if query else [],
            )
        results.append(item)
    following = offset + len(results)
    result = {
        "status": "ok",
        "total_encontrado": total,
        "resultados": results,
        "ementas_completas": detalhe == "completo",
        "campo_pesquisado": "ementa",
        "ordenacao": ordenar,
        "revisao_base": revision,
        "proximo_cursor": encode_cursor({"consulta": fingerprint, "revisao": revision, "offset": following})
        if following < total
        else None,
        "cobertura": {
            "integral": False,
            "grupos_carregados": groups,
            "aviso": "Resultado negativo vale apenas para a base carregada. "
            "Consulte consultar_cobertura para pendências e últimas coletas.",
        },
    }
    if modo_busca == "avancado":
        result.update(modo_busca=modo_busca, consulta_efetiva=query)
    if detalhe == "triagem":
        result.update(contrato="flora-mcp-2", detalhe="triagem", consulta_efetiva=query)
        while len(canonical(result).encode()) > 7500 and len(results) > 1:
            results.pop()
            following = offset + len(results)
            result["proximo_cursor"] = encode_cursor(
                {"consulta": fingerprint, "revisao": revision, "offset": following}
            )
        if len(canonical(result).encode()) > 7500:
            raise FloraError(
                "referencia_excede_orcamento", "Metadados excedem 8 KiB; solicite detalhe=completo."
            )
    return result


def document(
    store: Store, id: str, componente: str = "ementa", cursor: str | None = None, tamanho_bloco: int = 16000
) -> dict:
    if componente not in {"ementa", "espelho_original"} and not componente.startswith("secao:"):
        raise FloraError("componente_indisponivel", "Componentes disponíveis: ementa e espelho_original.")
    if not 100 <= tamanho_bloco <= 32000:
        raise FloraError("limite_invalido", "Blocos devem ter entre 100 e 32000 caracteres.")
    with store.read() as db:
        db.execute("BEGIN")
        row = db.execute("SELECT * FROM documents WHERE id=?", (id,)).fetchone()
        if not row:
            raise FloraError("documento_nao_encontrado", "Identificador não encontrado na base local.")
        body = json.loads(row["body"])
        raw = db.execute(
            "SELECT raw FROM versions WHERE document_id=? AND hash=?", (id, row["hash"])
        ).fetchone()[0]
        body = {**body, **citation_metadata(body, json.loads(raw))}
        text = body["ementa"] if componente == "ementa" else raw
        spans = sections(body["ementa"])
        if componente.startswith("secao:"):
            section = next((s for s in spans if s["nome"] == componente[6:]), None)
            if section is None:
                raise FloraError(
                    "componente_indisponivel",
                    "Seção não delimitada com segurança. Use ementa ou espelho_original.",
                )
            text = body["ementa"][section["inicio"] : section["fim"]]
        body["secoes_ementa"] = spans
        source = dict(
            db.execute(
                "SELECT url,sha256,checked,raw_path FROM resources WHERE id=?", (row["resource_id"],)
            ).fetchone()
        )
    offset = 0
    if cursor:
        value = decode_cursor(cursor)
        if value.get("id") != id or value.get("componente") != componente:
            raise FloraError("cursor_invalido", "Cursor de outro documento ou componente.")
        if value.get("hash") != row["hash"]:
            raise FloraError("documento_alterado", "Documento atualizado; reinicie sua leitura.")
        offset = value.get("offset")
        if type(offset) is not int or not 0 <= offset <= len(text):
            raise FloraError("cursor_invalido", "Posição inválida.")
    block = text[offset : offset + tamanho_bloco]
    following = offset + len(block)
    return {
        "status": "ok",
        "id": id,
        "componente": componente,
        "texto": block,
        "offset": offset,
        "total_caracteres": len(text),
        "parcial": offset > 0 or following < len(text),
        "fim": following == len(text),
        "hash_conteudo": row["hash"],
        "sha256_texto_completo": digest(text.encode()),
        "fonte": source,
        "proximo_cursor": encode_cursor(
            {"id": id, "componente": componente, "hash": row["hash"], "offset": following}
        )
        if following < len(text)
        else None,
        "metadados": {k: v for k, v in body.items() if k != "ementa"},
    }
