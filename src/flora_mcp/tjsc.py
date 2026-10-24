"""Experimental TJSC collector: complete public publication-day windows or no commit.

Besides the windows, a search by process number brings the acórdãos of one process, whatever the
organ (directed collection): each number is its own resource, kept apart from the windows. A
search by theme brings, for one organ, one search term and one publication period, every acórdão
whose ementa the portal matches; the caller filters what enters (public law, education).
"""

import base64
import json
import math
import re
import threading
import time
import unicodedata
from datetime import date, datetime, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .config import Config
from .model import FloraError, now, number
from .sources import TJSC_SEARCH, download, tjsc_field_label, validate_tjsc_page
from .store import Store
from .tjsc_orgaos import PADRAO, chamber, dataset, identity, name, window_name


class Pacer:
    """Global spacing between requests to the portal, shared by every thread of the process.

    Two requests never leave at the same instant, whatever the number of workers: each waits
    until `interval` seconds after the previous departure. The interval is the configured
    request_delay, divided by the number of parallel workers when a caller sets one.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._next = 0.0
        self.divisor = 1

    def wait(self, delay: float):
        interval = delay / max(1, self.divisor)
        with self._lock:
            at = max(time.monotonic(), self._next)
            self._next = at + interval
        pause = at - time.monotonic()
        if pause > 0:
            time.sleep(pause)


PACER = Pacer()


CNJ = re.compile(r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b")
# SAJ numbering as the portal shows it (0000.20.12.009537-4) and as votes cite it (2012.009537-4).
SAJ_PORTAL = re.compile(r"\b0000\.(\d{2})\.(\d{2})\.(\d{6})-(\d)\b")
SAJ_CITED = re.compile(r"\b(\d{4})\.(\d{6})-(\d)\b")


def process_number(field: str) -> str:
    """Process number of a card: CNJ as shown; SAJ as cited (AAAA.NNNNNN-D); else the field."""
    cnj = CNJ.search(field)
    if cnj:
        return cnj[0]
    saj = SAJ_PORTAL.search(field)
    return f"{saj[1]}{saj[2]}.{saj[3]}-{saj[4]}" if saj else field


def parse_cards(content: bytes, organ: int | str | None) -> tuple[int, list[tuple[dict, dict]]]:
    """Validated page and its documents; organ None for a search by process number."""
    validation = validate_tjsc_page(content, organ)
    soup = BeautifulSoup(content, "html.parser")
    rows = []
    for card in soup.select(".resultadoItem"):
        fields = {}
        for label in card.select(".resLabel"):
            value = label.find_next_sibling(class_="resValue")
            if value:
                fields[tjsc_field_label(label)] = value.get_text(" ", strip=True)
        try:
            publication = datetime.strptime(fields["DATA DA PUBLICAÇÃO"], "%d/%m/%Y").date()
            judgment = datetime.strptime(fields["DATA DO JULGAMENTO"], "%d/%m/%Y").date()
        except (KeyError, ValueError) as exc:
            raise FloraError("data_invalida", "TJSC sem datas reconhecíveis; janela não concluída.") from exc
        source_id = card["id"].removeprefix("resultado")
        link = card.select_one(".inteiroTeor")
        document_url = urljoin(TJSC_SEARCH, link["data-link"]) if link and link.get("data-link") else None
        raw = {"id": source_id, "campos": fields, "url_documento": document_url}
        process_field = fields.get("PROCESSO", "")
        process = process_number(process_field)
        class_match = re.search(r"/TJSC\s+([\w]+)\s+-", process_field)
        body = {
            "id": "TJSC:" + source_id,
            "id_origem": source_id,
            "tribunal": "TJSC",
            "orgao": fields["ÓRGÃO JULGADOR"],
            "classe": fields.get("CLASSE", class_match[1] if class_match else ""),
            "processo": process,
            "numero_processo": process,
            "processo_original": process_field,
            "numero_registro": "",
            "data_julgamento": judgment.isoformat(),
            "data_publicacao": publication.isoformat(),
            "publicacao_original": fields["DATA DA PUBLICAÇÃO"],
            "ementa": fields["EMENTA"],
            "url_documento": document_url,
            "inteiro_teor_disponivel": False,
            "tipo_conteudo": "espelho_do_portal",
            "extrator": "tjsc-html-v1",
            "atribuicao": "Tribunal de Justiça de Santa Catarina — portal público de jurisprudência.",
        }
        if not body["numero_processo"] or not source_id:
            raise FloraError("formato_invalido", "TJSC sem identidade documental.")
        rows.append((body, raw))
    return validation["total_informado"], rows


def parse_page(content: bytes, organ: int | str, day: date) -> tuple[int, list[tuple[dict, dict]]]:
    """Page of a publication-day window: every document must carry that publication day."""
    total, rows = parse_cards(content, organ)
    if any(body["data_publicacao"] != day.isoformat() for body, _ in rows):
        raise FloraError("filtro_nao_respeitado", "Documento TJSC fora do dia de publicação solicitado.")
    return total, rows


def collect_pages(
    http, config: Config, data: dict, parse, first_page: bytes | None = None
) -> tuple[int, list[dict], list]:
    """Every page of one portal search, with the first page fetched again at the end.

    parse(content) validates one page and returns (declared total, rows). Raises unless the count
    is stable, pages are full and disjoint, and the first page did not change during the traversal.
    first_page, when given, is the first page the caller has just fetched with the same data.
    """
    pages, rows, ids = [], [], set()

    def fetch(page):
        nonlocal first_page
        data["hdnPaginaAtual"] = str(page)
        url = TJSC_SEARCH if page == 1 else TJSC_SEARCH.replace("listar_resultados", "ajax_paginar_resultado")
        if first_page is not None:
            content, first_page = first_page, None
        else:
            PACER.wait(config.request_delay)
            content = download(http, url, config.max_download_bytes, method="POST", data=data)
        total, values = parse(content)
        pages.append(
            {
                "pagina": page,
                "url": url,
                "parametros": dict(data),
                "bytes_base64": base64.b64encode(content).decode(),
                "coletado_em": now(),
            }
        )
        return total, values

    total, first = fetch(1)
    page_count = max(1, math.ceil(total / 10))
    if page_count > 100:
        raise FloraError("janela_grande", "TJSC excedeu 100 páginas no dia; janela não concluída.")
    for page in range(1, page_count + 1):
        page_total, values = (total, first) if page == 1 else fetch(page)
        new_ids = {body["id"] for body, _ in values}
        if page_total != total or len(new_ids) != len(values) or ids & new_ids:
            raise FloraError(
                "paginacao_instavel", "Contagem variável ou IDs repetidos no TJSC; repetir janela."
            )
        if page < page_count and len(values) != 10:
            raise FloraError("paginacao_incompleta", "Página intermediária incompleta; janela não concluída.")
        ids |= new_ids
        rows.extend(values)
    if len(rows) != total:
        raise FloraError("paginacao_incompleta", "Número recuperado difere da contagem do portal.")
    # Recheck first page after traversal, including zero-result searches. A single page may come back
    # in another order (a search by term ranks ties at random); it must hold the same documents.
    end_total, end_first = fetch(1)
    same = first == end_first or (page_count == 1 and unordered(first) == unordered(end_first))
    if total != end_total or not same:
        raise FloraError("janela_alterada", "Primeira página mudou durante a coleta; repetir janela.")
    return total, pages, rows


def unordered(rows: list) -> list:
    return sorted(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows)


def collect_window(http, config: Config, organ: int | str, day: date):
    """Every page of one publication day of one organ, by portal name or chamber number."""
    date_string = day.strftime("%d/%m/%Y")
    data = {
        "txtPesquisa": "",
        "selOrgao[]": window_name(organ),
        "selOrigem[]": "1",
        "selTipoDocumento[]": "1",
        "rdoCampo": "E",
        "selTamanhoPagina": "10",
        "dtPublicacaoInicio": date_string,
        "dtPublicacaoFim": date_string,
        "hdnPublicacaoInicio": date_string,
        "hdnPublicacaoFim": date_string,
    }
    total, pages, rows = collect_pages(http, config, data, lambda content: parse_page(content, organ, day))
    payload = {
        "fonte": "TJSC",
        **identity(organ),
        "data_publicacao": day.isoformat(),
        "total": total,
        "paginas": pages,
    }
    return json.dumps(payload, ensure_ascii=False).encode(), rows


def catalog_window(store: Store, organ: int | str, day: date) -> str:
    """Catalog the publication-day window of an organ; returns the resource id.

    A Civil Law Chamber window keeps the metadata it always had (chamber number); another
    organ's window records the portal name instead.
    """
    window_name(organ)
    number = chamber(organ)
    resource = {
        "id": day.isoformat(),
        "name": day.strftime("%Y%m%d") + ".json",
        "url": TJSC_SEARCH,
        "last_modified": now(),
        "publication_day": day.isoformat(),
        **({"chamber": number} if number is not None else {"orgao": name(organ)}),
        "tipo": "janela_publicacao",
    }
    store.catalog(
        dataset(organ),
        {"fonte": TJSC_SEARCH, "tipo": "janela_publicacao"},
        [resource],
        complete_listing=False,
    )
    return dataset(organ) + ":" + resource["id"]


def parse_period_page(content: bytes, organ: int | str, start: date, end: date):
    """Page of a theme search: every document of that organ, published within the period."""
    total, rows = parse_cards(content, organ)
    if any(not start.isoformat() <= body["data_publicacao"] <= end.isoformat() for body, _ in rows):
        raise FloraError("filtro_nao_respeitado", "Documento TJSC fora do período de publicação solicitado.")
    return total, rows


def search_data(organ: int | str, term: str, start: date, end: date) -> dict:
    first, last = start.strftime("%d/%m/%Y"), end.strftime("%d/%m/%Y")
    return {
        "txtPesquisa": term,
        "selOrgao[]": name(organ),
        "selOrigem[]": "1",
        "selTipoDocumento[]": "1",
        "rdoCampo": "E",
        "selTamanhoPagina": "10",
        "dtPublicacaoInicio": first,
        "dtPublicacaoFim": last,
        "hdnPublicacaoInicio": first,
        "hdnPublicacaoFim": last,
        "hdnPaginaAtual": "1",
    }


# Answers of a theme search that a new attempt may cure; anything else stops the search.
UNSTABLE = {"paginacao_instavel", "paginacao_incompleta", "janela_alterada"}
SEARCH_ATTEMPTS = 3
UNION_PASSES = 6


def collect_union(http, config: Config, data: dict, parse, total: int, first_page: bytes):
    """One day of a theme search with more than one page, whose order changes at every request.

    Every pass reads all the pages, and the distinct acórdãos add up until they reach the declared
    total, which every page must repeat; the same acórdão may not come back different. Up to
    UNION_PASSES passes; short of the total, the search stops.
    """
    pages, found = [], {}
    page_count = math.ceil(total / 10)
    for passing in range(1, UNION_PASSES + 1):
        for page in range(1, page_count + 1):
            data["hdnPaginaAtual"] = str(page)
            url = (
                TJSC_SEARCH
                if page == 1
                else TJSC_SEARCH.replace("listar_resultados", "ajax_paginar_resultado")
            )
            if first_page is not None:
                content, first_page = first_page, None
            else:
                PACER.wait(config.request_delay)
                content = download(http, url, config.max_download_bytes, method="POST", data=data)
            page_total, values = parse(content)
            if page_total != total:
                raise FloraError("paginacao_instavel", "Contagem variável no TJSC; repetir consulta.")
            for body, raw in values:
                if found.get(body["id"], (body, raw)) != (body, raw):
                    raise FloraError(
                        "janela_alterada", "Acórdão TJSC mudou durante a coleta; repetir consulta."
                    )
                found[body["id"]] = (body, raw)
            pages.append(
                {
                    "passagem": passing,
                    "pagina": page,
                    "url": url,
                    "parametros": dict(data),
                    "bytes_base64": base64.b64encode(content).decode(),
                    "coletado_em": now(),
                }
            )
        if len(found) == total:
            return total, pages, [found[key] for key in sorted(found)]
    raise FloraError("paginacao_incompleta", f"TJSC devolveu {len(found)} de {total} acórdãos do dia.")


def collect_search(http, config: Config, organ: int | str, term: str, start: date, end: date):
    """Every acórdão of one organ, one search term in the ementa and one publication period.

    The portal has no ordering field, and a long search by term pages unstably (the same acórdão
    on two pages). A period with more than one page is split in halves until each part fits one
    page; only a single day with more results is paged, with the window checks. The first page of
    every split period stays in the envelope as provenance. The portal now and then answers a part
    with a repeated or reordered acórdão: the part is tried again, from a new first page, up to
    SEARCH_ATTEMPTS times, and the envelope records how many it took.
    """
    parts, probes, rows, ids = [], [], [], set()

    def sound(a: date, b: date):
        data = search_data(organ, term, a, b)
        PACER.wait(config.request_delay)
        probe = download(http, TJSC_SEARCH, config.max_download_bytes, method="POST", data=dict(data))
        total, _ = parse_period_page(probe, organ, a, b)
        return data, probe, total

    def visit(a: date, b: date):
        data, probe, total = sound(a, b)
        parse = lambda content: parse_period_page(content, organ, a, b)  # noqa: E731
        attempt = 1
        while total <= 10 or a == b:
            try:
                if total > 10:  # a single day with more than one page
                    part_total, pages, found = collect_union(http, config, data, parse, total, probe)
                else:
                    part_total, pages, found = collect_pages(http, config, data, parse, first_page=probe)
                break
            except FloraError as exc:
                if exc.code not in UNSTABLE or attempt == SEARCH_ATTEMPTS:
                    raise
                attempt += 1
                data, probe, total = sound(a, b)
        if total > 10 and a < b:
            probes.append(
                {
                    "publicacao_inicio": a.isoformat(),
                    "publicacao_fim": b.isoformat(),
                    "total": total,
                    "parametros": data,
                    "bytes_base64": base64.b64encode(probe).decode(),
                    "coletado_em": now(),
                }
            )
            middle = a + (b - a) // 2
            visit(a, middle)
            visit(middle + timedelta(days=1), b)
            return
        new = {body["id"] for body, _ in found}
        if ids & new:
            raise FloraError("paginacao_instavel", "Acórdão TJSC em dois períodos da mesma consulta.")
        ids.update(new)
        rows.extend(found)
        parts.append(
            {
                "publicacao_inicio": a.isoformat(),
                "publicacao_fim": b.isoformat(),
                "total": part_total,
                "tentativas": attempt,
                "paginas": pages,
            }
        )

    visit(start, end)
    payload = {
        "fonte": "TJSC",
        "consulta": "tema",
        **identity(organ),
        "termo": term,
        "publicacao_inicio": start.isoformat(),
        "publicacao_fim": end.isoformat(),
        "total": len(rows),
        "partes": parts,
        "sondagens": probes,
    }
    return json.dumps(payload, ensure_ascii=False).encode(), rows


def term_slug(term: str) -> str:
    plain = unicodedata.normalize("NFKD", term).encode("ascii", "ignore").decode()
    return "-".join(re.findall(r"[a-z0-9]+", plain.lower()))


# Rank of a theme search: above the search by number and below every window ("AAAAMMDD").
TEMA_RANK = "00000001"


def catalog_search(store: Store, organ: int | str, term: str, start: date, end: date) -> str:
    """Catalog one theme search in the organ's dataset; returns the resource id."""
    key = f"tema-{term_slug(term)}-{start.isoformat()}-{end.isoformat()}"
    resource = {
        "id": key,
        "name": key + ".json",
        "url": TJSC_SEARCH,
        "last_modified": now(),
        "orgao": name(organ),
        "termo": term,
        "publicacao_inicio": start.isoformat(),
        "publicacao_fim": end.isoformat(),
        "tipo": "consulta_tema",
        "rank": TEMA_RANK,
    }
    store.catalog(
        dataset(organ), {"fonte": TJSC_SEARCH, "tipo": "consulta_tema"}, [resource], complete_listing=False
    )
    return dataset(organ) + ":" + key


PROCESSO_DATASET = "tjsc-processo"
# Rank of a process resource: below every window ("AAAAMMDD"), so a document a window also holds
# keeps the window as its current version; the search by number only adds what no window has.
PROCESSO_RANK = "00000000"


def process_key(value: str) -> str:
    """Digits that identify a TJSC process: 20 (CNJ, masked or not) or 11 (SAJ, AAAA.NNNNNN-D)."""
    text = str(value)
    portal = SAJ_PORTAL.search(text)
    found = CNJ.search(text) or SAJ_CITED.search(text)
    # The portal form of a SAJ number carries four leading zeros before the year.
    digits = number(portal[0])[4:] if portal and not found else number(found[0] if found else text)
    if len(digits) in (11, 20):
        return digits
    raise FloraError("numero_invalido", f"Número de processo do TJSC não reconhecido: {value}.")


def portal_number(key: str) -> str:
    """Process number as the portal search field takes it and as the card shows it."""
    if len(key) == 20:
        return f"{key[:7]}-{key[7:9]}.{key[9:13]}.{key[13]}.{key[14:16]}.{key[16:]}"
    return f"{key[:4]}.{key[4:10]}-{key[10]}"


def parse_process_page(content: bytes, key: str) -> tuple[int, list[tuple[dict, dict]]]:
    """Page of a search by number: any organ, but every document of the requested process."""
    total, rows = parse_cards(content, None)
    for body, _ in rows:
        shown = number(body["processo_original"].split("/TJSC")[0]).lstrip("0")
        if shown != key.lstrip("0"):
            raise FloraError("filtro_nao_respeitado", "TJSC devolveu documento de outro processo.")
    return total, rows


def collect_process(http, config: Config, key: str):
    """Every acórdão the portal holds for one process number, from any organ."""
    data = {
        "txtPesquisa": "",
        "txtProcesso": portal_number(key),
        "selOrigem[]": "1",
        "selTipoDocumento[]": "1",
        "rdoCampo": "E",
        "selTamanhoPagina": "10",
    }
    total, pages, rows = collect_pages(http, config, data, lambda content: parse_process_page(content, key))
    payload = {
        "fonte": "TJSC",
        "consulta": "processo",
        "numero_processo": portal_number(key),
        "total": total,
        "paginas": pages,
    }
    return json.dumps(payload, ensure_ascii=False).encode(), rows


def catalog_process(store: Store, key: str) -> str:
    """Catalog the search of one process number; returns the resource id."""
    resource = {
        "id": key,
        "name": key + ".json",
        "url": TJSC_SEARCH,
        "last_modified": now(),
        "numero_processo": portal_number(key),
        "tipo": "consulta_processo",
        "rank": PROCESSO_RANK,
    }
    store.catalog(
        PROCESSO_DATASET,
        {"fonte": TJSC_SEARCH, "tipo": "consulta_processo"},
        [resource],
        complete_listing=False,
    )
    return PROCESSO_DATASET + ":" + key


def sync_tjsc(config: Config, store: Store, http, start: date, end: date, organs=PADRAO) -> dict:
    if start > end or (end - start).days > 30:
        raise FloraError("intervalo_invalido", "Escolha de 1 a 31 dias por execução TJSC.")
    run = store.start_run("TJSC")
    result = {"execucao": run, "fonte": "TJSC", "experimental": True, "eventos": [], "falhas": []}
    try:
        for organ in organs:
            day = start
            while day <= end:
                resource_id = catalog_window(store, organ, day)
                saved = next(r for r in store.resources(dataset(organ)) if r["id"] == resource_id)
                try:
                    content, rows = collect_window(http, config, organ, day)
                    counts = store.ingest(saved, content, rows, run)
                    result["eventos"].append(
                        {
                            **identity(organ),
                            "dia_publicacao": day.isoformat(),
                            "registros": len(rows),
                            **counts,
                        }
                    )
                except Exception as exc:
                    store.failure(saved["id"], run, str(exc))
                    result["falhas"].append(
                        {
                            **identity(organ),
                            "dia": day.isoformat(),
                            "codigo": getattr(exc, "code", "erro_fonte"),
                            "erro": str(exc),
                        }
                    )
                    # Stop on first source failure, retain earlier committed windows.
                    result["status"] = "error"
                    store.finish_run(run, "error", result)
                    return result
                day += timedelta(days=1)
        result["status"] = "ok"
        store.finish_run(run, "ok", result)
        return result
    except BaseException:
        store.finish_run(run, "interrupted", {"erro": "Execução interrompida; repetir janela."})
        raise
