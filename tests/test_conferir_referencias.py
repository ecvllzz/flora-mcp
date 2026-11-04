"""conferir_referencias: a list of references in, one proven state out for each, never 'inexistente'."""

import asyncio

import pytest
from mcp.client.client import Client

from conftest import ingest, raw_doc
from flora_mcp import api, conferencia
from flora_mcp.model import FloraError
from flora_mcp.precedents import import_package, migrate
from flora_mcp.publication import publish
from flora_mcp.server import create_server
from test_precedents import packet


@pytest.fixture
def loaded(store, tmp_path):
    ingest(
        store,
        [
            raw_doc(
                "1",
                numeroProcesso="1779343",
                siglaClasse="AgInt no AREsp",
                ministroRelator="MINISTRO EXEMPLO",
            ),
            raw_doc("2", numeroProcesso="1497831", siglaClasse="REsp", dataDecisao="20260110", text="Juros."),
            raw_doc(
                "3", numeroProcesso="1497831", siglaClasse="REsp", dataDecisao="20260220", text="Embargos."
            ),
        ],
    )
    migrate(store)
    import_package(store, packet(tmp_path, species="tema_repetitivo", number="908"), apply=True)
    publish(store)
    return store


@pytest.mark.parametrize(
    "number,valid",
    [
        ("5002677-98.2022.8.24.0034", True),
        ("5002677-97.2022.8.24.0034", False),
        ("00135062220238160000", True),
    ],
)
def test_cnj_check_digit_follows_resolution_65(number, valid):
    assert conferencia.cnj_valid("".join(c for c in number if c.isdigit())) is valid


def test_each_reference_gets_one_state_and_the_fields_compared(loaded):
    answer = api.check_references(
        loaded,
        [
            "STJ, AgInt no AREsp 1.779.343/DF, rel. Ministro Exemplo, Terceira Turma, j. 24/08/2026",
            "AgInt no AREsp 1.779.343/DF, rel. Min. Outro Nome, Quarta Turma, j. 01/01/2020",
            "REsp 1.497.831/PR",
            "REsp 1.497.831/PR, j. 20/02/2026",
            "REsp 9.999.999/SP",
            "5002677-97.2022.8.24.0034",
            "5002677-98.2022.8.24.0034",
            "TJPR, 0013506-22.2023.8.16.0000",
            "Tema 908",
            "Súmula 7 do STJ",
            "sem número algum",
        ],
    )
    items = {i["referencia"]: i for i in answer["referencias"]}
    first = items["STJ, AgInt no AREsp 1.779.343/DF, rel. Ministro Exemplo, Terceira Turma, j. 24/08/2026"]
    assert first["estado"] == "localizado" and first["chave"] == "STJ:AGINT NO ARESP:1779343"
    assert first["acordaos"][0]["campos"] == {"data": "confere", "relator": "confere", "orgao": "confere"}
    assert first["conferir"] == [] and first["acordaos"][0]["id"] == "STJ:1"
    second = items["AgInt no AREsp 1.779.343/DF, rel. Min. Outro Nome, Quarta Turma, j. 01/01/2020"]
    assert second["estado"] == "localizado" and second["conferir"] == ["data", "orgao", "relator"]
    several = items["REsp 1.497.831/PR"]
    assert several["estado"] == "localizado" and [a["id"] for a in several["acordaos"]] == ["STJ:3", "STJ:2"]
    assert several["conferir"] == ["processo_com_varios_acordaos"] and "acordao_correspondente" not in several
    dated = items["REsp 1.497.831/PR, j. 20/02/2026"]
    assert dated["acordao_correspondente"] == "STJ:3" and dated["conferir"] == [
        "processo_com_varios_acordaos"
    ]
    assert items["REsp 9.999.999/SP"]["estado"] == "nao_localizado"
    assert items["5002677-97.2022.8.24.0034"]["estado"] == "numero_invalido"
    cnj = items["5002677-98.2022.8.24.0034"]
    assert cnj["estado"] == "nao_localizado" and cnj["chave"] == "50026779820228240034"
    assert items["TJPR, 0013506-22.2023.8.16.0000"]["motivo"] == "tribunal não coletado"
    theme = items["Tema 908"]
    assert theme["estado"] == "localizado" and theme["precedente"]["id"] == "STJ:tema_repetitivo:908"
    assert (
        theme["precedente"]["situacao"] == "vigente"
        and "tese_firmada" in theme["precedente"]["componentes_disponiveis"]
    )
    assert items["Súmula 7 do STJ"]["estado"] == "nao_localizado"
    assert items["sem número algum"]["estado"] == "nao_reconhecida"
    assert answer["resumo"] == {
        "numero_invalido": 1,
        "localizado": 5,
        "nao_localizado": 4,
        "inexistente_na_fonte": 0,
        "nao_reconhecida": 1,
    }
    assert any("não é inexistente" in a for a in answer["avisos"])
    assert answer["contrato"] == "flora-mcp-3.6" and answer["publicacao_id"]
    assert "inexistente" not in " ".join(i["estado"] for i in answer["referencias"])


def test_refuses_text_of_a_brief_and_empty_or_long_lists(loaded):
    with pytest.raises(FloraError, match="peça"):
        api.check_references(loaded, ["x" * 201])
    with pytest.raises(FloraError, match="1 a 50"):
        api.check_references(loaded, [])
    with pytest.raises(FloraError, match="1 a 50"):
        api.check_references(loaded, ["Tema 908"] * 51)


def test_works_over_the_work_database_too(store):
    ingest(store, [raw_doc("1", numeroProcesso="1779343", siglaClasse="AgInt no AREsp")])
    answer = api.check_references(store, ["AgInt no AREsp 1779343", "Tema 908"])
    assert [i["estado"] for i in answer["referencias"]] == ["localizado", "nao_localizado"]
    assert "publicacao_id" not in answer


def test_tool_is_read_only_and_refuses_long_items_by_schema(loaded):
    async def run():
        async with Client(create_server(loaded)) as client:
            ok = await client.call_tool("conferir_referencias", {"referencias": ["Tema 908", "x"]})
            long = await client.call_tool("conferir_referencias", {"referencias": ["y" * 300]})
            return ok, long

    ok, long = asyncio.run(run())
    tool = {t.name: t for t in asyncio.run(create_server(loaded).list_tools())}["conferir_referencias"]
    assert tool.annotations.read_only_hint and "peça" in tool.description
    assert [i["estado"] for i in ok.structured_content["referencias"]] == ["localizado", "nao_reconhecida"]
    assert long.is_error and long.structured_content["codigo"] == "parametro_invalido"
