"""Citations as data: extraction from the stored originals, derivation at publish, filters and component."""

import json

import pytest
from conftest import ingest, raw_doc
from test_precedents import packet

from flora_mcp import api, citations
from flora_mcp.model import FloraError
from flora_mcp.precedents import import_package, migrate
from flora_mcp.publication import publish
from flora_mcp.store import connection

TJSC_EMENTA = (
    "DIREITO CIVIL. FAMÍLIA. GUARDA.\r\nI. CASO EM EXAME\r\n1. Apelação.\r\nII. QUESTÃO EM DISCUSSÃO\r\n"
    "2. Saber se cabe.\r\nIII. RAZÕES DE DECIDIR\r\n3. Cabe.\r\nIV. DISPOSITIVO E TESE\r\n"
    "4. Recurso desprovido.\r\n"
    "Dispositivos relevantes citados: CC, arts. 1.634; 1.635, V; CPC, arts. 85, § 11, 1.022; "
    "Lei n. 8.560/1992, art. 2º, § 1º; CF/1988, art. 5º, XXXV e LV.\r\n"
    "Jurisprudência relevante citada: STJ, AgInt no AREsp 1.779.343/DF, Rel. Ministro Marco Aurélio "
    "Bellizze, Terceira Turma, j. 12/4/2021; STJ, REsp 1.497.831/PR, Tema 908; TJSC, Apelação n. "
    "5002677-98.2022.8.24.0034, rel. Edir Josias Silveira Beck, j. 05-10-2023; TJSC, AC 2006.011052-9, "
    "Rel. Des. Monteiro Rocha, j. 05/12/2016; STF, ADC n. 80; Súmula 7 do STJ; STJ, Agravo Interno no "
    "Recurso Especial n. 1357561/MG; TJ-PR, AI n. 0013506-22.2023.8.16.0000, rel. Des. Eduardo Cambi."
)


def tjsc_body(id="321", ementa=TJSC_EMENTA, process="5002677-98.2022.8.24.0034"):
    return {
        "id": "TJSC:" + id,
        "id_origem": id,
        "tribunal": "TJSC",
        "orgao": "10ª Câmara de Direito Civil",
        "classe": "APCIV",
        "processo": process,
        "numero_processo": process,
        "numero_registro": "",
        "data_julgamento": "2026-09-10",
        "data_publicacao": "2026-09-12",
        "ementa": ementa,
    }


def keys(items, tipo):
    return [i["chave"] for i in items if i["tipo"] == tipo]


def test_tjsc_closing_lines_become_keys_and_unparsed_fragments_keep_their_text():
    items = citations.extract(tjsc_body(), {"id": "321"})
    assert keys(items, "dispositivo") == [
        "CC:1634",
        "CC:1635",
        "CPC:85",
        "CPC:1022",
        "LEI 8.560/1992:2",
        "CF:5",
    ]
    assert keys(items, "precedente") == ["STJ:tema_repetitivo:908", "STJ:sumula:7"]
    assert keys(items, "acordao") == [
        "STJ:AGINT NO ARESP:1779343",
        "STJ:RESP:1497831",
        "TJSC:50026779820228240034",
        "TJSC:20060110529",
        "STF:ADC:80",
        "STJ:AGINT NO RESP:1357561",
        "TJPR:00135062220238160000",
    ]
    cf = next(i for i in items if i["chave"] == "CF:5")
    assert "XXXV e LV" in cf["texto"] and cf["origem"] == "ementa_cnj:dispositivos_citados"


def test_tjsc_without_closing_lines_and_other_courts_yield_nothing_or_unkeyed():
    assert citations.extract(tjsc_body(ementa="Guarda. Sem linhas finais."), {}) == []
    items = citations.extract(
        tjsc_body(ementa="Jurisprudência relevante citada: Enunciado 110 da II Jornada; TJSC, Súmula 34."), {}
    )
    assert [(i["tipo"], i["chave"]) for i in items] == [("acordao", ""), ("precedente", "")]


def test_stj_mirror_fields_become_keys():
    raw = raw_doc(
        "9",
        jurisprudenciaCitada=(
            "(REVISÃO CONTRATUAL)\n   STJ - <<REsp 1497831>>-PR (RECURSO REPETITIVO - TEMA(s) 908),\n"
            "         <<AgInt no REsp 1805335>>-PR\n(OUTRO)\n   STF - <<RE 123456>>-SP"
        ),
        referenciasLegislativas=[
            "LEG:FED LEI:013105 ANO:2015\n*****  CPC-15    CPC\n        ART:00085 PAR:00011 ART:01022",
            "LEG:FED LEI:009656 ANO:1998\n*****  LPSS-98    LEI DE PLANOS\n        ART:00010 INC:00006",
            "LEG:FED SUM:****** ANO:****\n*****  SUM(STJ)    SÚMULA DO STJ\n        SUM:000005 SUM:000007",
            "LEG:FED CFB:****** ANO:1988\n*****  CF-1988    CONSTITUIÇÃO\n        ART:00005 INC:00055",
            "LEG:FED RGI:****** ANO:1989\n*****  RISTJ-89    REGIMENTO INTERNO\n        ART:0184D",
        ],
        tema="Tema Repetitivo 1310\nSituação do tema: Afetado",
        acordaosSimilares=[
            "AgInt no AREsp  2613323  SP  2024/0132315-6  Decisão:16/12/2024\nDJEN",
            "EDcl no REsp 2219460 PR 2025/0219918-8 Decisão:24/08/2026",
        ],
    )
    items = citations.extract({"id": "STJ:9", "tribunal": "STJ"}, raw)
    assert keys(items, "dispositivo") == ["CPC:85", "CPC:1022", "LEI 9.656/1998:10", "CF:5", "RISTJ:184-D"]
    assert keys(items, "precedente") == [
        "STJ:sumula:5",
        "STJ:sumula:7",
        "STJ:tema_repetitivo:908",
        "STJ:tema_repetitivo:1310",
    ]
    assert keys(items, "acordao") == ["STJ:RESP:1497831", "STJ:AGINT NO RESP:1805335", "STF:RE:123456"]
    assert keys(items, "similar") == ["STJ:AGINT NO ARESP:2613323", "STJ:EDCL NO RESP:2219460"]


@pytest.mark.parametrize(
    "tipo,value,expected",
    [
        ("precedente", "Tema 1.076", "STJ:tema_repetitivo:1076"),
        ("precedente", "tema 908 do STJ", "STJ:tema_repetitivo:908"),
        ("precedente", "Súmula 7 do STJ", "STJ:sumula:7"),
        ("precedente", "STF, Súmula Vinculante 10", "STF:sumula_vinculante:10"),
        ("precedente", "STJ:tema_repetitivo:908", "STJ:tema_repetitivo:908"),
        ("precedente", "IRDR 17", "TJSC:irdr:17"),
        ("dispositivo", "CPC art. 85", "CPC:85"),
        ("dispositivo", "art. 85, § 11, do CPC", "CPC:85"),
        ("dispositivo", "art. 1.634 do Código Civil", "CC:1634"),
        ("dispositivo", "Lei n. 8.560/1992, art. 2º", "LEI 8.560/1992:2"),
        ("dispositivo", "CF/88, art. 5º", "CF:5"),
        ("acordao", "5002677-98.2022.8.24.0034", "TJSC:50026779820228240034"),
        ("acordao", "TJSP, 1000000-00.2020.8.26.0100", "TJSP:10000000020208260100"),
        ("acordao", "AgInt no AREsp 1.779.343/DF", "STJ:AGINT NO ARESP:1779343"),
        ("acordao", "STJ, Agravo Interno no Recurso Especial 1357561", "STJ:AGINT NO RESP:1357561"),
        ("acordao", "AC 2006.011052-9", "TJSC:20060110529"),
    ],
)
def test_filter_values_normalize_as_the_extraction(tipo, value, expected):
    assert citations.filter_key(tipo, value) == expected


@pytest.mark.parametrize(
    "tipo,value",
    [("precedente", "qualquer coisa"), ("dispositivo", "art. 85"), ("acordao", "123"), ("precedente", "")],
)
def test_unrecognized_filter_values_raise(tipo, value):
    with pytest.raises(ValueError):
        citations.filter_key(tipo, value)


@pytest.fixture
def published(store, tmp_path):
    cited = raw_doc("1", numeroProcesso="1497831", siglaClasse="REsp", text="Juros. Tema 908.")
    citing = raw_doc(
        "2",
        numeroProcesso="1805335",
        siglaClasse="AgInt no REsp",
        text="Revisão.",
        jurisprudenciaCitada="(X)\n   STJ - <<REsp 1497831>>-PR (RECURSO REPETITIVO - TEMA(s) 908)",
        referenciasLegislativas=["LEG:FED LEI:013105 ANO:2015\n*****  CPC-15    CPC\n        ART:00085"],
    )
    ingest(store, [cited, citing])
    migrate(store)
    import_package(store, packet(tmp_path, species="tema_repetitivo", number="908"), apply=True)
    publish(store)
    return store


def test_publication_derives_citations_resolved_against_the_generation(published):
    with connection(api._view(published, None, None).path) as db:
        rows = db.execute(
            "SELECT document_id,tipo,chave,resolvido FROM document_citations ORDER BY document_id,rowid"
        ).fetchall()
    assert [tuple(r) for r in rows] == [
        ("STJ:2", "dispositivo", "CPC:85", None),
        ("STJ:2", "acordao", "STJ:RESP:1497831", "STJ:1"),
        ("STJ:2", "precedente", "STJ:tema_repetitivo:908", "STJ:tema_repetitivo:908"),
    ]


def test_search_filters_by_citation_and_reports_the_key(published):
    by_theme = api.search(published, cita_precedente="Tema 908")
    assert [r["id"] for r in by_theme["resultados"]] == ["STJ:2"]
    assert by_theme["citacoes_filtradas"] == {"cita_precedente": "STJ:tema_repetitivo:908"}
    by_acordao = api.search(published, cita_acordao="REsp 1.497.831/PR", ordenar="mais_recentes")
    assert [r["id"] for r in by_acordao["resultados"]] == ["STJ:2"]
    assert api.search(published, cita_dispositivo="CPC art. 85")["total_encontrado"] == 1
    assert api.search(published, cita_dispositivo="CPC art. 1.022")["total_encontrado"] == 0
    assert api.search(published, "juros")["total_encontrado"] == 1 and "citacoes_filtradas" not in api.search(
        published, "juros"
    )
    with pytest.raises(FloraError, match="cita_dispositivo"):
        api.search(published, cita_dispositivo="artigo")


def test_citation_filters_need_a_publication(store):
    ingest(store, [raw_doc("1")])
    with pytest.raises(FloraError, match="publicação"):
        api.search(store, cita_precedente="Tema 908")


def test_component_citacoes_and_first_block_summary(published):
    first = api.document(published, "STJ:2")
    assert first["metadados"]["citacoes"] == {
        "total": 3,
        "por_tipo": {"precedente": 1, "acordao": 1, "dispositivo": 1, "similar": 0},
        "resolvidas_no_acervo": 2,
        "componente": "citacoes",
    }
    block = api.document(published, "STJ:2", "citacoes")
    listed = json.loads(block["texto"])
    assert [(i["tipo"], i["chave"], i["resolvido"]) for i in listed] == [
        ("dispositivo", "CPC:85", None),
        ("acordao", "STJ:RESP:1497831", "STJ:1"),
        ("precedente", "STJ:tema_repetitivo:908", "STJ:tema_repetitivo:908"),
    ]
    assert block["fim"] and block["componente"] == "citacoes"
    with pytest.raises(FloraError, match="citacoes"):
        api.document(published, "STJ:2", "resumo")


def test_publication_without_the_derived_table_still_reads_and_refuses_filters(published, monkeypatch):
    monkeypatch.setattr("flora_mcp.query.has_citations", lambda db: False)
    first = api.document(published, "STJ:2")
    assert first["metadados"]["citacoes"]["total"] == 3
    assert first["metadados"]["citacoes"]["resolvidas_no_acervo"] == 0
    with pytest.raises(FloraError, match="citacoes-1"):
        api.search(published, cita_precedente="Tema 908")
