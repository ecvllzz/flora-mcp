"""Catalog of the official situation of the STJ themes: derived from the preserved temas.csv at
publication, exposed as "cancelado segundo a fonte", admitting nothing and serving no thesis."""

import json

import pytest

from conftest import ingest, raw_doc
from flora_mcp import api, catalogo
from flora_mcp.catalogo import NOTA
from flora_mcp.model import FloraError, canonical, digest
from flora_mcp.precedents import import_package, migrate
from flora_mcp.publication import DERIVER, publish
from flora_mcp.store import connection

TEMAS_CSV = (
    "sequencialPrecedente,tipoPrecedente,numeroPrecedente,orgaoJulgador,situacao,dataPublicacaoAcordao,"
    "Assuntos,questaoSubmetidaAJulgamento,teseFirmada\n"
    "1,Tema,908,S2,Trânsito em Julgado,2016-03-02,899- DIREITO CIVIL,Questão.,Tese firmada.\n"
    "2,Tema,357,S1,Cancelado,,899- DIREITO CIVIL,Questão cancelada.,\n"
    "3,Tema,133,S2,Afetado - Possível Revisão de Tese,2010-01-01,899- DIREITO CIVIL,Q.,T.\n"
    "3,Tema,133,S2,Afetado - Possível Revisão de Tese,2010-01-01,899- DIREITO CIVIL,Q.,T.\n"
    "4,IAC,12,S2,Acórdão Publicado,2022-01-01,899- DIREITO CIVIL,Q.,T.\n"
    "5,Controvérsia,999,S2,Vinculada a Tema,,,,\n"
)
TEMAS_URL = (
    "https://dadosabertos.web.stj.jus.br/dataset/4238da2f-c07b-4c1a-b345-4402accacdcf/resource/"
    "df29da13-7d6b-41ba-ad96-cd1a5bbd191c/download/temas.csv"
)


def theme_packet(tmp_path):
    """Tema 908 admitted from the structured source temas.csv, as the real import does."""
    raw = TEMAS_CSV.encode("utf-8")
    source = tmp_path / "temas.csv"
    source.write_bytes(raw)
    sha = digest(raw)
    evidence = {
        k: {"fonte_sha256": sha, "trecho": "Trânsito em Julgado", "localizador": "CSV linha lógica 2"}
        for k in (
            "situacao",
            "publicacao",
            "materia",
            "componente:tese_firmada",
            "componente:questao_submetida",
        )
    }
    record = {
        "tribunal": "STJ",
        "especie": "tema_repetitivo",
        "numero": "908",
        "orgao": "S2",
        "data_publicacao": "2016-03-02",
        "materia": "civil",
        "situacao": "vigente",
        "tipo_publicacao": "acordao_merito",
        "pendencias": [],
        "componentes": {"questao_submetida": "Questão.", "tese_firmada": "Tese firmada."},
        "fontes": [
            {
                "url": TEMAS_URL,
                "sha256": sha,
                "arquivo": "temas.csv",
                "coletado_em": "2026-09-29T20:22:29+00:00",
                "classe": "estruturada",
            }
        ],
        "evidencias": evidence,
        "conferencia": {"evidencias_conferidas": True, "responsavel": "teste", "data": "2026-09-29"},
    }
    package = tmp_path / "pacote.json"
    package.write_text(canonical({"schema": "flora-precedentes-1", "registros": [record]}), encoding="utf-8")
    return package


@pytest.fixture
def published(store, tmp_path):
    ingest(store, [raw_doc("1", text="Juros.")])
    migrate(store)
    import_package(store, theme_packet(tmp_path), apply=True)
    report = publish(store)
    assert report["catalogo_temas"]["temas"] == 4
    return store


def test_catalog_rows_keep_the_source_situation_and_mark_repeats():
    rows = catalogo.catalog_rows(TEMAS_CSV.encode(), {"url": "u", "sha256": "s", "coletado_em": "c"})
    by_id = {r[0]: r for r in rows}
    assert set(by_id) == {
        "STJ:tema_repetitivo:908",
        "STJ:tema_repetitivo:357",
        "STJ:tema_repetitivo:133",
        "STJ:iac:12",
    }
    assert by_id["STJ:tema_repetitivo:357"][3:5] == ("Cancelado", "cancelado")
    assert by_id["STJ:tema_repetitivo:133"][3:5] == ("Afetado - Possível Revisão de Tese", "vigente")
    assert "catalogo-temas-1" in DERIVER


def test_publication_derives_the_catalog_from_the_preserved_original(published):
    view = api._view(published, None, None)
    with connection(view.path) as db:
        rows = db.execute("SELECT id,situacao_fonte,coletado_em FROM theme_catalog ORDER BY id").fetchall()
        served = db.execute("SELECT id FROM precedents").fetchall()
    assert [tuple(r) for r in rows] == [
        ("STJ:iac:12", "Acórdão Publicado", "2026-09-29T20:22:29+00:00"),
        ("STJ:tema_repetitivo:133", "Afetado - Possível Revisão de Tese", "2026-09-29T20:22:29+00:00"),
        ("STJ:tema_repetitivo:357", "Cancelado", "2026-09-29T20:22:29+00:00"),
        ("STJ:tema_repetitivo:908", "Trânsito em Julgado", "2026-09-29T20:22:29+00:00"),
    ]
    assert [r[0] for r in served] == ["STJ:tema_repetitivo:908"]  # the catalog admits nothing


def test_search_by_number_says_cancelado_segundo_a_fonte_and_serves_no_thesis(published):
    page = api.search_precedents(published, numero="357")
    assert page["total_encontrado"] == 0 and page["motivo"] == "filtro_restritivo"
    assert page["situacao_na_fonte"] == [
        {
            "id": "STJ:tema_repetitivo:357",
            "numero": "357",
            "situacao_fonte": "Cancelado",
            "situacao": "cancelado",
            "fonte": TEMAS_URL,
            "coletado_em": "2026-09-29T20:22:29+00:00",
            "nota": NOTA,
        }
    ]
    assert "Questão cancelada" not in json.dumps(page, ensure_ascii=False)
    assert "situacao_na_fonte" not in api.search_precedents(published, numero="999")
    assert "situacao_na_fonte" not in api.search_precedents(published, numero="357", tribunal="STF")
    served = api.search_precedents(published, numero="908")["resultados"][0]
    assert served["situacao_fonte"] == "Trânsito em Julgado" and served["situacao"] == "vigente"
    first = api.document(published, "STJ:tema_repetitivo:908")
    assert first["metadados"]["situacao_fonte"] == "Trânsito em Julgado"


def test_document_of_a_cancelled_theme_is_refused_with_the_source_situation(published):
    with pytest.raises(FloraError) as info:
        api.document(published, "STJ:tema_repetitivo:357")
    assert info.value.code == "precedente_nao_servido" and "Cancelado" in str(info.value)
    assert "2026-09-29" in str(info.value)
    with pytest.raises(FloraError) as absent:
        api.document(published, "STJ:tema_repetitivo:5000")
    assert absent.value.code == "documento_nao_encontrado"


def test_conferir_referencias_uses_the_catalog(published):
    answer = api.check_references(published, ["Tema 357", "Tema 5000", "Tema 908", "Súmula 7 do STJ"])
    states = [i["estado"] for i in answer["referencias"]]
    assert states == ["nao_localizado", "inexistente_na_fonte", "localizado", "nao_localizado"]
    cancelled, absent, served = answer["referencias"][:3]
    assert cancelled["situacao_fonte"] == "Cancelado" and cancelled["catalogo"]["fonte"] == TEMAS_URL
    assert absent["catalogo"]["coletado_em"] == "2026-09-29T20:22:29+00:00"
    assert served["precedente"]["situacao_fonte"] == "Trânsito em Julgado"
    assert answer["resumo"]["inexistente_na_fonte"] == 1


def test_without_a_preserved_temas_csv_the_catalog_is_empty_and_nothing_changes(store, tmp_path):
    from test_precedents import packet

    ingest(store, [raw_doc("1")])
    migrate(store)
    import_package(store, packet(tmp_path), apply=True)
    assert publish(store)["catalogo_temas"] == {"temas": 0, "fonte": None}
    assert "situacao_na_fonte" not in api.search_precedents(store, numero="357")
    assert api.check_references(store, ["Tema 357"])["referencias"][0]["estado"] == "nao_localizado"
