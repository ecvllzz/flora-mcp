"""Experimental TJSC collector: complete public publication-day windows or no commit."""

import base64
import json
import math
import re
import time
from datetime import date, datetime, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .config import Config
from .model import FloraError, now
from .sources import TJSC_SEARCH, download, tjsc_field_label, validate_tjsc_page
from .store import Store


def parse_page(content: bytes, chamber: int, day: date) -> tuple[int, list[tuple[dict, dict]]]:
    validation = validate_tjsc_page(content, chamber)
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
        if publication != day:
            raise FloraError("filtro_nao_respeitado", "Documento TJSC fora do dia de publicação solicitado.")
        source_id = card["id"].removeprefix("resultado")
        link = card.select_one(".inteiroTeor")
        document_url = urljoin(TJSC_SEARCH, link["data-link"]) if link and link.get("data-link") else None
        raw = {"id": source_id, "campos": fields, "url_documento": document_url}
        process_field = fields.get("PROCESSO", "")
        process_match = re.search(r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b", process_field)
        class_match = re.search(r"/TJSC\s+([\w]+)\s+-", process_field)
        body = {
            "id": "TJSC:" + source_id,
            "id_origem": source_id,
            "tribunal": "TJSC",
            "orgao": fields["ÓRGÃO JULGADOR"],
            "classe": fields.get("CLASSE", class_match[1] if class_match else ""),
            "processo": process_match[0] if process_match else process_field,
            "numero_processo": process_match[0] if process_match else process_field,
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


def collect_window(http, config: Config, chamber: int, day: date):
    date_string = day.strftime("%d/%m/%Y")
    data = {
        "txtPesquisa": "",
        "selOrgao[]": f"{chamber}ª Câmara de Direito Civil",
        "selOrigem[]": "1",
        "selTipoDocumento[]": "1",
        "rdoCampo": "E",
        "selTamanhoPagina": "10",
        "dtPublicacaoInicio": date_string,
        "dtPublicacaoFim": date_string,
        "hdnPublicacaoInicio": date_string,
        "hdnPublicacaoFim": date_string,
    }
    pages, rows, ids = [], [], set()

    def fetch(page):
        time.sleep(config.request_delay)
        data["hdnPaginaAtual"] = str(page)
        url = TJSC_SEARCH if page == 1 else TJSC_SEARCH.replace("listar_resultados", "ajax_paginar_resultado")
        content = download(http, url, config.max_download_bytes, method="POST", data=data)
        total, values = parse_page(content, chamber, day)
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
    # Recheck first page after traversal, including zero-result windows.
    end_total, end_first = fetch(1)
    if total != end_total or first != end_first:
        raise FloraError("janela_alterada", "Primeira página mudou durante a coleta; repetir janela.")
    payload = {
        "fonte": "TJSC",
        "camara": chamber,
        "data_publicacao": day.isoformat(),
        "total": total,
        "paginas": pages,
    }
    return json.dumps(payload, ensure_ascii=False).encode(), rows


def sync_tjsc(config: Config, store: Store, http, start: date, end: date) -> dict:
    if start > end or (end - start).days > 30:
        raise FloraError("intervalo_invalido", "Escolha de 1 a 31 dias por execução TJSC.")
    run = store.start_run("TJSC")
    result = {"execucao": run, "fonte": "TJSC", "experimental": True, "eventos": [], "falhas": []}
    try:
        for chamber in (9, 10):
            day = start
            while day <= end:
                dataset = f"tjsc-{chamber}-civil"
                resource = {
                    "id": day.isoformat(),
                    "name": day.strftime("%Y%m%d") + ".json",
                    "url": TJSC_SEARCH,
                    "last_modified": now(),
                    "publication_day": day.isoformat(),
                    "chamber": chamber,
                    "tipo": "janela_publicacao",
                }
                store.catalog(
                    dataset,
                    {"fonte": TJSC_SEARCH, "tipo": "janela_publicacao"},
                    [resource],
                    complete_listing=False,
                )
                saved = next(r for r in store.resources(dataset) if r["id"] == dataset + ":" + resource["id"])
                try:
                    content, rows = collect_window(http, config, chamber, day)
                    counts = store.ingest(saved, content, rows, run)
                    result["eventos"].append(
                        {
                            "camara": chamber,
                            "dia_publicacao": day.isoformat(),
                            "registros": len(rows),
                            **counts,
                        }
                    )
                except Exception as exc:
                    store.failure(saved["id"], run, str(exc))
                    result["falhas"].append(
                        {
                            "camara": chamber,
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
