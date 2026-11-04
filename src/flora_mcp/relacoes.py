"""Optional modes of pesquisar_jurisprudencia that start from one acórdão of the collection.

``quem_cita`` and ``o_que_cita`` walk the citation links the publication derived (citacoes-2:
one row per citing acórdão and candidate cited acórdão, ambiguous when the key fits several);
``parecido_com`` turns the most distinctive terms of the seed ementa into an OR query over the
existing index. None of them changes the default search: without the parameter nothing here runs,
and with it the order stays the one the caller asked for (relevance or date), never a count.
"""

import math
import re
from collections import Counter

from .model import FloraError
from .text import plain

SEED_TERMS, SEED_MIN_DF, SEED_MAX_SHARE, SEED_MIN_TERMS = 25, 5, 0.25, 3
CRITERION = (
    f"{SEED_TERMS} termos mais distintivos da ementa da semente (tf-idf, só letras, sem palavras vazias, "
    f"presentes em ao menos {SEED_MIN_DF} documentos e em no máximo {int(SEED_MAX_SHARE * 100)}% do acervo), "
    "ligados por OR no índice existente, sem a semente"
)
SIMILAR_NOTICE = (
    "Vizinho por texto não é pertinência jurídica: a semelhança é de vocabulário, medida pelo índice."
)
RELATION_NOTICE = (
    "Contagem não é entendimento nem autoridade: é a coincidência de chave de citação no acervo carregado, "
    "que é parcial; a ordem dos resultados não a usa."
)


def seed_document(db, id: str) -> dict:
    import json

    row = db.execute("SELECT body FROM documents WHERE id=?", (id,)).fetchone()
    if not row:
        raise FloraError("documento_nao_encontrado", f"Acórdão {id} não está nesta base.")
    return json.loads(row["body"])


def has_table(db, name: str) -> bool:
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def relation_plan(db, view, *, quem_cita, o_que_cita, stopwords=None) -> tuple[list, list, dict] | None:
    """Filter and information block of quem_cita or o_que_cita; None without them."""
    if quem_cita and o_que_cita:
        raise FloraError("filtro_invalido", "Use quem_cita ou o_que_cita, não os dois.")
    seed = quem_cita or o_que_cita
    if not seed:
        return None
    if view.publication is None or not has_table(db, "document_citations"):
        raise FloraError(
            "filtro_indisponivel", "quem_cita e o_que_cita exigem publicação com citações derivadas."
        )
    seed_document(db, seed)
    linked = has_table(db, "citation_links")
    kind = "quem_cita" if quem_cita else "o_que_cita"
    if linked:
        citing = "SELECT document_id FROM citation_links WHERE cited_id=?"
        cited = "SELECT cited_id FROM citation_links WHERE document_id=?"
        column = "cited_id" if quem_cita else "document_id"
        ambiguous = db.execute(
            f"SELECT count(*) FROM citation_links WHERE {column}=? AND ambiguo=1", (seed,)
        ).fetchone()[0]
    else:
        # Generation of citacoes-1: one acórdão per key, chosen at publication, without ambiguity.
        citing = "SELECT document_id FROM document_citations WHERE tipo='acordao' AND resolvido=?"
        cited = (
            "SELECT resolvido FROM document_citations WHERE tipo='acordao' AND resolvido IS NOT NULL "
            "AND document_id=?"
        )
        ambiguous = None
    info = {
        "acordao": seed,
        "tipo": kind,
        "citantes_no_acervo": db.execute(
            f"SELECT count(*) FROM (SELECT DISTINCT * FROM ({citing}))", (seed,)
        ).fetchone()[0],
        "citados_no_acervo": db.execute(
            f"SELECT count(*) FROM (SELECT DISTINCT * FROM ({cited}))", (seed,)
        ).fetchone()[0],
        "ambiguos": ambiguous,
        "derivador": "citacoes-2" if linked else "citacoes-1",
        "aviso": RELATION_NOTICE,
    }
    return [f"d.id IN ({citing if quem_cita else cited})"], [seed], info


def ambiguity(db, info: dict, ids: list[str]) -> dict:
    """{id: 'ambiguo' or 'resolvido'} for the page items of a relation over citation_links."""
    if not ids or info.get("ambiguos") is None:
        return {}
    marks = ",".join("?" * len(ids))
    if info["tipo"] == "quem_cita":
        rows = db.execute(
            f"SELECT document_id,ambiguo FROM citation_links WHERE cited_id=? AND document_id IN ({marks})",
            (info["acordao"], *ids),
        )
    else:
        rows = db.execute(
            f"SELECT cited_id,ambiguo FROM citation_links WHERE document_id=? AND cited_id IN ({marks})",
            (info["acordao"], *ids),
        )
    return {r[0]: "ambiguo" if r[1] else "resolvido" for r in rows}


def seed_terms(db, ementa: str, stopwords) -> list[str]:
    """The most distinctive terms of the ementa, by tf-idf over the document frequencies of the index."""
    tokens = [t for t in re.findall(r"[^\W\d_]+", plain(ementa).lower()) if len(t) >= 3]
    counts = Counter(t for t in tokens if t.upper() not in stopwords)
    if not counts:
        return []
    db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS temp.vocab USING fts5vocab(main,'search','row')")
    total = db.execute("SELECT count(*) FROM documents").fetchone()[0]
    marks = ",".join("?" * len(counts))
    scores = {}
    for term, df in db.execute(f"SELECT term,doc FROM temp.vocab WHERE term IN ({marks})", list(counts)):
        if SEED_MIN_DF <= df <= total * SEED_MAX_SHARE:
            scores[term] = counts[term] * math.log(total / df)
    return sorted(scores, key=lambda t: (-scores[t], t))[:SEED_TERMS]


def similar_plan(db, id: str, stopwords) -> tuple[list[str], dict]:
    """Terms of the OR query of parecido_com and the block that declares them."""
    body = seed_document(db, id)
    terms = seed_terms(db, body.get("ementa") or "", stopwords)
    if len(terms) < SEED_MIN_TERMS:
        raise FloraError(
            "consulta_invalida",
            f"A ementa de {id} não tem termos distintivos suficientes para servir de semente.",
        )
    return terms, {"id": id, "termos": terms, "criterio": CRITERION, "aviso": SIMILAR_NOTICE}
