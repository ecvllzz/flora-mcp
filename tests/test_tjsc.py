import json
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from flora_mcp.config import Config
from flora_mcp.model import FloraError
from flora_mcp.sources import validate_tjsc_page
from flora_mcp.store import connection
from flora_mcp.tjsc import UNION_PASSES, collect_window, parse_page, sync_tjsc
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
            assert "coleta" not in json.loads(content)
        elif scenario == "first_page_changes":
            content, rows = collect_window(http, config, 9, date(2026, 9, 18))
            envelope = json.loads(content)
            assert len(rows) == 12 and envelope["total"] == 12
            assert (envelope["coleta"], envelope["instabilidade"]) == (
                "uniao_de_passagens",
                "janela_alterada",
            )
            assert all("passagem" in saved for saved in envelope["paginas"])
        else:
            with pytest.raises(FloraError):
                collect_window(http, config, 9, date(2026, 9, 18))


def window_route(answers):
    """Answers in sequence; each request gets the next (ids, keyword arguments of page)."""
    pending = iter(answers)

    def route(_req):
        ids, options = next(pending)
        return httpx.Response(200, content=page(ids, **options))

    return route


def recollect(store, answers):
    with httpx.Client(transport=httpx.MockTransport(window_route(answers))) as http:
        return collect_window(http, Config(store.directory, request_delay=0), 9, date(2026, 9, 18))


def test_pages_that_change_order_between_passes_conclude_with_the_total(store):
    content, rows = recollect(
        store,
        [
            (range(10), {}),  # first reading: page 2 repeats a document
            ([0, 1], {}),
            (range(10), {}),  # new first page, first pass misses 10 and 11
            ([8, 9], {}),
            (range(2, 12), {}),  # second pass brings them
            ([0, 1], {}),
        ],
    )
    envelope = json.loads(content)
    assert {body["id"] for body, _ in rows} == {f"TJSC:{i}" for i in range(12)}
    assert (envelope["coleta"], envelope["instabilidade"]) == ("uniao_de_passagens", "paginacao_instavel")
    assert [(p["passagem"], p["pagina"]) for p in envelope["paginas"]] == [(1, 1), (1, 2), (2, 1), (2, 2)]


def test_same_document_with_different_content_fails(store):
    other = page([0, 11]).replace("Texto público".encode("latin1"), b"Outro texto")
    answers = [(range(10), {}), ([0, 1], {}), (range(10), {})]
    pending = iter(answers)

    def route(_req):
        try:
            ids, options = next(pending)
        except StopIteration:
            return httpx.Response(200, content=other)  # document 0 comes back with another ementa
        return httpx.Response(200, content=page(ids, **options))

    with httpx.Client(transport=httpx.MockTransport(route)) as http:
        with pytest.raises(FloraError) as info:
            collect_window(http, Config(store.directory, request_delay=0), 9, date(2026, 9, 18))
    assert info.value.code == "janela_alterada"


def test_union_short_of_the_total_does_not_conclude(store):
    answers = [(range(10), {}), ([0, 1], {})] + [(range(10), {}), ([0, 1], {})] * UNION_PASSES
    with pytest.raises(FloraError) as info:
        recollect(store, answers)
    assert info.value.code == "paginacao_incompleta"


def test_single_page_is_read_again_and_recorded(store):
    answers = [([1, 2], {"total": 2}), ([3, 4], {"total": 2})]  # first reading ends in a changed page
    answers += [([1, 2], {"total": 2}), ([1, 2], {"total": 2})]
    content, rows = recollect(store, answers)
    envelope = json.loads(content)
    assert len(rows) == 2 and envelope["coleta"] == "nova_leitura"


def test_block_during_the_new_reading_stops_the_window(store):
    calls = 0

    def route(_req):
        nonlocal calls
        calls += 1
        if calls > 2:
            return httpx.Response(200, content=b"<html>captcha</html>")
        return httpx.Response(200, content=page(range(10)) if calls == 1 else page([0, 1]))

    with httpx.Client(transport=httpx.MockTransport(route)) as http:
        with pytest.raises(FloraError) as info:
            collect_window(http, Config(store.directory, request_delay=0), 9, date(2026, 9, 18))
    assert info.value.code == "acesso_bloqueado"


def sync_days(store, monkeypatch, failing_code):
    """sync_tjsc over three days of two chambers, the first chamber failing on the second day."""
    calls = []

    def fetch(_http, _config, organ, day):
        calls.append((organ, day))
        if (organ, day) == (9, date(2026, 9, 2)):
            raise FloraError(failing_code, "falha da janela")
        envelope = {"fonte": "TJSC", "camara": organ, "data_publicacao": str(day), "total": 0}
        return json.dumps(envelope).encode(), []

    monkeypatch.setattr("flora_mcp.tjsc.collect_window", fetch)
    config = Config(store.directory, request_delay=0)
    result = sync_tjsc(config, store, None, date(2026, 9, 1), date(2026, 9, 3), organs=(9, 10))
    with connection(store.path) as db:
        run = db.execute("SELECT status FROM runs WHERE id=?", (result["execucao"],)).fetchone()[0]
        failed = [r[0] for r in db.execute("SELECT id FROM resources WHERE status='error'")]
    return result, calls, run, failed


@pytest.mark.parametrize("code", ["paginacao_instavel", "paginacao_incompleta", "janela_alterada"])
def test_unstable_window_does_not_stop_sync(store, monkeypatch, code):
    result, calls, run, failed = sync_days(store, monkeypatch, code)
    assert len(calls) == 6 and len(result["eventos"]) == 5
    assert (result["status"], run) == ("partial", "partial")
    assert failed == ["tjsc-9-civil:2026-09-02"]
    assert [(f["codigo"], f["dia"]) for f in result["falhas"]] == [(code, "2026-09-02")]


def test_blocked_portal_stops_sync(store, monkeypatch):
    result, calls, run, failed = sync_days(store, monkeypatch, "acesso_bloqueado")
    assert len(calls) == 2 and len(result["eventos"]) == 1
    assert (result["status"], run) == ("error", "error")
    assert failed == ["tjsc-9-civil:2026-09-02"]


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


def test_pacer_spaces_requests_across_threads_by_delay_over_divisor():
    import threading
    import time

    from flora_mcp.tjsc import Pacer

    pacer = Pacer()
    pacer.divisor = 4
    departures = []
    lock = threading.Lock()

    def go():
        pacer.wait(0.2)
        with lock:
            departures.append(time.monotonic())

    threads = [threading.Thread(target=go) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    departures.sort()
    gaps = [b - a for a, b in zip(departures, departures[1:], strict=False)]
    assert min(gaps) >= 0.045  # 0.2 / 4, with scheduling slack
    assert departures[-1] - departures[0] < 1.0
