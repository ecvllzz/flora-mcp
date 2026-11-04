"""Deriver citacoes-2 and ementa-secoes-3: keys that were wrong, ambiguity marked, DISPOSITIVO alone."""

import json

from conftest import ingest, raw_doc
from test_citacoes import keys, tjsc_body
from test_precedents import packet

from flora_mcp import api, citations
from flora_mcp.precedents import import_package, migrate
from flora_mcp.publication import DERIVER, publish
from flora_mcp.store import connection
from flora_mcp.text import SECTIONS_DERIVER, sections


def test_irdr_named_by_its_cnj_process_number_is_not_irdr_5011():
    ementa = (
        "GUARDA.\r\nJurisprudência relevante citada: TJSC, IRDR n. 5011469-46.2022.8.24.0000; "
        "TJSC, IRDR n. 17; TJSC, IAC n. 5000000-00.2020.8.24.0000, rel. Des. Exemplo."
    )
    items = citations.extract(tjsc_body(ementa=ementa), {})
    assert keys(items, "precedente") == ["", "TJSC:irdr:17", ""]
    assert keys(items, "acordao") == ["TJSC:50114694620228240000", "TJSC:50000000020208240000"]
    assert items[0]["texto"].startswith("IRDR n. 5011469-46.2022.8.24.0000")


def test_stj_summary_line_that_says_stf_gets_the_stf_key_even_when_indented():
    raw = raw_doc(
        "9",
        referenciasLegislativas=[
            "LEG:FED SUM:****** ANO:****\n *****  SUM(STF)    SÚMULA DO SUPREMO TRIBUNAL FEDERAL\n"
            "         SUM:000735",
            "LEG:FED SUM:****** ANO:****\n*****  SUM(STJ)    SÚMULA DO STJ\n        SUM:000007",
        ],
    )
    items = citations.extract({"id": "STJ:9", "tribunal": "STJ"}, raw)
    assert keys(items, "precedente") == ["STF:sumula:735", "STJ:sumula:7"]


def test_bare_dispositivo_heading_is_the_fourth_section():
    text = (
        "VERBETE.\r\nI. CASO EM EXAME\r\n1. Apelação.\r\nII. QUESTÃO EM DISCUSSÃO\r\n2. Saber.\r\n"
        "III. RAZÕES DE DECIDIR\r\n3. Porque.\r\nIV. DISPOSITIVO\r\n4. Recurso desprovido.\r\n"
        "Dispositivos relevantes citados: CC, art. 1.694."
    )
    names = [s["nome"] for s in sections(text)]
    assert names == [
        "cabecalho",
        "caso_em_exame",
        "questao_em_discussao",
        "razoes_de_decidir",
        "dispositivo_e_tese",
        "dispositivos_citados",
    ]
    assert sections(text)[0]["derivador"] == SECTIONS_DERIVER == "ementa-secoes-3"
    # Still refused: a repeated heading, and DISPOSITIVO as a word inside a line.
    assert sections("A.\nIV. DISPOSITIVO\nx\nIV. DISPOSITIVO\ny") == []
    assert [s["nome"] for s in sections("A.\nIV. DISPOSITIVO E TESE\nx")] == [
        "cabecalho",
        "dispositivo_e_tese",
    ]
    assert "ementa-secoes-3" in DERIVER and "citacoes-2" in DERIVER


def test_key_that_fits_several_acordaos_is_marked_ambiguous_not_picked(store, tmp_path):
    cited = raw_doc("1", numeroProcesso="1497831", siglaClasse="REsp", text="Juros. Primeiro.")
    again = raw_doc(
        "3", numeroProcesso="1497831", siglaClasse="REsp", text="Juros. Embargos.", dataDecisao="20260901"
    )
    citing = raw_doc(
        "2",
        numeroProcesso="1805335",
        siglaClasse="AgInt no REsp",
        text="Revisão.",
        jurisprudenciaCitada=(
            "(X)\n   STJ - <<REsp 1497831>>-PR (RECURSO REPETITIVO - TEMA(s) 908),\n"
            "   <<AgInt no AREsp 1>>-SP"
        ),
    )
    single = raw_doc("4", numeroProcesso="1", siglaClasse="AgInt no AREsp", text="Único.")
    ingest(store, [cited, again, citing, single])
    migrate(store)
    import_package(store, packet(tmp_path, species="tema_repetitivo", number="908"), apply=True)
    publish(store)
    view = api._view(store, None, None)
    with connection(view.path) as db:
        rows = db.execute(
            "SELECT chave,resolvido,candidatos FROM document_citations WHERE document_id='STJ:2' "
            "ORDER BY rowid"
        ).fetchall()
        links = db.execute("SELECT * FROM citation_links ORDER BY cited_id").fetchall()
    assert [tuple(r) for r in rows] == [
        ("STJ:RESP:1497831", None, '["STJ:1","STJ:3"]'),
        ("STJ:tema_repetitivo:908", "STJ:tema_repetitivo:908", None),
        ("STJ:AGINT NO ARESP:1", "STJ:4", None),
    ]
    assert [tuple(r) for r in links] == [("STJ:2", "STJ:1", 1), ("STJ:2", "STJ:3", 1), ("STJ:2", "STJ:4", 0)]
    listed = json.loads(api.document(store, "STJ:2", "citacoes")["texto"])
    assert listed[0]["resolvido"] is None and listed[0]["candidatos"] == ["STJ:1", "STJ:3"]
    assert "candidatos" not in listed[2] and listed[2]["resolvido"] == "STJ:4"
    summary = api.document(store, "STJ:2")["metadados"]["citacoes"]
    assert summary["resolvidas_no_acervo"] == 2 and summary["ambiguas_no_acervo"] == 1
