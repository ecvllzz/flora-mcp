"""Adaptadores de fontes estruturadas, mapeamentos, política de admissão por amostra e comando.

As fixtures em tests/fixtures/precedentes são recortes literais (bytes copiados) dos originais
oficiais coletados em 29/09/2026; nenhum teste usa rede.
"""

import csv
import io
import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from flora_mcp import cli
from flora_mcp.model import FloraError, canonical, digest
from flora_mcp.precedent_sources import OUT_OF_SCOPE, stf_sumulas, stj_sumulas, stj_temas, structured_url
from flora_mcp.precedent_sources.common import Original, branch_matter
from flora_mcp.precedent_sources.pacote import prepare_package, sample_skeleton
from flora_mcp.precedents import draw, import_package, migrate, minimum_sample

FIXTURES = Path(__file__).parent / "fixtures" / "precedentes"
COLLECTED = "2026-09-29T20:22:29.995945+00:00"
DATASET = "https://dadosabertos.web.stj.jus.br/dataset/4238da2f-c07b-4c1a-b345-4402accacdcf/resource/"
TEMAS = DATASET + "df29da13-7d6b-41ba-ad96-cd1a5bbd191c/download/temas.csv"
PROCESSOS = DATASET + "7ed21202-0049-4fcb-aa7c-48d810d3c499/download/processos.csv"
SCON = "https://processo.stj.jus.br/SCON/sumstj/toc.jsp?tipo=sumula+ou+su&b=SUMU&i=1&l=100&ordenacao=-@NUM"
LATIN1 = "text/html;charset=ISO-8859-1"
STF = "https://portal.stf.jus.br/jurisprudencia/sumariosumulas.asp?base="
ORIGINALS = {
    "stj_temas": [("temas.csv", TEMAS, "text/csv"), ("processos.csv", PROCESSOS, "text/csv")],
    "stj_sumulas": [("scon-sumulas.html", SCON, LATIN1)],
    "stf_sumulas": [
        ("stf-indice-sumulas.html", STF + "30", None),
        ("stf-indice-vinculantes.html", STF + "26", None),
        ("stf-sumula-380.html", STF + "30&sumula=2482", "text/html"),
        ("stf-sumula-619.html", STF + "30&sumula=1523", "text/html"),
        ("stf-sumula-257.html", STF + "30&sumula=4159", "text/html"),
        ("stf-sv-25.html", STF + "26&sumula=1268", "text/html"),
    ],
}


def original(name, url, content_type=None):
    content = (FIXTURES / name).read_bytes()
    return Original("originais/" + name, content, url, COLLECTED, digest(content), content_type)


def adapted(source):
    module = {"stj_temas": stj_temas, "stj_sumulas": stj_sumulas, "stf_sumulas": stf_sumulas}[source]
    result = module.adapt([original(*item) for item in ORIGINALS[source]])
    return result, {(body["especie"], body["numero"]): body for body in result.registros}


def collected_folder(tmp_path, source):
    """Originals with receipts, in the layout of a collection folder."""
    folder = tmp_path / "brutos"
    folder.mkdir(exist_ok=True)
    for name, url, content_type in ORIGINALS[source]:
        content = (FIXTURES / name).read_bytes()
        (folder / (name + ".raw")).write_bytes(content)
        receipt = {
            "url_solicitada": url,
            "obtido_em": COLLECTED,
            "status": "obtido",
            "sha256": digest(content),
        }
        receipt |= {"arquivo": "brutos\\" + name + ".raw", "content_type": content_type}
        (folder / (name + ".recibo.json")).write_text(json.dumps(receipt), encoding="utf-8")
    return folder


# Adaptadores sobre os recortes reais


def test_stj_temas_fields_evidence_and_leading_case():
    result, records = adapted("stj_temas")
    iac = records["iac", "2"]
    assert (iac["orgao"], iac["materia"], iac["situacao"], iac["pendencias"]) == (
        "S2",
        "civil",
        "vigente",
        [],
    )
    assert (iac["data_publicacao"], iac["tipo_publicacao"]) == ("2021-12-16", "acordao_merito")
    assert iac["componentes"]["questao_submetida"].startswith("Prazo anual de prescrição")
    assert iac["evidencias"]["situacao"] == {
        "fonte_sha256": digest((FIXTURES / "temas.csv").read_bytes()),
        "trecho": "Trânsito em Julgado",
        "localizador": "originais/temas.csv, CSV linha lógica 3 (cabeçalho = 1), "
        "sequencialPrecedente=1650, coluna situacao",
    }
    assert iac["evidencias"]["componente:tese_firmada"]["trecho"] == iac["componentes"]["tese_firmada"]
    assert iac["julgados_relacionados"] == [
        {
            "id": "STJ:registro:201200075421:2021-11-30",
            "referencia": "STJ, REsp 1303374, rel. LUIS FELIPE SALOMÃO, S2, j. 30/11/2021, publ. 16/12/2021",
            "evidencia_vinculo": "vinculo:201200075421",
        }
    ]
    assert [s["classe"] for s in iac["fontes"]] == ["estruturada", "estruturada"]
    assert {i["motivo"] for i in result.ignorados} == {"tipo_fora_do_contrato:Controvérsia", "linha_repetida"}


def source_text(name, content_type):
    """Cell values of a CSV (quotes undone) or the text of an HTML page (tags removed)."""
    item = original(name, "", content_type)
    if name.endswith(".csv"):
        reader = csv.reader(io.StringIO(item.content.decode("utf-8-sig"), newline=""))
        return "\n".join(cell for row in reader for cell in row)
    return BeautifulSoup(item.text(), "html.parser").get_text()


@pytest.mark.parametrize("source", sorted(ORIGINALS))
def test_every_required_excerpt_is_text_of_the_cited_source(source):
    """Each excerpt is in the source it cites (tags removed); components are their own excerpts."""
    result, _ = adapted(source)
    texts = {digest((FIXTURES / n).read_bytes()): (n, source_text(n, t)) for n, _, t in ORIGINALS[source]}
    for body in result.registros:
        for key, item in body["evidencias"].items():
            name, text = texts[item["fonte_sha256"]]
            assert item["localizador"].startswith("originais/" + name), key
            if not key.startswith("vinculo:"):
                assert " ".join(item["trecho"].split()) in " ".join(text.split()), (body["numero"], key)
        for name, value in body["componentes"].items():
            assert body["evidencias"]["componente:" + name]["trecho"] == value


def test_stj_sumulas_statement_reference_and_markers():
    result, records = adapted("stj_sumulas")
    summary = records["sumula", "385"]
    assert summary["componentes"]["enunciado"].startswith("Da anotação irregular em cadastro")
    assert summary["componentes"]["enunciado"].endswith("ressalvado o direito ao cancelamento.")
    assert (summary["orgao"], summary["data_publicacao"], summary["materia"]) == (
        "SEGUNDA SEÇÃO",
        "2009-06-08",
        "civil",
    )
    assert summary["evidencias"]["publicacao"]["trecho"].endswith("DJe 08/06/2009)")
    assert summary["evidencias"]["situacao"]["trecho"] == "Súmula 385"
    assert records["sumula", "603"]["situacao"] == "cancelado"
    assert records["sumula", "476"]["materia"] == "civil"  # direito empresarial
    assert records["sumula", "676"]["materia"] == OUT_OF_SCOPE  # processual penal, sem span.clsVerbete
    old = records["sumula", "106"]  # "DJ 03/06/1994, p. 13885" e órgão quebrado em duas linhas
    assert (old["orgao"], old["data_publicacao"], old["materia"]) == (
        "CORTE ESPECIAL",
        "1994-06-03",
        "processual_civil",
    )
    assert {i["referencia"]: i["motivo"] for i in result.ignorados} == {
        "originais/scon-sumulas.html, Súmula 545": "verbete_fora_do_padrao",
        "originais/scon-sumulas.html, Súmula 212": "verbete_fora_do_padrao",
    }


def test_stf_sumulas_index_status_and_page_statement():
    result, records = adapted("stf_sumulas")
    assert result.ignorados == []
    summary = records["sumula", "380"]
    assert summary["componentes"]["enunciado"] == (
        "Comprovada a existência de sociedade de fato entre os concubinos, é cabível a sua dissolução "
        "judicial, com a partilha do patrimônio adquirido pelo esforço comum."
    )
    assert (summary["situacao"], summary["data_publicacao"], summary["materia"]) == (
        "vigente",
        "1964-05-12",
        None,
    )
    assert summary["evidencias"]["publicacao"]["trecho"] == "Data de publicação do enunciado: DJ de 12-5-1964"
    assert [s["url"] for s in summary["fontes"]] == [STF + "30&sumula=2482", STF + "30"]
    assert records["sumula", "619"]["situacao"] == "revogado"
    assert records["sumula", "257"]["data_publicacao"] is None  # só data de aprovação
    binding = records["sumula_vinculante", "25"]
    assert (binding["data_publicacao"], binding["evidencias"]["situacao"]["trecho"]) == (
        "2009-12-23",
        "Súmula Vinculante 25",
    )


# Mapeamentos


@pytest.mark.parametrize(
    "value,expected",
    [
        ("Trânsito em Julgado", ("vigente", None)),
        ("Acórdão Publicado", ("vigente", None)),
        ("Acórdão Publicado - RE Pendente", ("vigente", "recurso_extraordinario_pendente")),
        ("Afetado", ("pendente", None)),
        ("Sobrestado", ("pendente", None)),
        ("Em Julgamento", ("pendente", None)),
        ("Cancelado", ("cancelado", None)),
        ("Revisado", ("superado", None)),
    ],
)
def test_stj_situation_table(value, expected):
    assert stj_temas.SITUACOES[value] == expected


def test_unmapped_situation_is_unknown_and_pending():
    _, records = adapted("stj_temas")
    assert records["tema_repetitivo", "1320"]["situacao"] == "desconhecido"  # "Sem Processo Vinculado"
    assert records["tema_repetitivo", "978"]["situacao"] == "pendente"
    assert records["tema_repetitivo", "369"]["pendencias"] == ["recurso_extraordinario_pendente"]
    assert records["tema_repetitivo", "126"]["situacao"] == "superado"


@pytest.mark.parametrize(
    "branches,expected",
    [
        ([], None),
        (["899- DIREITO CIVIL"], "civil"),
        (["1156- DIREITO DO CONSUMIDOR"], "civil"),
        (["8826- DIREITO PROCESSUAL CIVIL E DO TRABALHO"], "processual_civil"),
        (["899- DIREITO CIVIL", "8826- DIREITO PROCESSUAL CIVIL E DO TRABALHO"], "civil"),
        (["14- DIREITO TRIBUTÁRIO"], OUT_OF_SCOPE),
        (["8826- DIREITO PROCESSUAL CIVIL E DO TRABALHO", "9985- DIREITO ADMINISTRATIVO"], OUT_OF_SCOPE),
    ],
)
def test_branch_to_matter(branches, expected):
    assert branch_matter(branches, stj_temas.RAMOS) == expected


def test_subject_branches_are_read_from_the_cnj_codes():
    subjects = "9148- Liquidação / Cumprimento / Execução, 8826- DIREITO PROCESSUAL CIVIL E DO TRABALHO"
    assert stj_temas.branches(subjects) == ["8826- DIREITO PROCESSUAL CIVIL E DO TRABALHO"]
    assert stj_temas.branches("10296- Descontos Indevidos, 5632- Prescrição e Decadência") == []


def test_stj_organ_codes_stay_literal_without_a_source_table():
    assert stj_temas.ORGAOS == {}
    _, records = adapted("stj_temas")
    assert {body["orgao"] for body in records.values()} <= {"S1", "S2", "S3", "CE"}


def test_structured_sources_are_only_the_registered_addresses():
    assert structured_url(TEMAS) == "stj_temas"
    assert structured_url(SCON) == "stj_sumulas"
    assert structured_url(STF + "30&sumula=2482") == "stf_sumulas"
    assert (
        structured_url("https://portal.stf.jus.br/jurisprudenciaRepercussao/verAndamentoProcesso.asp") is None
    )
    assert structured_url("https://www.tjsc.jus.br/documents/sumula-67.pdf") is None


# Política de admissão


def prepared(tmp_path, source="stj_temas"):
    package = tmp_path / "pacote" / f"{source}.json"
    prepare_package(source, collected_folder(tmp_path, source), package)
    return package


def fill(package, **changes):
    data = json.loads(package.read_text(encoding="utf-8"))
    sample = data["conferencia"]["amostra"]
    for check in sample["verificacoes"]:
        check["campos_conferidos"] = check["campos_a_conferir"]
        check["resultado"] = "conforme"
    sample |= {"responsavel": "auditor de teste", "data": "2026-09-30", "resultado": "aprovada"}
    for key, value in changes.items():
        sample[key] = value
    package.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def admissions(receipt):
    return {entry["id"]: (entry["admissao"], entry["motivos"]) for entry in receipt["registros"]}


def test_package_without_batch_review_keeps_every_record_pending(store, tmp_path):
    receipt = import_package(store, prepared(tmp_path))
    assert all("conferencia_pendente" in motives for _, motives in admissions(receipt).values())


def test_approved_sample_admits_structured_records_that_pass_every_other_rule(store, tmp_path):
    migrate(store)
    package = prepared(tmp_path)
    sample_skeleton(package, 20260930)
    fill(package)
    receipt = import_package(store, package, apply=True)
    result = admissions(receipt)
    assert result["STJ:iac:2"] == ("admitido", [])
    assert result["STJ:tema_repetitivo:1085"] == ("admitido", [])
    assert result["STJ:tema_repetitivo:1071"] == ("pendente", ["tese_firmada_ausente"])
    assert result["STJ:iac:17"] == ("pendente", ["evidencia_ausente:materia", "materia_nao_confirmada"])
    assert result["STJ:tema_repetitivo:126"] == ("excluido", ["materia_fora_do_recorte", "situacao_superado"])
    assert result["STJ:tema_repetitivo:369"][1] == ["recurso_extraordinario_pendente"]
    assert receipt["conferencia_lote"]["semente"] == 20260930
    found = cli_search(store, "segurado")
    assert [item["id"] for item in found["resultados"]] == ["STJ:iac:2"]
    assert found["resultados"][0]["referencia"] == (
        "STJ, IAC n. 2, S2, publicação do acórdão de mérito 16/12/2021. Fonte: " + TEMAS
    )


def cli_search(store, terms):
    from flora_mcp import api

    return api.search_precedents(store, terms)


@pytest.mark.parametrize(
    "change,message",
    [
        ({"resultado": "reprovada"}, "resultado da amostra não é aprovada."),
        ({"resultado": None}, "resultado da amostra não é aprovada."),
        ({"responsavel": ""}, "responsavel da amostra é obrigatório."),
        ({"semente": 1}, "ids não correspondem ao sorteio da semente."),
    ],
)
def test_sample_problems_refuse_the_whole_batch(store, tmp_path, change, message):
    package = prepared(tmp_path)
    sample_skeleton(package, 20260930)
    fill(package, **change)
    with pytest.raises(FloraError) as error:
        import_package(store, package)
    assert (error.value.code, str(error.value)) == ("amostra_reprovada", "Lote recusado: " + message)


def test_failed_verification_refuses_the_whole_batch(store, tmp_path):
    package = prepared(tmp_path)
    sample_skeleton(package, 20260930)
    data = fill(package)
    data["conferencia"]["amostra"]["verificacoes"][0]["resultado"] = "divergente"
    package.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(FloraError, match="não está conforme") as error:
        import_package(store, package)
    assert error.value.code == "amostra_reprovada"


def test_verification_must_cover_the_required_fields(store, tmp_path):
    package = prepared(tmp_path)
    sample_skeleton(package, 20260930)
    data = fill(package)
    data["conferencia"]["amostra"]["verificacoes"][0]["campos_conferidos"] = ["situacao"]
    package.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(FloraError, match="não cobre os campos obrigatórios"):
        import_package(store, package)


def test_undersized_sample_and_id_outside_the_batch_refuse_the_batch(store, tmp_path):
    package = prepared(tmp_path)
    sample_skeleton(package, 20260930)
    data = fill(package)
    sample = data["conferencia"]["amostra"]
    small = dict(sample, tamanho=sample["tamanho"] - 1, ids=sample["ids"][:-1])
    small["verificacoes"] = sample["verificacoes"][:-1]
    data["conferencia"]["amostra"] = small
    package.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(FloraError, match="ao menos 10 registros sorteados"):
        import_package(store, package)
    data["conferencia"]["amostra"] = dict(sample, ids=["STJ:iac:999"] + sample["ids"][1:])
    package.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(FloraError, match="id sorteado fora do lote"):
        import_package(store, package)


def test_minimum_sample_size_and_reproducible_draw():
    assert [minimum_sample(n) for n in (3, 10, 199, 200, 201, 1496)] == [3, 10, 10, 10, 11, 75]
    ids = [f"STJ:tema_repetitivo:{n}" for n in range(1, 300)]
    assert draw(ids, 7, 15) == draw(list(reversed(ids)), 7, 15)
    assert draw(ids, 7, 15) != draw(ids, 8, 15)


def test_document_source_is_never_admitted_by_the_batch_sample(store, tmp_path):
    """A record of a document source in an approved batch still needs individual review."""
    package = prepared(tmp_path)
    data = json.loads(package.read_text(encoding="utf-8"))
    raw = "Página de tema com andamentos, recorte sintético."
    (package.parent / "pagina.html").write_text(raw, encoding="utf-8")
    sha = digest(raw.encode())
    document = json.loads(canonical(data["registros"][0]))
    document |= {"tribunal": "STF", "especie": "tema_repercussao_geral", "numero": "809", "orgao": "STF"}
    document["fontes"] = [
        {
            "url": "https://portal.stf.jus.br/jurisprudenciaRepercussao/verAndamentoProcesso.asp?numeroTema=809",
            "sha256": sha,
            "arquivo": "pagina.html",
            "coletado_em": COLLECTED,
            "classe": "documento",
        }
    ]
    document["julgados_relacionados"] = []
    document["evidencias"] = {
        key: {"fonte_sha256": sha, "trecho": raw, "localizador": "recorte"}
        for key in (
            "situacao",
            "publicacao",
            "materia",
            "componente:questao_submetida",
            "componente:tese_firmada",
        )
    }
    data["registros"].append(document)
    package.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    sample_skeleton(package, 20260930)
    fill(package)
    result = admissions(import_package(store, package))
    assert result["STF:tema_repercussao_geral:809"] == ("pendente", ["conferencia_pendente"])
    assert result["STJ:iac:2"] == ("admitido", [])


def test_structured_class_requires_a_registered_address(store, tmp_path):
    package = prepared(tmp_path)
    data = json.loads(package.read_text(encoding="utf-8"))
    data["registros"][0]["fontes"][0]["url"] = "https://www.stj.jus.br/outra/fonte.csv"
    package.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(FloraError, match="Classe estruturada exige fonte estruturada registrada") as error:
        import_package(store, package)
    assert error.value.code == "fonte_invalida"


def test_simulation_reports_the_effect_on_the_current_collection(store, tmp_path):
    migrate(store)
    package = prepared(tmp_path)
    sample_skeleton(package, 20260930)
    fill(package)
    import_package(store, package, apply=True)
    effects = {e["id"]: e["efeito"] for e in import_package(store, package)["registros"]}
    assert set(effects.values()) == {"sem_alteracao"}
    # The same records without the batch review: admitted ones are kept, as an incomplete observation.
    data = json.loads(package.read_text(encoding="utf-8"))
    del data["conferencia"]
    package.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    effects = {e["id"]: e["efeito"] for e in import_package(store, package)["registros"]}
    assert effects["STJ:iac:2"] == "estado_anterior_conservado"


# Comando


def run(capsys, *argv):
    cli.main(list(argv))
    return json.loads(capsys.readouterr().out)


def test_command_prepares_package_and_writes_sample_skeleton(tmp_path, capsys):
    folder = collected_folder(tmp_path, "stf_sumulas")
    package = tmp_path / "saida" / "stf.json"
    summary = run(
        capsys,
        "precedentes",
        "preparar",
        "--fonte",
        "stf_sumulas",
        "--originais",
        str(folder),
        "--saida",
        str(package),
    )
    assert (summary["registros"], summary["ignorados"]) == (4, {})
    assert (package.parent / "originais" / "stf-sumula-380.html.raw").is_file()
    drawn = run(capsys, "precedentes", "amostra", str(package), "--semente", "20260930")
    assert drawn["tamanho"] == 4 and sorted(drawn["ids"]) == sorted(
        ["STF:sumula:257", "STF:sumula:380", "STF:sumula:619", "STF:sumula_vinculante:25"]
    )
    review = json.loads(package.read_text(encoding="utf-8"))["conferencia"]
    assert review["modo"] == "fonte_estruturada"
    assert review["amostra"]["ids"] == drawn["ids"]
    assert review["amostra"]["resultado"] is None
    assert review["amostra"]["verificacoes"][0]["campos_conferidos"] == []
    assert run(capsys, "precedentes", "amostra", str(package), "--semente", "20260930")["ids"] == drawn["ids"]


def test_command_refuses_to_overwrite_a_filled_sample(tmp_path, capsys):
    package = prepared(tmp_path)
    sample_skeleton(package, 20260930)
    fill(package)
    with pytest.raises(SystemExit):
        cli.main(["precedentes", "amostra", str(package), "--semente", "1"])
    assert "amostra_existente" in capsys.readouterr().err


def test_package_actions_do_not_capture_searches():
    assert cli.package_action(["precedentes", "preparar", "--fonte", "stj_temas"]) == [
        "preparar",
        "--fonte",
        "stj_temas",
    ]
    assert cli.package_action(["--data-dir", "x", "precedentes", "amostra", "p.json"]) == [
        "amostra",
        "p.json",
    ]
    assert cli.package_action(["precedentes", "--", "preparar"]) is None
    assert cli.package_action(["precedentes", "alimentos"]) is None
