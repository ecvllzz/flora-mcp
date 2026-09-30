"""Ramos de erro e de pendência de prepare e import_package.

A primeira falha é a que o usuário vê: cada caso fixa código e mensagem exatos.
"""

import json

import pytest

from flora_mcp.model import FloraError, canonical, digest
from flora_mcp.precedents import import_package, migrate, prepare

RAW = "FONTE SINTÉTICA DE TESTE, NÃO É PRECEDENTE REAL."
SHA = digest(RAW.encode())
OTHER_SHA = "0" * 64


def record(species="sumula", tribunal="STJ"):
    component = "enunciado" if species in {"sumula", "sumula_vinculante"} else "tese_firmada"
    evidence = {
        k: {"fonte_sha256": SHA, "trecho": RAW, "localizador": "fixture integral"}
        for k in ("situacao", "publicacao", "materia", "componente:" + component, "vinculo", "ementa")
    }
    return {
        "tribunal": tribunal,
        "especie": species,
        "numero": "999999",
        "orgao": "Grupo de Câmaras de Direito Civil" if tribunal == "TJSC" else "Órgão de teste",
        "data_publicacao": "2026-09-01",
        "materia": "civil",
        "situacao": "vigente",
        "tipo_publicacao": "enunciado" if component == "enunciado" else "acordao_merito",
        "pendencias": [],
        "componentes": {component: "Texto sintético."},
        "fontes": [
            {
                "url": f"https://www.{tribunal.lower()}.jus.br/fixture",
                "sha256": SHA,
                "arquivo": "fonte.txt",
                "coletado_em": "2026-09-29T12:00:00-03:00",
            }
        ],
        "evidencias": evidence,
        "conferencia": {"evidencias_conferidas": True, "responsavel": "teste", "data": "2026-09-29"},
        "julgados_relacionados": [
            {
                "id": "STJ:1",
                "referencia": "REsp 1",
                "evidencia_vinculo": "vinculo",
                "ementa": "Ementa sintética.",
                "evidencia_ementa": "ementa",
            }
        ],
    }


@pytest.fixture
def root(tmp_path):
    (tmp_path / "fonte.txt").write_text(RAW, encoding="utf-8")
    return tmp_path


def setter(path, value):
    def change(data):
        *parents, last = path
        for key in parents:
            data = data[key]
        data[last] = value

    return change


def dropper(path):
    def change(data):
        *parents, last = path
        for key in parents:
            data = data[key]
        del data[last]

    return change


def replace(value):
    return lambda data: value


INVALID = "pacote_invalido"
CASES = [
    ("nao_objeto", replace(["lista"]), INVALID, "Registro deve ser um objeto."),
    ("tribunal", setter(["tribunal"], "TRF4"), INVALID, "Tribunal ou espécie fora do contrato."),
    ("especie", setter(["especie"], "iac_x"), INVALID, "Tribunal ou espécie fora do contrato."),
    ("numero_ausente", dropper(["numero"]), INVALID, "Campo textual obrigatório: numero."),
    ("numero_zero", setter(["numero"], "0123"), INVALID, "Número deve ser inteiro positivo, em texto."),
    ("orgao_vazio", setter(["orgao"], "  "), INVALID, "Campo textual obrigatório: orgao."),
    (
        "componentes_lista",
        setter(["componentes"], ["x"]),
        INVALID,
        "Componentes inválidos; ementas pertencem aos julgados associados.",
    ),
    (
        "componente_ementa",
        setter(["componentes", "ementa"], "x"),
        INVALID,
        "Componentes inválidos; ementas pertencem aos julgados associados.",
    ),
    (
        "componente_vazio",
        setter(["componentes", "enunciado"], ""),
        INVALID,
        "Campo textual obrigatório: enunciado.",
    ),
    (
        "sumula_com_tese",
        setter(["componentes", "tese_firmada"], "x"),
        INVALID,
        "Texto de súmula deve usar enunciado.",
    ),
    ("fontes_vazias", setter(["fontes"], []), INVALID, "Fontes oficiais preservadas são obrigatórias."),
    ("fontes_objeto", setter(["fontes"], {"a": 1}), INVALID, "Fontes oficiais preservadas são obrigatórias."),
    (
        "fonte_nao_objeto",
        setter(["fontes"], ["https://www.stj.jus.br"]),
        "fonte_invalida",
        "Fonte deve pertencer ao tribunal do registro e usar HTTPS.",
    ),
    (
        "fonte_http",
        setter(["fontes", 0, "url"], "http://www.stj.jus.br/x"),
        "fonte_invalida",
        "Fonte deve pertencer ao tribunal do registro e usar HTTPS.",
    ),
    (
        "fonte_outro_tribunal",
        setter(["fontes", 0, "url"], "https://www.stf.jus.br/x"),
        "fonte_invalida",
        "Fonte deve pertencer ao tribunal do registro e usar HTTPS.",
    ),
    (
        "fonte_dominio_parecido",
        setter(["fontes", 0, "url"], "https://falsostj.jus.br/x"),
        "fonte_invalida",
        "Fonte deve pertencer ao tribunal do registro e usar HTTPS.",
    ),
    ("hash_maiusculo", setter(["fontes", 0, "sha256"], SHA.upper()), INVALID, "Hash de fonte inválido."),
    ("hash_ausente", dropper(["fontes", 0, "sha256"]), INVALID, "Hash de fonte inválido."),
    ("arquivo_ausente", dropper(["fontes", 0, "arquivo"]), INVALID, "Campo textual obrigatório: arquivo."),
    (
        "hash_divergente",
        setter(["fontes", 0, "sha256"], OTHER_SHA),
        "arquivo_corrompido",
        "Original diverge do hash declarado.",
    ),
    ("coleta_ausente", dropper(["fontes", 0, "coletado_em"]), INVALID, "Coleta exige data/hora com fuso."),
    (
        "coleta_sem_fuso",
        setter(["fontes", 0, "coletado_em"], "2026-09-29T12:00:00"),
        INVALID,
        "Coleta exige data/hora com fuso.",
    ),
    (
        "coleta_texto",
        setter(["fontes", 0, "coletado_em"], "ontem"),
        INVALID,
        "Coleta exige data/hora com fuso.",
    ),
    ("coleta_numero", setter(["fontes", 0, "coletado_em"], 5), INVALID, "Coleta exige data/hora com fuso."),
    ("evidencias_lista", setter(["evidencias"], []), INVALID, "Evidências devem ser um objeto."),
    (
        "evidencia_nao_objeto",
        setter(["evidencias", "situacao"], "x"),
        INVALID,
        "Evidência situacao sem fonte preservada.",
    ),
    (
        "evidencia_outra_fonte",
        setter(["evidencias", "materia", "fonte_sha256"], OTHER_SHA),
        INVALID,
        "Evidência materia sem fonte preservada.",
    ),
    (
        "evidencia_sem_trecho",
        dropper(["evidencias", "situacao", "trecho"]),
        INVALID,
        "Campo textual obrigatório: evidencias.situacao.trecho.",
    ),
    (
        "evidencia_sem_localizador",
        setter(["evidencias", "situacao", "localizador"], ""),
        INVALID,
        "Campo textual obrigatório: evidencias.situacao.localizador.",
    ),
    ("situacao_ausente", dropper(["situacao"]), INVALID, "Situação desconhecida no contrato."),
    ("situacao_estranha", setter(["situacao"], "ativo"), INVALID, "Situação desconhecida no contrato."),
    ("publicacao_curta", setter(["data_publicacao"], "2026-9-1"), INVALID, "Publicação exige AAAA-MM-DD."),
    ("publicacao_basica", setter(["data_publicacao"], "20260901"), INVALID, "Publicação exige AAAA-MM-DD."),
    (
        "publicacao_invalida",
        setter(["data_publicacao"], "2026-02-30"),
        INVALID,
        "Publicação exige AAAA-MM-DD.",
    ),
    ("publicacao_numero", setter(["data_publicacao"], 20260901), INVALID, "Publicação exige AAAA-MM-DD."),
    ("pendencias_texto", setter(["pendencias"], "x"), INVALID, "Pendências devem ser uma lista textual."),
    (
        "pendencias_numero",
        setter(["pendencias"], ["x", 1]),
        INVALID,
        "Pendências devem ser uma lista textual.",
    ),
    (
        "conferencia_sem_responsavel",
        dropper(["conferencia", "responsavel"]),
        INVALID,
        "Campo textual obrigatório: conferencia.responsavel.",
    ),
    (
        "conferencia_sem_data",
        setter(["conferencia", "data"], ""),
        INVALID,
        "Campo textual obrigatório: conferencia.data.",
    ),
    (
        "julgados_objeto",
        setter(["julgados_relacionados"], {}),
        INVALID,
        "Julgados relacionados devem ser lista.",
    ),
    (
        "julgado_texto",
        setter(["julgados_relacionados", 0], "STJ:1"),
        INVALID,
        "Vínculo de julgado exige evidência própria.",
    ),
    (
        "julgado_sem_evidencia",
        setter(["julgados_relacionados", 0, "evidencia_vinculo"], "inexistente"),
        INVALID,
        "Vínculo de julgado exige evidência própria.",
    ),
    (
        "julgado_sem_id",
        dropper(["julgados_relacionados", 0, "id"]),
        INVALID,
        "Campo textual obrigatório: julgado.id.",
    ),
    (
        "julgado_sem_referencia",
        setter(["julgados_relacionados", 0, "referencia"], " "),
        INVALID,
        "Campo textual obrigatório: julgado.referencia.",
    ),
    (
        "julgado_ementa_vazia",
        setter(["julgados_relacionados", 0, "ementa"], ""),
        INVALID,
        "Campo textual obrigatório: julgado.ementa.",
    ),
    (
        "julgado_ementa_sem_evidencia",
        dropper(["julgados_relacionados", 0, "evidencia_ementa"]),
        INVALID,
        "Ementa vinculada exige evidência própria.",
    ),
]


def apply_change(change):
    data = record()
    result = change(data)
    return data if result is None else result


@pytest.mark.parametrize("change,code,message", [c[1:] for c in CASES], ids=[c[0] for c in CASES])
def test_prepare_rejects_with_exact_code_and_message(root, change, code, message):
    data = apply_change(change)
    with pytest.raises(FloraError) as error:
        prepare(data, root)
    assert (error.value.code, str(error.value)) == (code, message)


def test_prepare_rejects_source_outside_package(root):
    outside = root.parent / (root.name + "-fora.txt")
    outside.write_text(RAW, encoding="utf-8")
    data = record()
    data["fontes"][0]["arquivo"] = "../" + outside.name
    with pytest.raises(FloraError) as error:
        prepare(data, root)
    assert (error.value.code, str(error.value)) == (INVALID, "Original fora do pacote.")


def test_prepare_tema_rejects_enunciado(root):
    data = record("tema_repetitivo")
    data["componentes"]["enunciado"] = "x"
    with pytest.raises(FloraError, match="^Tema usa questão submetida e tese firmada.$"):
        prepare(data, root)


def test_prepare_tjsc_scope_and_organ(root):
    body, _ = prepare(record(tribunal="TJSC"), root)
    assert body["id"] == "TJSC:sumula:GCDC:999999"
    data = record(tribunal="TJSC")
    data["orgao"] = "Primeira Câmara de Direito Civil"
    with pytest.raises(FloraError) as error:
        prepare(data, root)
    assert (error.value.code, str(error.value)) == (INVALID, "Órgão TJSC fora do recorte aprovado.")


@pytest.mark.parametrize(
    "first,second,message",
    [
        (setter(["numero"], "x"), setter(["orgao"], ""), "Número deve ser inteiro positivo, em texto."),
        (setter(["componentes"], []), setter(["fontes"], []), "Componentes inválidos"),
        (setter(["fontes"], []), setter(["evidencias"], []), "Fontes oficiais"),
        (setter(["fontes", 0, "sha256"], "x"), setter(["fontes", 0, "url"], "ftp://x"), "Fonte deve"),
        (setter(["evidencias"], []), setter(["situacao"], "x"), "Evidências devem"),
        (setter(["situacao"], "x"), setter(["data_publicacao"], "x"), "Situação desconhecida"),
        (setter(["data_publicacao"], "x"), setter(["pendencias"], "x"), "Publicação exige"),
        (setter(["pendencias"], "x"), setter(["julgados_relacionados"], {}), "Pendências devem"),
        (
            setter(["conferencia", "data"], ""),
            setter(["julgados_relacionados"], {}),
            "Campo textual obrigatório: conferencia.data.",
        ),
    ],
)
def test_prepare_reports_first_failure_in_fixed_order(root, first, second, message):
    data = record()
    first(data)
    second(data)
    with pytest.raises(FloraError, match="^" + message):
        prepare(data, root)


def test_prepare_admitted_body_and_reference(root):
    cache = {}
    body, blobs = prepare(record(), root, cache)
    assert blobs == {SHA: RAW.encode()}
    assert list(cache.values()) == [RAW.encode()]
    assert body["id"] == "STJ:sumula:999999"
    assert (body["admissao"], body["motivos_admissao"]) == ("admitido", [])
    assert body["referencia"] == (
        "STJ, Súmula n. 999999, Órgão de teste, publicação do enunciado 01/09/2026. "
        "Fonte: https://www.stj.jus.br/fixture"
    )
    assert (body["referencia_completa"], body["referencia_pendencias"]) == (True, [])


def test_prepare_pending_reasons_accumulate(root):
    data = record("tema_repetitivo")
    del data["data_publicacao"], data["tipo_publicacao"], data["evidencias"]["materia"]
    data.pop("julgados_relacionados")
    data["materia"] = "penal"
    data["pendencias"] = ["recurso_pendente", "recurso_pendente"]
    data["componentes"] = {"questao_submetida": "Questão sintética."}
    data["conferencia"] = {"evidencias_conferidas": "sim"}
    body, _ = prepare(data, root)
    assert body["admissao"] == "pendente"
    assert body["motivos_admissao"] == [
        "conferencia_pendente",
        "evidencia_ausente:componente:questao_submetida",
        "evidencia_ausente:materia",
        "materia_nao_confirmada",
        "publicacao_ausente",
        "recurso_pendente",
        "tese_firmada_ausente",
        "tipo_publicacao_nao_informado",
    ]
    assert body["tipo_publicacao"] is None
    assert (
        body["referencia"]
        == "STJ, Tema repetitivo n. 999999, Órgão de teste. Fonte: https://www.stj.jus.br/fixture"
    )
    assert (body["referencia_completa"], body["referencia_pendencias"]) == (False, ["data_publicacao"])


def test_prepare_unknown_publication_type_and_exclusion(root):
    data = record()
    data["situacao"] = "revogado"
    data["tipo_publicacao"] = "diario"
    data["conferencia"] = "feita"
    body, _ = prepare(data, root)
    assert body["admissao"] == "excluido"
    assert body["motivos_admissao"] == [
        "conferencia_pendente",
        "situacao_revogado",
        "tipo_publicacao_nao_informado",
    ]
    assert "publicação de natureza não identificada 01/09/2026" in body["referencia"]


def write_package(root, value):
    path = root / "pacote.json"
    path.write_text(canonical(value), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "package,code,message",
    [
        ([], INVALID, "Esperado pacote flora-precedentes-1."),
        ({"schema": "flora-precedentes-2", "registros": []}, INVALID, "Esperado pacote flora-precedentes-1."),
        ({"schema": "flora-precedentes-1"}, INVALID, "Pacote deve conter registros."),
        ({"schema": "flora-precedentes-1", "registros": []}, INVALID, "Pacote deve conter registros."),
        ({"schema": "flora-precedentes-1", "registros": {"a": 1}}, INVALID, "Pacote deve conter registros."),
        ({"schema": "flora-precedentes-1", "registros": [record(), record()]}, "id_duplicado", None),
        (
            {"schema": "flora-precedentes-1", "registros": [record(), 1]},
            INVALID,
            "Registro deve ser um objeto.",
        ),
    ],
)
def test_import_package_rejects(store, root, package, code, message):
    with pytest.raises(FloraError) as error:
        import_package(store, write_package(root, package))
    assert error.value.code == code
    assert str(error.value) == (message or "Pacote contém identidade duplicada.")


def test_import_package_accepts_bom_and_requires_migration(store, root):
    path = root / "pacote.json"
    package = {"schema": "flora-precedentes-1", "registros": [record()]}
    path.write_bytes(b"\xef\xbb\xbf" + canonical(package).encode())
    receipt = import_package(store, path)
    assert receipt == {
        "status": "ok",
        "aplicado": False,
        "registros": [{"id": "STJ:sumula:999999", "admissao": "admitido", "motivos": []}],
    }
    with pytest.raises(FloraError) as error:
        import_package(store, path, apply=True)
    assert (error.value.code, str(error.value)) == (
        "migracao_pendente",
        "Execute a migração administrativa antes de importar.",
    )


def test_import_package_refuses_retired_version_and_retires_changed_components(store, root):
    from flora_mcp.store import connection

    migrate(store)
    admitted = {"schema": "flora-precedentes-1", "registros": [record()]}
    path = write_package(root, admitted)
    assert import_package(store, path, apply=True)["alterado"] is True
    changed = json.loads(canonical(admitted))
    changed["registros"][0]["componentes"]["enunciado"] = "Texto sintético revisto."
    receipt = import_package(store, write_package(root, changed), apply=True)
    assert receipt["alterado"] is True and "estado_anterior_conservado" not in receipt["registros"][0]
    with connection(store.path) as db:
        assert db.execute("SELECT count(*) FROM precedent_retirements").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM precedent_texts").fetchone()[0] == 1
    with pytest.raises(FloraError) as error:
        import_package(store, write_package(root, admitted), apply=True)
    assert (error.value.code, str(error.value)) == (
        "versao_retirada",
        "Readmissão exige nova evidência; este conteúdo foi retirado.",
    )
