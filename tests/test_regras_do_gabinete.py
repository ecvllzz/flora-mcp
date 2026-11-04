"""M4: rules of the gabinete leave the code; the current configuration reproduces the old behaviour.

The inventory is docs/regras-do-gabinete.md. Each test compares what the server or the collector does
with no configuration against what it did before M4, and shows the configuration that keeps it.
"""

import asyncio
import json
from datetime import date

import pytest
from mcp.client.client import Client

from test_contrato import published  # noqa: F401  (fixture: acervo com publicação)
from flora_mcp import config as configuracao
from flora_mcp.config import FERRAMENTAS, Config, load_config
from flora_mcp.model import FloraError
from flora_mcp.server import DESCRIPTIONS, create_server
from flora_mcp.sources import probe_tjsc
from flora_mcp.tjsc import sync_tjsc
from flora_mcp.tjsc_orgaos import PADRAO

# What flora.local.toml of the gabinete holds on 04/11/2026: nothing beyond the folder and the pause.
GABINETE = "[flora]\ndata_dir = '{}'\nrequest_delay = 2.5\n"
# The sentences the descriptions carried before M4, now given by [flora.orientacoes] when wanted.
ORIENTACOES = {
    "pesquisar_jurisprudencia": (
        "O acervo tem acórdãos do STJ (Terceira e Quarta Turmas e Segunda Seção), de câmaras cíveis do "
        "TJSC e os de educação das Câmaras de Direito Público."
    ),
    "pesquisar_precedentes": "Súmula bancária é apoio: apresente antes as de civil e processual civil.",
}


def descriptions(orientacoes=None):
    tools = asyncio.run(create_server(None, orientacoes=orientacoes).list_tools())
    return {t.name: t.description for t in tools}


def test_descriptions_without_configuration_carry_no_rule_of_the_gabinete():
    plain = descriptions()
    assert set(plain) == set(DESCRIPTIONS) == set(FERRAMENTAS)
    for text in plain.values():
        assert "bancária" not in text and "Terceira" not in text and "Direito Público" not in text
        assert "câmaras cíveis" not in text
    # The organs whose precedents the source admits are the collection's scope, not a rule of the gabinete.
    assert "Grupo de Câmaras de Direito Civil" in plain["pesquisar_precedentes"]
    assert "consultar_cobertura" in plain["pesquisar_jurisprudencia"]
    assert "materia filtra" in plain["pesquisar_precedentes"]


def test_orientacoes_from_configuration_restore_the_sentences_of_the_gabinete():
    oriented = descriptions(ORIENTACOES)
    for name, sentence in ORIENTACOES.items():
        assert oriented[name] == DESCRIPTIONS[name] + " " + sentence
    assert oriented["obter_documento"] == DESCRIPTIONS["obter_documento"]
    with pytest.raises(ValueError, match="orientacoes"):
        create_server(None, orientacoes={"ferramenta_inexistente": "x"})


def test_gabinete_configuration_reads_the_same_defaults_as_before(tmp_path, monkeypatch):
    local = tmp_path / "flora.local.toml"
    local.write_text(GABINETE.format((tmp_path / "acervo").as_posix()), encoding="utf-8")
    monkeypatch.setattr(configuracao, "LOCAL_CONFIG", local)
    monkeypatch.delenv("FLORA_MCP_DATA_DIR", raising=False)
    config = load_config()
    assert config.request_delay == 2.5
    assert tuple(config.tjsc_orgaos) == PADRAO == tuple(f"{n}ª Câmara de Direito Civil" for n in range(1, 11))
    assert config.atrasos == {"STJ": 45, "TJSC": 7}
    assert config.orientacoes == {} and config.painel_nota is None
    assert config.datasets == [
        "espelhos-de-acordaos-terceira-turma",
        "espelhos-de-acordaos-quarta-turma",
        "espelhos-de-acordaos-segunda-secao",
    ]


def test_configured_organs_and_orientations_are_read_and_checked(tmp_path, monkeypatch):
    local = tmp_path / "flora.local.toml"
    monkeypatch.setattr(configuracao, "LOCAL_CONFIG", local)
    monkeypatch.delenv("FLORA_MCP_DATA_DIR", raising=False)
    base = f"[flora]\ndata_dir = '{(tmp_path / 'acervo').as_posix()}'\n"
    local.write_text(
        base
        + 'tjsc_orgaos = ["9ª Câmara de Direito Civil", "1ª Câmara Especial de Enfrentamento de Acervos"]\n'
        + "painel_nota = 'nota.md'\n[flora.orientacoes]\npesquisar_precedentes = 'Apoio.'\n",
        encoding="utf-8",
    )
    config = load_config()
    assert config.tjsc_orgaos == [
        "9ª Câmara de Direito Civil",
        "1ª Câmara Especial de Enfrentamento de Acervos",
    ]
    assert config.orientacoes == {"pesquisar_precedentes": "Apoio."} and config.painel_nota == "nota.md"
    for wrong, message in (
        ('tjsc_orgaos = ["Câmara Inexistente"]\n', "fora da lista"),
        ('tjsc_orgaos = ["1ª Câmara de Direito Público"]\n', "consulta de tema"),
        ("tjsc_orgaos = []\n", "tjsc_orgaos"),
        ('tjsc_orgaos = "9ª Câmara de Direito Civil"\n', "tjsc_orgaos"),
        ("[flora.orientacoes]\noutra = 'x'\n", "orientacoes"),
        ("[flora.orientacoes]\npesquisar_precedentes = 3\n", "orientacoes"),
    ):
        local.write_text(base + wrong, encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            load_config()


def test_collection_without_configuration_visits_the_same_windows_as_before(store, monkeypatch):
    visited = []

    def fetch(_http, _config, organ, day):
        visited.append((organ, day))
        return json.dumps({"fonte": "TJSC", "data_publicacao": str(day), "total": 0}).encode(), []

    monkeypatch.setattr("flora_mcp.tjsc.collect_window", fetch)
    config = Config(store.directory, request_delay=0)
    sync_tjsc(config, store, None, date(2026, 9, 1), date(2026, 9, 2))
    before = [(organ, day) for organ in PADRAO for day in (date(2026, 9, 1), date(2026, 9, 2))]
    assert visited == before
    visited.clear()
    chosen = Config(store.directory, request_delay=0, tjsc_orgaos=["10ª Câmara de Direito Civil"])
    sync_tjsc(chosen, store, None, date(2026, 9, 3), date(2026, 9, 3))
    assert visited == [("10ª Câmara de Direito Civil", date(2026, 9, 3))]


def test_probe_asks_the_portal_for_the_configured_organs(store, monkeypatch):
    asked = []

    def download(_http, _url, _limit, **kwargs):
        asked.append(kwargs["data"]["selOrgao[]"])
        raise FloraError("sem_rede", "sem rede no teste")

    monkeypatch.setattr("flora_mcp.sources.download", download)
    probe_tjsc(Config(store.directory, tjsc_orgaos=["3ª Câmara de Direito Civil"]), store, None)
    assert asked == ["3ª Câmara de Direito Civil"]


def test_responses_are_the_same_with_and_without_orientacoes(published):  # noqa: F811
    async def run():
        calls = [
            ("pesquisar_jurisprudencia", {"termos": "alimentos"}),
            ("pesquisar_precedentes", {"termos": "sintético"}),
            ("consultar_cobertura", {}),
        ]
        answers = []
        for orientacoes in (None, ORIENTACOES):
            async with Client(create_server(published, orientacoes=orientacoes)) as client:
                answers.append([(await client.call_tool(*call)).structured_content for call in calls])
        return answers

    before, after = asyncio.run(run())
    assert before == after and before[0]["total_encontrado"] == 1 and before[1]["total_encontrado"] == 1
