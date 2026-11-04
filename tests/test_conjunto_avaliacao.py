"""O conjunto de avaliação fica no repositório público: sem traço de caso e com o tamanho declarado."""

import json
from pathlib import Path

import pytest

from flora_mcp.text import advanced_query

AVALIACAO = Path(__file__).resolve().parents[1] / "avaliacao"
PROIBIDOS = ('"caso"', '"origem"', '"registros"', "Controle/pesquisa-")


@pytest.fixture(scope="module")
def conjunto():
    return json.loads((AVALIACAO / "conjunto-m1.json").read_text(encoding="utf-8"))


def test_tamanho_declarado(conjunto):
    perguntas = conjunto["perguntas"]
    assert len(perguntas) == 80
    assert sum(p["bloco"] == "r3" for p in perguntas) == 54
    so_stj = [p for p in perguntas if all(e.startswith("STJ:") for e in p["esperados"])]
    assert len(so_stj) == conjunto["stj"]["perguntas_so_do_stj"] == 30
    assert len({p["id"] for p in perguntas}) == len(perguntas)


def test_pergunta_sem_campo_de_caso(conjunto):
    permitidos = {
        "id",
        "bloco",
        "proposicao",
        "assessor",
        "curta",
        "avancada",
        "hipotetica",
        "esperados",
        "graus",
    }
    for pergunta in conjunto["perguntas"]:
        assert set(pergunta) <= permitidos, pergunta["id"]
        assert pergunta["esperados"] == sorted(i for i, g in pergunta["graus"].items() if g > 0), pergunta[
            "id"
        ]


def test_consultas_avancadas_compilam(conjunto):
    for pergunta in conjunto["perguntas"]:
        assert advanced_query(pergunta["avancada"]), pergunta["id"]


@pytest.mark.parametrize(
    "arquivo", sorted(f for f in AVALIACAO.rglob("*") if f.suffix == ".json"), ids=lambda f: f.name
)
def test_arquivos_sem_marca_de_caso(arquivo):
    texto = arquivo.read_text(encoding="utf-8")
    assert not [marca for marca in PROIBIDOS if marca in texto]
