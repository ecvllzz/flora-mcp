"""Educação no TJSC por consulta de tema: órgãos de direito público, filtro, coleta e as três fases."""

import importlib.util
import json
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from flora_mcp.config import Config
from flora_mcp.model import FloraError
from flora_mcp.store import connection
from flora_mcp.tema import educacao
from flora_mcp.tjsc import catalog_window, collect_search, collect_window
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
        ("APELAÇÃO. ECA. VAGA EM CRECHE. DEVER DO MUNICÍPIO. Recurso desprovido.", "verbetacao: creche"),
        (
            "REEXAME NECESSÁRIO. SEGUNDO PROFESSOR PARA ALUNO COM AUTISMO.\n1. Cabe.",
            "verbetacao: segundo prof",
        ),
        ("MANDADO DE SEGURANÇA. TRANSPORTE.\n1. Garantido, nos termos do art. 208 da CF.", "legislacao: CF"),
        ("APELAÇÃO. OBRIGAÇÃO DE FAZER.\n1. Lei n. 9.394/1996 assegura o atendimento.", "legislacao: LDB"),
        ("AGRAVO. PROTEÇÃO.\n1. O art. 54 do ECA garante o acesso.", "legislacao: ECA"),
        ("AGRAVO. INCLUSÃO.\n1. Lei 13.146/2015, art. 28, impõe o apoio.", "legislacao: Lei 13.146"),
    ],
)
def test_education_enters_by_heading_or_by_cited_law(ementa, motivo):
    assert educacao(ementa).startswith(motivo)


@pytest.mark.parametrize(
    "ementa",
    [
        "APELAÇÃO. SERVIDOR PÚBLICO. PROFESSOR. PISO SALARIAL DO MAGISTÉRIO.\n1. Devido.",
        "APELAÇÃO. REGISTRO DE IMÓVEIS. MATRÍCULA. RETIFICAÇÃO.\n1. Cabe.",
        "TRIBUTÁRIO. IPTU. RECURSO ESPECIAL.\n1. Educação especial não se discute.",
        "APELAÇÃO. SAÚDE. MEDICAMENTO.\n1. O art. 196 da CF assegura a saúde.",
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
    assert json.loads(rejeitados)[0]["motivo"] == "fora_do_tema: educacao"
    again = script.aplicar(config, store, registros, aprovacao, tmp_path / "recibo2.json", tmp_path / "bk")
    assert again["pendentes"] == 0 and again["eventos"] == []
