from datetime import date
from urllib.parse import parse_qs

import httpx
import pytest

from flora_mcp.config import Config
from flora_mcp.model import FloraError
from flora_mcp.sources import validate_tjsc_page
from flora_mcp.tjsc import collect_window, parse_page


def page(ids, total=12, publication="18/09/2026"):
    html = '<meta charset="iso-8859-1"><input id="hdnTotalResultado" value="' + str(total) + '">'
    for id in ids:
        fields = {
            "ÓRGÃO JULGADOR": "9ª Câmara de Direito Civil",
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
