"""Educação no TJSC por consulta de tema: órgãos de direito público, filtro, coleta e as três fases."""

import importlib.util
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from flora_mcp.config import Config
from flora_mcp.model import FloraError
from flora_mcp.store import connection
from flora_mcp.tema import educacao
from flora_mcp.tjsc import catalog_window, collect_pages, collect_search, collect_union, collect_window
from flora_mcp.tjsc_orgaos import PUBLICO, dataset

FIXTURES = Path(__file__).parent / "fixtures" / "tjsc"
# A real page with two cards of the Grupo de Câmaras de Direito Civil (latin-1), renamed to public law.
PAGE = (
    (FIXTURES / "processo-cnj-dois-acordaos.html")
    .read_bytes()
    .replace(
        "Grupo de Câmaras de Direito Civil".encode("latin-1"),
        "Grupo de Câmaras de Direito Público".encode("latin-1"),
    )
)
GRUPO = "Grupo de Câmaras de Direito Público"
EMPTY = (FIXTURES / "processo-sem-resultado.html").read_bytes()
# The same page declaring 25 results: a period that answers this has to be split.
CROWDED = PAGE.replace(b'type="hidden" value="2"', b'type="hidden" value="25"')

spec = importlib.util.spec_from_file_location(
    "coleta_educacao_tjsc", Path(__file__).parents[1] / "scripts/coleta_educacao_tjsc.py"
)
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)


def test_public_law_enters_only_by_theme_search(store):
    assert len(PUBLICO) == 6 and dataset(GRUPO) == "tjsc-grupo-de-camaras-de-direito-publico"
    for call in (
        lambda: catalog_window(store, "1ª Câmara de Direito Público", date(2026, 1, 5)),
        lambda: collect_window(None, Config(store.directory), GRUPO, date(2026, 1, 5)),
    ):
        with pytest.raises(FloraError) as info:
            call()
        assert info.value.code == "orgao_so_por_tema"


@pytest.mark.parametrize(
    "ementa,motivo",
    [
        ("APELAÇÃO. ECA. VAGA EM CRECHE. DEVER DO MUNICÍPIO. Recurso desprovido.", "verbetacao: vaga"),
        ("REEXAME NECESSÁRIO. SEGUNDO PROFESSOR PARA ALUNO COM AUTISMO.\n1. Cabe.", "verbetacao: apoio"),
        ("AGRAVO. DIREITO FUNDAMENTAL À EDUCAÇÃO. TRANSPORTE GRATUITO.\n1. Devido.", "verbetacao: direito"),
        ("AÇÃO CIVIL PÚBLICA. ACESSIBILIDADE EM ESCOLA MUNICIPAL.\n1. Obras devidas.", "verbetacao: acess"),
        ("APELAÇÃO. REFORMA DA ESCOLA ESTADUAL. SEGURANÇA DOS EDUCANDOS.\n1. Cabe.", "verbetacao: estrutura"),
        # Barrier words do not stop the explicit right: a servant's child and the vacancy in a crèche.
        ("APELAÇÃO. FILHO DE SERVIDOR. VAGA EM CRECHE.\n1. Devida.", "verbetacao: vaga"),
    ],
)
def test_education_enters_by_a_mark_of_the_pupils_right(ementa, motivo):
    assert educacao(ementa).startswith(motivo)


@pytest.mark.parametrize(
    "ementa",
    [
        "APELAÇÃO. SERVIDOR PÚBLICO. PROFESSOR. PISO SALARIAL DO MAGISTÉRIO.\n1. Devido.",
        "AGRAVO. FUNDAÇÃO CATARINENSE DE EDUCAÇÃO ESPECIAL. GRATIFICAÇÃO DE PRODUTIVIDADE.\n1. Devida.",
        "APELAÇÃO. EQUIPARAÇÃO SALARIAL. PROFESSOR AUXILIAR DE SALA.\n1. Indevida.",
        "APELAÇÃO. PREVIDENCIÁRIO. APOSENTADORIA POR INVALIDEZ. ESCOLARIDADE.\n1. Devida.",
        "APELAÇÃO. RESPONSABILIDADE CIVIL. QUEDA DE ALUNO NA ESCOLA.\n1. Indenização.",
        "APELAÇÃO. CONCURSO PÚBLICO. PROFESSOR DE EDUCAÇÃO ESPECIAL.\n1. Nomeação.",
        "MANDADO DE SEGURANÇA. TRANSPORTE.\n1. Garantido, nos termos do art. 208 da CF.",
        "AGRAVO. LICITAÇÃO. PREGÃO PARA TRANSPORTE ESCOLAR. HABILITAÇÃO.\n1. Mantida.",
        "APELAÇÃO. COBRANÇA. CONTRATO DE TRANSPORTE ESCOLAR. PRESCRIÇÃO.\n1. Afastada.",
        "APELAÇÃO. CONCURSO PÚBLICO. VAGAS NA REDE DE ENSINO.\n1. Nomeação indevida.",
        "AGRAVO. PRODUÇÃO ANTECIPADA DE PROVAS. IMAGENS DE CÂMERA DE CRECHE.\n1. Cabe.",
        "APELAÇÃO. REGISTRO DE IMÓVEIS. MATRÍCULA. RETIFICAÇÃO.\n1. Cabe.",
        "TRIBUTÁRIO. IPTU. RECURSO ESPECIAL.\n1. Educação especial não se discute.",
    ],
)
def test_other_matters_stay_out(ementa):
    assert educacao(ementa) is None


def test_theme_search_sends_term_organ_and_period_and_checks_every_card(store):
    sent = []

    def route(req):
        sent.append(parse_qs(req.content.decode()))
        return httpx.Response(200, content=PAGE)

    config = Config(store.directory, request_delay=0)
    with httpx.Client(transport=httpx.MockTransport(route)) as http:
        content, rows = collect_search(http, config, GRUPO, "creche", date(2022, 1, 1), date(2026, 10, 24))
        envelope = json.loads(content)
        assert (envelope["consulta"], envelope["orgao"], envelope["termo"], envelope["total"]) == (
            "tema",
            GRUPO,
            "creche",
            2,
        )
        assert {v["txtPesquisa"][0] for v in sent} == {"creche"} and {v["selOrgao[]"][0] for v in sent} == {
            GRUPO
        }
        assert len(rows) == 2
        with pytest.raises(FloraError) as info:
            collect_search(http, config, GRUPO, "creche", date(2024, 1, 1), date(2026, 10, 24))
        assert info.value.code == "filtro_nao_respeitado"  # the fixture cards are from 2022 and 2023


def test_period_with_more_than_one_page_is_split_until_each_part_fits_one(store):
    sent = []

    def route(req):
        values = parse_qs(req.content.decode())
        start, end = (
            date(*reversed([int(x) for x in values[k][0].split("/")]))
            for k in ("dtPublicacaoInicio", "dtPublicacaoFim")
        )
        sent.append((start, end))
        if (end - start).days > 1700:
            return httpx.Response(200, content=CROWDED)
        # The fixture cards are of 10/08/2022 and 09/08/2023.
        return httpx.Response(
            200, content=PAGE if start <= date(2022, 8, 10) and date(2023, 8, 9) <= end else EMPTY
        )

    with httpx.Client(transport=httpx.MockTransport(route)) as http:
        content, rows = collect_search(
            http,
            Config(store.directory, request_delay=0),
            GRUPO,
            "ensino",
            date(2022, 1, 1),
            date(2026, 10, 24),
        )
    envelope = json.loads(content)
    assert len(rows) == envelope["total"] == 2
    assert [(p["publicacao_inicio"], p["publicacao_fim"]) for p in envelope["sondagens"]] == [
        ("2022-01-01", "2026-10-24")
    ]
    assert [(p["publicacao_inicio"], p["total"]) for p in envelope["partes"]] == [
        ("2022-01-01", 2),
        ("2024-05-29", 0),
    ]
    assert len(sent) == 5  # the crowded probe, then a probe and the final recheck of each half


def test_a_part_answered_with_a_repeated_acordao_is_tried_again(store):
    first, second = re.findall(rb'id="resultado(\d+)"', PAGE)[:2]
    repeated = PAGE.replace(b'id="resultado' + second + b'"', b'id="resultado' + first + b'"')
    answers = iter([repeated, PAGE, PAGE, PAGE])
    with httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, content=next(answers)))
    ) as http:
        content, rows = collect_search(
            http,
            Config(store.directory, request_delay=0),
            GRUPO,
            "creche",
            date(2022, 1, 1),
            date(2023, 12, 31),
        )
    assert len(rows) == 2 and json.loads(content)["partes"][0]["tentativas"] == 2
    always = httpx.MockTransport(lambda req: httpx.Response(200, content=repeated))
    with httpx.Client(transport=always) as http, pytest.raises(FloraError) as info:
        collect_search(
            http,
            Config(store.directory, request_delay=0),
            GRUPO,
            "creche",
            date(2022, 1, 1),
            date(2023, 12, 31),
        )
    assert info.value.code == "paginacao_instavel"


def test_crowded_day_adds_passes_until_the_distinct_acordaos_reach_the_total(store):
    def row(n):
        return ({"id": f"TJSC:{n:02d}"}, {"id": str(n)})

    # Each pass returns the two pages in another order: 10 + 2 rows, overlapping across pages.
    passes = [[list(range(1, 11)), [1, 2]], [list(range(3, 13)), [11, 12]]]
    answers = iter(page for each in passes for page in each)
    config = Config(store.directory, request_delay=0)
    parse = lambda _content: (12, [row(n) for n in next(answers)])  # noqa: E731
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, content=b"x"))) as http:
        total, pages, rows = collect_union(http, config, {}, parse, 12, b"first")
        assert (total, len(pages), [r[0]["id"] for r in rows]) == (
            12,
            4,
            [f"TJSC:{n:02d}" for n in range(1, 13)],
        )
        short = iter([list(range(1, 11)), [1, 2]] * 6)
        never = lambda _content: (12, [row(n) for n in next(short)])  # noqa: E731
        with pytest.raises(FloraError) as info:
            collect_union(http, config, {}, never, 12, b"first")
    assert info.value.code == "paginacao_incompleta"


def test_single_page_may_return_in_another_order_but_not_with_other_documents(store):
    rows = [({"id": "TJSC:1"}, {"id": "1"}), ({"id": "TJSC:2"}, {"id": "2"})]
    answers = iter([rows, list(reversed(rows)), rows, rows[:1] + [({"id": "TJSC:3"}, {"id": "3"})]])
    config = Config(store.directory, request_delay=0)
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, content=b"x"))) as http:
        assert collect_pages(http, config, {}, lambda _content: (2, next(answers)))[0] == 2
        with pytest.raises(FloraError) as info:
            collect_pages(http, config, {}, lambda _content: (2, next(answers)))
    assert info.value.code == "janela_alterada"


def fake_search(passing_text):
    def collect(_http, _config, organ, term, start, end):
        rows = []
        for n, text in enumerate((passing_text, "TRIBUTÁRIO. IPTU.\n1. Devido.")):
            source = f"{dataset(organ)}-{term}-{n}"
            body = {
                "id": "TJSC:" + source,
                "id_origem": source,
                "tribunal": "TJSC",
                "orgao": organ,
                "classe": "APL",
                "processo": f"500{n}000-00.2023.8.24.0000",
                "numero_processo": f"500{n}000-00.2023.8.24.0000",
                "numero_registro": "",
                "data_julgamento": "2023-05-02",
                "data_publicacao": "2023-05-03",
                "ementa": text,
            }
            rows.append((body, {"id": source, "campos": {"EMENTA": text}}))
        return json.dumps({"orgao": organ, "termo": term}).encode(), rows

    return collect


def test_three_phases_stage_sample_and_ingest_only_what_passes(store, tmp_path, monkeypatch):
    monkeypatch.setattr(script, "collect_search", fake_search("APELAÇÃO. VAGA EM CRECHE.\n1. Devida."))
    config = Config(store.directory, request_delay=0)
    preparo, todas = tmp_path / "preparo", script.consultas(date(2022, 1, 1), date(2026, 10, 24))
    script.candidatos(config, preparo, todas)
    registros = script.ler_preparo(preparo, todas)
    total, passam = script.resumo(registros)
    assert total == {"consultas": 72, "acordaos_unicos": 144, "passam_unicos": 72} and len(passam) == 72
    script.amostra(registros, 7, tmp_path / "amostra.json", tmp_path / "chave.json")
    cego = json.loads((tmp_path / "amostra.json").read_text(encoding="utf-8"))
    assert len(cego["itens"]) == 50 and all("id" not in item for item in cego["itens"])
    # A second sample leaves out what the first one showed: only 22 others pass.
    novo = script.amostra(
        registros, 8, tmp_path / "a2.json", tmp_path / "c2.json", (tmp_path / "chave.json",)
    )
    primeira, segunda = (
        json.loads((tmp_path / n).read_text(encoding="utf-8"))["codigos"] for n in ("chave.json", "c2.json")
    )
    assert (
        novo["excluidos"] == 50 and len(segunda) == 22 and not set(primeira.values()) & set(segunda.values())
    )
    juizo = {item["codigo"]: {"no_tema": True, "razao": "creche"} for item in cego["itens"]}
    for codigo in list(juizo)[:6]:
        juizo[codigo] = {"no_tema": False, "razao": "fora"}
    (tmp_path / "julgamento.json").write_text(json.dumps(juizo), encoding="utf-8")
    with pytest.raises(ValueError, match="reprovada"):
        script.aprovar(tmp_path / "julgamento.json", tmp_path / "chave.json")
    juizo = {k: {"no_tema": i >= 5, "razao": "r"} for i, k in enumerate(juizo)}
    (tmp_path / "julgamento.json").write_text(json.dumps(juizo), encoding="utf-8")
    aprovacao = script.aprovar(tmp_path / "julgamento.json", tmp_path / "chave.json")
    assert (aprovacao["no_tema"], aprovacao["taxa"]) == (45, 0.9)
    report = script.aplicar(config, store, registros, aprovacao, tmp_path / "recibo.json", tmp_path / "bk")
    assert report["status"] == "ok" and len(report["eventos"]) == 72
    with connection(store.path) as db:
        assert db.execute("SELECT count(*) FROM documents").fetchone()[0] == 72
        rejeitados = db.execute(
            "SELECT rejeitados FROM resources WHERE id LIKE 'tjsc-%:tema-%' LIMIT 1"
        ).fetchone()[0]
    assert json.loads(rejeitados)[0]["motivo"] == "fora_do_tema: educacao-3"
    again = script.aplicar(config, store, registros, aprovacao, tmp_path / "recibo2.json", tmp_path / "bk")
    assert again["pendentes"] == 0 and again["eventos"] == []
