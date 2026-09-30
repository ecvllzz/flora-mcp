import base64
import json
import re
import sqlite3
from datetime import date

from .ausencia import empty_reason
from .citation import citation_metadata
from .model import FloraError, canonical, digest, folded, number
from .store import ReadView, collection_delay
from .text import advanced_query, header, matched_window, sections

CONTRATO = "flora-mcp-3.2"
ORDERS = ("mais_recentes", "mais_antigos", "relevancia")
# Triage pages stay under 8 KiB of compact JSON, with room for the publication identity.
TRIAGE_BUDGET = 7500
TRIAGE_KEYS = (
    "id",
    "tribunal",
    "orgao",
    "classe_descricao",
    "processo",
    "relator",
    "referencia",
    "referencia_completa",
    "referencia_pendencias",
    "hash_conteudo",
)


def as_view(store) -> ReadView:
    """Local callers may pass the Store itself: it reads the work database."""
    return store.view() if hasattr(store, "view") else store


def encode_cursor(view: ReadView, fields: dict) -> str:
    """One encoding for every cursor: contract, publication and the continuation fields."""
    value = {"contrato": CONTRATO, "publicacao": view.publication, **fields}
    return base64.urlsafe_b64encode(canonical(value).encode()).decode()


def decode_cursor(value: str) -> dict:
    try:
        if len(value) > 2048:
            raise ValueError()
        result = json.loads(base64.b64decode(value, altchars=b"-_", validate=True))
        if not isinstance(result, dict):
            raise ValueError()
    except (ValueError, UnicodeError) as exc:
        raise FloraError("cursor_invalido", "Cursor inválido; reinicie a consulta.") from exc
    if result.get("contrato") != CONTRATO:
        raise FloraError("cursor_invalido", "Cursor de outra versão do contrato; reinicie a consulta.")
    return result


def read_cursor(view: ReadView, value: str) -> dict:
    decoded = decode_cursor(value)
    if decoded.get("publicacao") != view.publication:
        raise FloraError("base_alterada", "A base mudou entre páginas. Reinicie a consulta.")
    return decoded


def page_offset(view: ReadView, cursor: str | None, fingerprint: str, revision) -> int:
    if not cursor:
        return 0
    decoded = read_cursor(view, cursor)
    if decoded.get("consulta") != fingerprint:
        raise FloraError("cursor_invalido", "O cursor pertence a outra consulta.")
    if decoded.get("revisao") != revision:
        raise FloraError("base_alterada", "A base mudou entre páginas. Reinicie a consulta.")
    offset = decoded.get("offset")
    if type(offset) is not int or offset < 0:
        raise FloraError("cursor_invalido", "Posição do cursor inválida.")
    return offset


def block_offset(view: ReadView, cursor: str | None, id: str, componente: str, sha: str, length: int) -> int:
    if not cursor:
        return 0
    value = read_cursor(view, cursor)
    if value.get("id") != id or value.get("componente") != componente:
        raise FloraError("cursor_invalido", "Cursor de outro documento ou componente.")
    if value.get("hash") != sha:
        raise FloraError("documento_alterado", "Documento atualizado; reinicie sua leitura.")
    offset = value.get("offset")
    if type(offset) is not int or not 0 <= offset <= length:
        raise FloraError("cursor_invalido", "Posição inválida.")
    return offset


QUERY_ERRORS = ("fts5:", "no such column", "unterminated string", "malformed match")


def database_error(exc: sqlite3.OperationalError) -> FloraError:
    """Syntax problems of the MATCH expression are the caller's; anything else is the database's."""
    message = str(exc).lower()
    if message.startswith(QUERY_ERRORS) or "syntax error" in message:
        return FloraError("consulta_invalida", "Consulta lexical inválida.")
    return FloraError("base_indisponivel", "Acervo indisponível no momento; tente novamente.")


def quoted(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def lexical_tokens(terms: str) -> list[tuple[str, bool]]:
    """(value, is_phrase) for each plain word or quoted phrase. No raw FTS/SQL operators."""
    if len(terms) > 500 or terms.count('"') % 2:
        raise FloraError("consulta_invalida", "Consulta muito longa ou aspas sem fechamento.")
    tokens = [
        (phrase, True) if phrase else (token, False)
        for phrase, token in re.findall(r'"([^"]+)"|(\S+)', terms)
    ]
    if len(tokens) > 30:
        raise FloraError("consulta_invalida", "Use até 30 termos ou expressões.")
    return tokens


def lexical_terms(terms: str) -> list[str]:
    # Plain words are ANDed; quoted phrases are preserved.
    return [value for value, _ in lexical_tokens(terms)]


def lexical_query(terms: str) -> str:
    return " AND ".join(quoted(v) for v in lexical_terms(terms))


# Portuguese stopwords dropped from a broadened query, compared after folding case and accents:
# articles, prepositions and their contractions, conjunctions, relative and interrogative
# pronouns and common linking verbs.
STOPWORDS = frozenset(
    """
    o a os as um uma uns umas
    ante apos ate com contra de desde em entre para perante por sem sob sobre
    ao aos do da dos das no na nos nas num numa pelo pela pelos pelas
    deste desta destes destas desse dessa desses dessas neste nesta nesse nessa
    e ou mas nem que se porque pois porem como quando
    qual quais quem onde cujo cuja cujos cujas quanto quanta quantos quantas
    pode podem deve devem cabe cabem foi foram ser sao esta estao ha
    """.upper().split()
)
BROADENED = {
    "de": "todos_os_termos",
    "para": "qualquer_termo",
    "motivo": "nenhum documento contém todos os termos",
}


def broadening(termos: str) -> tuple[list[str], list[str]] | None:
    """Terms kept and stopwords dropped when a simple query of two or more terms is ORed; None if not."""
    tokens = lexical_tokens(termos)
    if len(tokens) < 2:
        return None
    kept, dropped = [], []
    for value, phrase in tokens:
        stopword = not phrase and re.sub(r"\W", "", folded(value)) in STOPWORDS
        (dropped if stopword else kept).append(value)
    return (kept, dropped) if kept else None


def compile_terms(termos: str, modo_busca: str) -> str:
    if modo_busca not in {"simples", "avancado"}:
        raise FloraError("consulta_invalida", "Modo de busca: simples ou avancado.")
    return advanced_query(termos) if modo_busca == "avancado" else lexical_query(termos)


def resolve_order(ordenar: str | None, query: str) -> str:
    """None is automatic: relevance with terms, most recent without them."""
    if ordenar is None:
        return "relevancia" if query else "mais_recentes"
    if ordenar not in ORDERS:
        raise FloraError("filtro_invalido", "Ordenação: mais_recentes, mais_antigos ou relevancia.")
    if ordenar == "relevancia" and not query:
        raise FloraError("consulta_invalida", "Ordenação por relevância exige termos de pesquisa.")
    return ordenar


def check_dates(data_inicio: str | None, data_fim: str | None):
    try:
        for value in (data_inicio, data_fim):
            if value and date.fromisoformat(value).isoformat() != value:
                raise ValueError()
    except ValueError as exc:
        raise FloraError("data_invalida", "Datas devem usar AAAA-MM-DD.") from exc
    if data_inicio and data_fim and data_inicio > data_fim:
        raise FloraError("data_invalida", "Data inicial posterior à final.")


def page_limit(detalhe: str, limite: int | None) -> int:
    if detalhe not in {"completo", "triagem"}:
        raise FloraError("filtro_invalido", "Detalhe disponível: triagem ou completo.")
    triage = detalhe == "triagem"
    limit = limite if limite is not None else (8 if triage else 3)
    if not 1 <= limit <= (8 if triage else 5):
        raise FloraError("limite_invalido", "Use de 1 a 8 itens em triagem ou de 1 a 5 ementas completas.")
    return limit


def coverage_notice(delay: dict) -> dict:
    return {
        "integral": False,
        "fontes_em_atraso": sorted(source for source, value in delay.items() if value["atraso"]),
        "aviso": "Resultado negativo vale apenas para a base carregada; detalhes em consultar_cobertura.",
    }


def fit_triage(result: dict, next_cursor):
    """Drop items from the end until the page fits the budget; next_cursor(n) continues after n items."""
    results = result["resultados"]
    while len(canonical(result).encode()) > TRIAGE_BUDGET and len(results) > 1:
        results.pop()
        result["proximo_cursor"] = next_cursor(len(results))
    if len(canonical(result).encode()) > TRIAGE_BUDGET:
        raise FloraError("referencia_excede_orcamento", "Metadados excedem 8 KiB; solicite detalhe=completo.")


RELATOR_PUBLISHED = "instr((SELECT relator_fold FROM document_details WHERE id=d.id),?)>0"
RELATOR_WORK = """instr(flora_fold(COALESCE((SELECT COALESCE(
json_extract(v.raw,'$.ministroRelator'), json_extract(v.raw,'$.campos.RELATOR'),
json_extract(v.raw,'$.campos.RELATORA')) FROM versions v
WHERE v.document_id=d.id AND v.hash=d.hash),'')),?)>0"""


def judgment_filters(view: ReadView, *, processo, tribunal, orgao, classe, relator):
    filters, params = [], []
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
        filters.append(RELATOR_PUBLISHED if view.publication is not None else RELATOR_WORK)
        params.append(folded(relator))
    return filters, params


def date_filters(column: str, data_inicio, data_fim):
    pairs = [(op, value) for op, value in ((">=", data_inicio), ("<=", data_fim)) if value]
    return [f"{column}{op}?" for op, _ in pairs], [value for _, value in pairs]


class JudgmentSearch:
    """One acórdão search: validated parameters, SQL plan and the reading of one page."""

    def __init__(self, view: ReadView, termos, *, detalhe, limite, ordenar, modo_busca, tipo_data):
        if tipo_data not in {"publicacao", "julgamento"}:
            raise FloraError("filtro_invalido", "Tipo de data: publicacao ou julgamento.")
        self.view = view
        self.termos, self.modo_busca, self.detalhe = termos, modo_busca, detalhe
        self.limit = page_limit(detalhe, limite)
        self.query = compile_terms(termos, modo_busca)
        self.ordenar = resolve_order(ordenar, self.query)
        self.column = "publication" if tipo_data == "publicacao" else "judgment"
        self.filters, self.params, self.filtered = [], [], False
        self.offset = 0
        self.original, self.broadened = self.query, None

    def restrict(self, filters, params):
        self.filters += filters
        self.params += params
        self.filtered = self.filtered or bool(filters)

    def plan(self):
        ranked = self.ordenar == "relevancia"
        source = "documents d JOIN search ON search.id=d.id" if ranked else "documents d"
        filters, params = list(self.filters), list(self.params)
        if self.query:
            match = "search MATCH ?" if ranked else "d.id IN (SELECT id FROM search WHERE search MATCH ?)"
            filters.insert(0, match)
            params.insert(0, self.query)
        direction = "ASC" if self.ordenar == "mais_antigos" else "DESC"
        order = f"d.{self.column} IS NULL,d.{self.column} {direction},d.id"
        if ranked:
            # FTS5 BM25: lower scores first; dates/ID break lexical ties deterministically.
            order = "bm25(search)," + order
        return source, " AND ".join(filters) or "1=1", params, order

    def fingerprint(self, where, params):
        values = [where, params, self.column, self.ordenar, self.limit, self.detalhe]
        return digest(canonical(values).encode())

    def continuation(self, fingerprint, revision, offset):
        return encode_cursor(self.view, {"consulta": fingerprint, "revisao": revision, "offset": offset})

    def count(self, db):
        source, where, params, _ = self.plan()
        try:
            return db.execute(f"SELECT count(*) FROM {source} WHERE {where}", params).fetchone()[0]
        except sqlite3.OperationalError as exc:
            raise database_error(exc) from exc

    def term_count(self, db, term):
        try:
            return db.execute("SELECT count(*) FROM search WHERE search MATCH ?", (quoted(term),)).fetchone()[
                0
            ]
        except sqlite3.OperationalError as exc:
            raise database_error(exc) from exc

    def total(self, db):
        """Count with every term; when that is zero, retry with any term (simple mode only)."""
        total = self.count(db)
        terms = broadening(self.termos) if total == 0 and self.modo_busca == "simples" else None
        if terms is None:
            return total
        self.query = " OR ".join(quoted(t) for t in terms[0])
        total = self.count(db)
        if total == 0:
            self.query = self.original  # The empty answer and its reason stay those of the query asked.
            return 0
        counts = [{"termo": t, "documentos": self.term_count(db, t)} for t in terms[0]]
        self.broadened = {**BROADENED, "termos": counts, "termos_descartados": terms[1]}
        return total

    def page(self, db, cursor, revision):
        source, where, params, order = self.plan()
        fingerprint = self.fingerprint(where, params)
        offset = self.offset = page_offset(self.view, cursor, fingerprint, revision)
        try:
            rows = db.execute(
                f"""SELECT d.body,
                (SELECT v.raw FROM versions v WHERE v.document_id=d.id AND v.hash=d.hash) AS original
                FROM {source} WHERE {where}
                ORDER BY {order}
                LIMIT ? OFFSET ?""",
                (*params, self.limit, offset),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            raise database_error(exc) from exc
        return rows, lambda n: self.continuation(fingerprint, revision, offset + n)

    def highlights(self, db, ids):
        if not self.query or not ids or self.detalhe != "triagem":
            return {}
        marks = ",".join("?" * len(ids))
        try:
            return dict(
                db.execute(
                    "SELECT id,highlight(search,1,char(1),char(2)) FROM search "
                    f"WHERE search MATCH ? AND id IN ({marks})",
                    (self.query, *ids),
                ).fetchall()
            )
        except sqlite3.OperationalError as exc:
            raise database_error(exc) from exc

    def item(self, body, original, marked):
        item = {**body, **citation_metadata(body, original)}
        if self.detalhe == "completo":
            return item
        full = item["ementa"]
        result = {k: item.get(k) for k in TRIAGE_KEYS}
        cabecalho, parcial = header(full)
        result.update(sha256_componente=digest(full.encode()), cabecalho=cabecalho, cabecalho_parcial=parcial)
        if self.query:
            result["trecho_correspondente"] = matched_window(full, marked)
        return result

    def reason(self, db, tribunal, orgao, dates):
        def intervals():
            conditions = [(k, folded(v)) for k, v in (("tribunal", tribunal), ("organ", orgao)) if v]
            where = " AND ".join(f"{k}=?" for k, _ in conditions) or "1=1"
            return [
                dict(r)
                for r in db.execute(
                    f"SELECT tribunal,json_extract(body,'$.orgao') AS orgao,min({self.column}) AS inicio,"
                    f"max({self.column}) AS fim FROM documents WHERE {where} GROUP BY tribunal,organ "
                    "ORDER BY tribunal,organ",
                    [v for _, v in conditions],
                )
            ]

        def unfiltered_total():
            if not self.query:
                return db.execute("SELECT count(*) FROM documents").fetchone()[0]
            return db.execute(
                "SELECT count(*) FROM documents d WHERE d.id IN (SELECT id FROM search WHERE search MATCH ?)",
                (self.query,),
            ).fetchone()[0]

        def term_counts():
            if self.modo_busca != "simples":
                return None
            return [{"termo": t, "documentos": self.term_count(db, t)} for t in lexical_terms(self.termos)]

        try:
            return empty_reason(
                dates=dates,
                intervals=intervals,
                filtered=self.filtered,
                unfiltered_total=unfiltered_total,
                term_counts=term_counts,
            )
        except sqlite3.OperationalError as exc:
            raise database_error(exc) from exc


def search(
    store: ReadView,
    termos: str = "",
    processo: str | None = None,
    tribunal: str | None = None,
    orgao: str | None = None,
    classe: str | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
    tipo_data: str = "publicacao",
    ordenar: str | None = None,
    limite: int | None = None,
    cursor: str | None = None,
    *,
    relator: str | None = None,
    detalhe: str = "triagem",
    modo_busca: str = "simples",
) -> dict:
    store = as_view(store)
    plan = JudgmentSearch(
        store,
        termos,
        detalhe=detalhe,
        limite=limite,
        ordenar=ordenar,
        modo_busca=modo_busca,
        tipo_data=tipo_data,
    )
    if tribunal and tribunal.upper() not in {"STJ", "TJSC"}:
        raise FloraError("tribunal_invalido", "Tribunal suportado: STJ ou TJSC.")
    check_dates(data_inicio, data_fim)
    plan.restrict(
        *judgment_filters(
            store, processo=processo, tribunal=tribunal, orgao=orgao, classe=classe, relator=relator
        )
    )
    plan.restrict(*date_filters("d." + plan.column, data_inicio, data_fim))
    with store.read() as db:
        db.create_function("flora_fold", 1, lambda value: folded(value or ""), deterministic=True)
        db.execute("BEGIN")  # Revision and rows belong to the same read snapshot.
        revision = db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]
        total = plan.total(db)
        rows, following = plan.page(db, cursor, revision)
        bodies = [(json.loads(r["body"]), json.loads(r["original"]) if r["original"] else None) for r in rows]
        marks = plan.highlights(db, [body["id"] for body, _ in bodies])
        reason = plan.reason(db, tribunal, orgao, (data_inicio, data_fim)) if total == 0 else {}
        delay = collection_delay(db, store.atrasos)
    result = {
        "status": "ok",
        "contrato": CONTRATO,
        "total_encontrado": total,
        "resultados": [plan.item(body, original, marks.get(body["id"])) for body, original in bodies],
        "detalhe": detalhe,
        "ementas_completas": detalhe == "completo",
        "campo_pesquisado": "ementa",
        "modo_busca": modo_busca,
        "consulta_efetiva": plan.query,
        **({"ampliacao": plan.broadened} if plan.broadened else {}),
        "ordenacao": plan.ordenar,
        "revisao_base": revision,
        "proximo_cursor": following(len(rows)) if plan.offset + len(rows) < total else None,
        "cobertura": coverage_notice(delay),
        **reason,
    }
    if detalhe == "triagem":
        fit_triage(result, following)
    return result


def document(
    store: ReadView,
    id: str,
    componente: str = "ementa",
    cursor: str | None = None,
    tamanho_bloco: int = 16000,
) -> dict:
    if componente not in {"ementa", "espelho_original"} and not componente.startswith("secao:"):
        raise FloraError(
            "componente_indisponivel", "Componentes disponíveis: ementa, espelho_original e secao:<nome>."
        )
    if not 100 <= tamanho_bloco <= 32000:
        raise FloraError("limite_invalido", "Blocos devem ter entre 100 e 32000 caracteres.")
    store = as_view(store)
    with store.read() as db:
        db.execute("BEGIN")
        row = db.execute("SELECT * FROM documents WHERE id=?", (id,)).fetchone()
        if not row:
            raise FloraError("documento_nao_encontrado", "Identificador não encontrado na base local.")
        body = json.loads(row["body"])
        raw = db.execute(
            "SELECT raw FROM versions WHERE document_id=? AND hash=?", (id, row["hash"])
        ).fetchone()[0]
        source = dict(
            db.execute(
                "SELECT url,sha256,checked,raw_path FROM resources WHERE id=?", (row["resource_id"],)
            ).fetchone()
        )
    body = {**body, **citation_metadata(body, json.loads(raw))}
    text = component_text(body, raw, componente)
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
        "referencia": body["referencia"],
        "referencia_pendencias": body["referencia_pendencias"],
        "proximo_cursor": encode_cursor(
            store, {"id": id, "componente": componente, "hash": row["hash"], "offset": following}
        )
        if following < len(text)
        else None,
    }
    if offset == 0:
        # Complete metadata once, in the first block; later blocks carry the reference only.
        body["secoes_ementa"] = sections(body["ementa"])
        result.update(fonte=source, metadados={k: v for k, v in body.items() if k != "ementa"})
    return result


def component_text(body: dict, raw: str, componente: str) -> str:
    if componente == "ementa":
        return body["ementa"]
    if componente == "espelho_original":
        return raw
    section = next((s for s in sections(body["ementa"]) if s["nome"] == componente[6:]), None)
    if section is None:
        raise FloraError(
            "componente_indisponivel",
            "Seção não delimitada com segurança. Use ementa ou espelho_original.",
        )
    return body["ementa"][section["inicio"] : section["fim"]]
