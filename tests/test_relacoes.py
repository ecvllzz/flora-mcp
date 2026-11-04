"""quem_cita, o_que_cita and parecido_com: optional, from one acórdão of the base; the default stays."""

import pytest

from conftest import ingest, raw_doc
from flora_mcp import api, relacoes
from flora_mcp.model import FloraError
from flora_mcp.precedents import import_package, migrate
from flora_mcp.publication import publish
from test_precedents import packet


@pytest.fixture
def graph(store, tmp_path):
    """STJ:2 cites STJ:1 (one acórdão) and REsp 7 (two acórdãos, STJ:3 and STJ:4); STJ:5 cites STJ:1."""
    ingest(
        store,
        [
            raw_doc(
                "1", numeroProcesso="1111111", siglaClasse="REsp", text="Guarda compartilhada e alimentos."
            ),
            raw_doc(
                "2",
                numeroProcesso="2222222",
                siglaClasse="AgInt no REsp",
                text="Revisão de alimentos entre genitores.",
                jurisprudenciaCitada="(X)\n   STJ - <<REsp 1111111>>-SP,\n   <<REsp 7>>-PR",
            ),
            raw_doc("3", numeroProcesso="7", siglaClasse="REsp", text="Primeiro acórdão do processo sete."),
            raw_doc(
                "4",
                numeroProcesso="7",
                siglaClasse="REsp",
                text="Embargos no processo sete.",
                dataDecisao="20260901",
            ),
            raw_doc(
                "5",
                numeroProcesso="5555555",
                siglaClasse="REsp",
                text="Guarda unilateral, convivência e alimentos do menor.",
                jurisprudenciaCitada="(Y)\n   STJ - <<REsp 1111111>>-SP",
                dataPublicacao="DJEN DATA:15/08/2026",
            ),
            raw_doc("6", numeroProcesso="6", siglaClasse="REsp", text="Usucapião de imóvel urbano."),
        ],
    )
    migrate(store)
    import_package(store, packet(tmp_path), apply=True)
    publish(store)
    return store


def test_quem_cita_lists_the_citing_acordaos_with_the_count_as_information_only(graph):
    page = api.search(graph, quem_cita="STJ:1")
    assert [r["id"] for r in page["resultados"]] == ["STJ:2", "STJ:5"]  # default order: most recent
    assert page["ordenacao"] == "mais_recentes"
    assert page["relacao"] == {
        "acordao": "STJ:1",
        "tipo": "quem_cita",
        "citantes_no_acervo": 2,
        "citados_no_acervo": 0,
        "ambiguos": 0,
        "derivador": "citacoes-2",
        "aviso": relacoes.RELATION_NOTICE,
    }
    assert all(r["vinculo"] == "resolvido" for r in page["resultados"])
    # With terms, the relation restricts and the relevance order is the usual one.
    ranked = api.search(graph, "guarda menor", quem_cita="STJ:1")
    assert [r["id"] for r in ranked["resultados"]] == ["STJ:5"] and ranked["ordenacao"] == "relevancia"
    assert ranked["resultados"][0]["termos_presentes"] == ["guarda", "menor"]
    empty = api.search(graph, quem_cita="STJ:6")
    assert empty["total_encontrado"] == 0 and empty["relacao"]["citantes_no_acervo"] == 0


def test_o_que_cita_lists_the_cited_acordaos_and_marks_ambiguity(graph):
    page = api.search(graph, o_que_cita="STJ:2")
    by_id = {r["id"]: r["vinculo"] for r in page["resultados"]}
    assert by_id == {"STJ:1": "resolvido", "STJ:3": "ambiguo", "STJ:4": "ambiguo"}
    assert page["relacao"]["citados_no_acervo"] == 3 and page["relacao"]["ambiguos"] == 2
    assert page["relacao"]["tipo"] == "o_que_cita"
    complete = api.search(graph, o_que_cita="STJ:2", detalhe="completo")
    assert complete["resultados"][0]["vinculo"] in {"resolvido", "ambiguo"}


def test_relation_refusals(graph):
    with pytest.raises(FloraError, match="não os dois"):
        api.search(graph, quem_cita="STJ:1", o_que_cita="STJ:2")
    with pytest.raises(FloraError) as missing:
        api.search(graph, quem_cita="STJ:999")
    assert missing.value.code == "documento_nao_encontrado"


def test_relations_need_a_publication(store):
    ingest(store, [raw_doc("1")])
    with pytest.raises(FloraError) as unpublished:
        api.search(store, quem_cita="STJ:1")
    assert unpublished.value.code == "filtro_indisponivel"


@pytest.fixture
def small_base(monkeypatch):
    """Six documents: the frequency bounds of the real base (5 documents, 25%) would leave no term."""
    monkeypatch.setattr(relacoes, "SEED_MIN_DF", 1)
    monkeypatch.setattr(relacoes, "SEED_MAX_SHARE", 1.0)


def test_parecido_com_queries_the_seed_terms_and_leaves_the_seed_out(graph, small_base):
    page = api.search(graph, parecido_com="STJ:5")
    assert page["semente"]["id"] == "STJ:5" and page["semente"]["aviso"] == relacoes.SIMILAR_NOTICE
    terms = page["semente"]["termos"]
    assert terms and all(t.islower() and t.isalpha() for t in terms)
    assert page["consulta_efetiva"] == " OR ".join(f'"{t}"' for t in terms)
    ids = [r["id"] for r in page["resultados"]]
    assert "STJ:5" not in ids and ids[0] == "STJ:1" and page["ordenacao"] == "relevancia"
    assert "termos_descartados" not in page and "relacao" not in page
    assert all(r["termos_presentes"] for r in page["resultados"])
    by_date = api.search(graph, parecido_com="STJ:5", ordenar="mais_antigos")
    assert by_date["ordenacao"] == "mais_antigos" and by_date["consulta_efetiva"] == page["consulta_efetiva"]


def test_parecido_com_refusals_and_default_untouched(graph, small_base):
    with pytest.raises(FloraError, match="não combine com termos"):
        api.search(graph, "guarda", parecido_com="STJ:5")
    with pytest.raises(FloraError, match="quem_cita"):
        api.search(graph, parecido_com="STJ:5", quem_cita="STJ:1")
    with pytest.raises(FloraError) as missing:
        api.search(graph, parecido_com="STJ:999")
    assert missing.value.code == "documento_nao_encontrado"
    plain = api.search(graph, "guarda alimentos")
    assert not {"semente", "relacao"} & set(plain) and "vinculo" not in plain["resultados"][0]


def test_seed_without_enough_distinctive_terms_is_refused(graph):
    # With the real bounds (5 documents at least), a six-document base yields no term.
    with pytest.raises(FloraError) as info:
        api.search(graph, parecido_com="STJ:5")
    assert info.value.code == "consulta_invalida" and "semente" in str(info.value)


def test_seed_terms_follow_tf_idf_and_drop_numbers_and_stopwords(graph, small_base):
    view = api._view(graph, None, None)
    with view.read() as db:
        terms = relacoes.seed_terms(db, "Guarda, guarda e alimentos do menor; 2026.", {"DO", "E"})
    assert terms[0] == "guarda" and "2026" not in terms and "do" not in terms and "menor" in terms
