import json
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from flora_mcp.config import Config
from flora_mcp.model import FloraError
from flora_mcp.sources import validate_tjsc_page
from flora_mcp.tjsc import collect_window, parse_page
from flora_mcp.tjsc_orgaos import ESPECIAIS, ORGAOS, PADRAO, chamber, dataset, name, portal_names

# Portal search form read once on 30/09/2026 (receipt beside it); source of the organ names.
FORM = Path(__file__).parent / "fixtures" / "tjsc" / "formulario-pesquisa.html"


def page(ids, total=12, publication="18/09/2026", organ="9ª Câmara de Direito Civil"):
    html = '<meta charset="iso-8859-1"><input id="hdnTotalResultado" value="' + str(total) + '">'
    for id in ids:
        fields = {
            "ÓRGÃO JULGADOR": organ,
            "EMENTA": "Texto público completo.",
            "DATA DA PUBLICAÇÃO": publication,
            "DATA DO JULGAMENTO": "10/09/2026",
            "PROCESSO": f"{5000000 + id}-00.2026.8.24.0000/TJSC AI - Agravo de Instrumento",
        }
        html += f'<div class="resultadoItem" id="resultado{id}">'
        for k, v in fields.items():
            html += f'<span class="resLabel">{k}</span><span class="resValue">{v}</span>'
        html += "</div>"
    return html.encode("latin1")


@pytest.mark.parametrize("scenario", ["ok", "duplicate", "total_drift", "outside_date", "first_page_changes"])
def test_window_commit_requires_all_pages_and_stable_first_page(store, scenario):
    first_calls = 0

    def route(req):
        nonlocal first_calls
        values = parse_qs(req.content.decode())
        requested = int(values["hdnPaginaAtual"][0])
        if requested == 1:
            first_calls += 1
            content = page(range(10))
            if scenario == "first_page_changes" and first_calls == 2:
                content = page(range(1, 11))
        else:
            content = page(
                [0, 11] if scenario == "duplicate" else [10, 11],
                total=13 if scenario == "total_drift" else 12,
                publication="17/09/2026" if scenario == "outside_date" else "18/09/2026",
            )
        return httpx.Response(200, content=content)

    with httpx.Client(transport=httpx.MockTransport(route)) as http:
        config = Config(store.directory, request_delay=0)
        if scenario == "ok":
            content, rows = collect_window(http, config, 9, date(2026, 9, 18))
            assert len(rows) == 12
            assert rows[0][0]["classe"] == "AI"
            assert rows[0][0]["numero_processo"] == "5000000-00.2026.8.24.0000"
            assert b"bytes_base64" in content
            assert first_calls == 2
        else:
            with pytest.raises(FloraError):
                collect_window(http, config, 9, date(2026, 9, 18))


def test_zero_is_distinguished_from_unknown_page():
    content = b'<input id="hdnTotalResultado"><h2>0 documentos encontrados</h2>'
    assert validate_tjsc_page(content, 9)["total_informado"] == 0
    with pytest.raises(FloraError):
        validate_tjsc_page(b'<input id="hdnTotalResultado"><h2>Erro desconhecido</h2>', 9)


def test_copy_control_inside_ementa_label_preserves_document():
    original = page([1], total=1)
    with_control = original.replace(
        b"EMENTA</span>",
        b'EMENTA <a class="copiarCampoResultado" data-label="EMENTA">'
        b'<i class="material-icons">content_copy</i></a></span>',
    )
    expected = parse_page(original, 9, date(2026, 9, 18))
    assert parse_page(with_control, 9, date(2026, 9, 18)) == expected


def test_collector_organs_are_exact_names_of_the_portal_filter():
    names = portal_names(FORM.read_bytes())
    assert set(ORGAOS) <= set(names)
    assert ESPECIAIS == (
        "1ª Câmara Especial de Enfrentamento de Acervos",
        "2ª Câmara Especial de Enfrentamento de Acervos",
        "3ª Câmara Especial de Enfrentamento de Acervos",
    )
    # Homonyms the portal also lists stay out: the collector never guesses among them.
    assert {"1ª Câmara de Enfrentamento de Acervos", "3ª Câmara de Direito Civil (Janeiro)"} <= set(names)
    assert not {"1ª Câmara de Enfrentamento de Acervos", "3ª Câmara de Direito Civil (Janeiro)"} & set(ORGAOS)
    with pytest.raises(FloraError):
        portal_names(b"<html><select name='outro'></select></html>")


def test_numbered_chamber_keeps_its_dataset_and_other_organs_get_a_named_one():
    assert PADRAO == tuple(name(n) for n in range(1, 11))
    assert not set(PADRAO) & set(ESPECIAIS)
    assert (name(9), chamber(9), dataset(9)) == ("9ª Câmara de Direito Civil", 9, "tjsc-9-civil")
    assert dataset("10ª Câmara de Direito Civil") == "tjsc-10-civil"
    assert [dataset(o) for o in ESPECIAIS] == [
        f"tjsc-{n}a-camara-especial-de-enfrentamento-de-acervos" for n in (1, 2, 3)
    ]
    assert chamber(ESPECIAIS[0]) is None
    for invalid in (11, "Câmara Especial", "9a Câmara de Direito Civil"):
        with pytest.raises(FloraError) as info:
            name(invalid)
        assert info.value.code == "orgao_invalido"


def test_named_organ_window_filters_and_checks_by_the_portal_name(store):
    special = ESPECIAIS[1]
    sent = []

    def route(req):
        sent.append(parse_qs(req.content.decode())["selOrgao[]"][0])
        return httpx.Response(200, content=page([1, 2], total=2, organ=special))

    with httpx.Client(transport=httpx.MockTransport(route)) as http:
        content, rows = collect_window(
            http, Config(store.directory, request_delay=0), special, date(2026, 9, 18)
        )
    envelope = json.loads(content)
    assert set(sent) == {special}
    assert (envelope["orgao"], "camara" in envelope, envelope["total"]) == (special, False, 2)
    assert {body["orgao"] for body, _ in rows} == {special}
    civil = json.loads(collect_window_envelope(store, 9))
    assert (civil["orgao"], civil["camara"]) == ("9ª Câmara de Direito Civil", 9)
    with pytest.raises(FloraError, match="outro órgão"):
        validate_tjsc_page(page([1], total=1), special)
    with pytest.raises(FloraError, match="outro órgão"):
        validate_tjsc_page(page([1], total=1, organ=special), 9)


def collect_window_envelope(store, organ):
    def route(req):
        return httpx.Response(200, content=page([1], total=1))

    with httpx.Client(transport=httpx.MockTransport(route)) as http:
        return collect_window(http, Config(store.directory, request_delay=0), organ, date(2026, 9, 18))[0]
