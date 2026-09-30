"""Official HTTP sources; no browser challenge or CAPTCHA circumvention."""

import json
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from .config import Config
from .model import FloraError, digest, normalize_stj, now
from .store import Store
from .tjsc_orgaos import PADRAO, dataset, identity, name

STJ_API = "https://dadosabertos.web.stj.jus.br/api/3/action/package_show"
TJSC_SEARCH = (
    "https://eprocwebcon.tjsc.jus.br/consulta1g/externo_controlador.php"
    "?acao=jurisprudencia@jurisprudencia/listar_resultados"
)


def client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(45, connect=15),
        follow_redirects=False,
        headers={"User-Agent": "Flora-MCP/0.1 (public jurisprudence research)"},
    )


def download(http: httpx.Client, url: str, limit: int, *, method="GET", **kwargs) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {
        "dadosabertos.web.stj.jus.br",
        "eprocwebcon.tjsc.jus.br",
    }:
        raise FloraError("url_nao_permitida", "Fonte fora dos domínios oficiais autorizados.")
    for attempt in range(3):
        try:
            with http.stream(method, url, **kwargs) as response:
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 2:
                        time.sleep(min(10, 2 ** (attempt + 1)))
                        continue
                response.raise_for_status()
                length = response.headers.get("content-length", "")
                if length.isdigit() and int(length) > limit:
                    raise FloraError("recurso_grande", "Recurso excede o limite de download configurado.")
                chunks, size = [], 0
                for block in response.iter_bytes():
                    size += len(block)
                    if size > limit:
                        raise FloraError("recurso_grande", "Download excede o limite configurado.")
                    chunks.append(block)
                return b"".join(chunks)
        except (httpx.TimeoutException, httpx.NetworkError):
            if attempt == 2:
                raise
            time.sleep(2**attempt)
    raise FloraError("rede_indisponivel", "Tentativas de download esgotadas.")


def parse_json(content: bytes):
    try:
        return json.loads(content)
    except (ValueError, UnicodeError) as exc:
        raise FloraError(
            "formato_invalido", "A fonte não retornou JSON válido; nenhum recurso foi concluído."
        ) from exc


def normalize_batch(records) -> tuple[list[tuple[dict, dict]], list[dict]]:
    """Valid mirrors of one STJ batch and the rejected ones, identified by position (from 0) and id."""
    if not isinstance(records, list) or not records:
        raise FloraError("formato_invalido", "Recurso STJ vazio ou sem lista de espelhos.")
    rows, rejected = [], []
    for position, raw in enumerate(records):
        try:
            rows.append((normalize_stj(raw), raw))
        except FloraError as exc:
            identity = raw.get("id") if isinstance(raw, dict) else None
            rejected.append({"posicao": position, "id": identity or None, "motivo": str(exc)})
    if not rows:
        raise FloraError("formato_invalido", "Nenhum espelho válido no lote. " + rejected[0]["motivo"])
    return rows, rejected


def sync_stj(config: Config, store: Store, http: httpx.Client, *, force: bool = False) -> dict:
    run = store.start_run("STJ")
    report = {
        "execucao": run,
        "fonte": "STJ",
        "eventos": [],
        "falhas": [],
        "selecao": {"recursos_desde": config.resource_from, "limite_por_dataset": config.max_resources},
    }
    try:
        for dataset in config.datasets:
            try:
                payload = parse_json(download(http, STJ_API, 4 * 1024 * 1024, params={"id": dataset}))
                if not isinstance(payload, dict) or payload.get("success") is not True:
                    raise FloraError("catalogo_invalido", "Catálogo STJ não confirmou sucesso.")
                package = payload["result"]
                selected = [
                    r
                    for r in package["resources"]
                    if re.fullmatch(r"\d{8}\.json", r.get("name", ""))
                    and r["name"][:8] >= config.resource_from
                ]
                if not selected:
                    raise FloraError(
                        "catalogo_vazio", "Nenhum recurso JSON corresponde ao recorte configurado."
                    )
                store.catalog(dataset, package, selected)
                resources = store.resources(dataset)
                cutoff = datetime.now(timezone.utc) - timedelta(days=config.recheck_days)
                pending = [
                    r
                    for r in resources
                    if r["status"] != "ok" or r["applied_fingerprint"] != r["expected_fingerprint"]
                ]
                recheck = [
                    r
                    for r in resources
                    if r not in pending
                    and (force or not r["checked"] or datetime.fromisoformat(r["checked"]) < cutoff)
                ]
                # Oldest verification first prevents starvation during historical reconciliation.
                recheck.sort(key=lambda r: r["checked"] or "")
                tasks = (pending + recheck)[: config.max_resources]
                for resource in tasks:
                    try:
                        time.sleep(config.request_delay)
                        content = download(http, resource["url"], config.max_download_bytes)
                        rows, rejected = normalize_batch(parse_json(content))
                        counts = store.ingest(resource, content, rows, run, rejected=rejected)
                        event = {"dataset": dataset, "recurso": resource["name"], "registros": len(rows)}
                        report["eventos"].append({**event, **counts})
                        if rejected:
                            report["eventos"][-1]["rejeitados"] = rejected
                            report.setdefault("rejeitados", []).append({**event, "registros": len(rejected)})
                    except (FloraError, httpx.HTTPError, KeyError, ValueError) as exc:
                        store.failure(resource["id"], run, str(exc))
                        report["falhas"].append(
                            {
                                "dataset": dataset,
                                "recurso": resource["name"],
                                "codigo": getattr(exc, "code", "erro_fonte"),
                                "erro": str(exc),
                            }
                        )
                current = store.resources(dataset)
                report.setdefault("datasets", []).append(
                    {
                        "dataset": dataset,
                        "recursos_catalogados": len(current),
                        "recursos_pendentes": sum(
                            r["status"] != "ok" or r["applied_fingerprint"] != r["expected_fingerprint"]
                            for r in current
                        ),
                    }
                )
            except (FloraError, httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                report["falhas"].append(
                    {"dataset": dataset, "codigo": getattr(exc, "code", "erro_catalogo"), "erro": str(exc)}
                )
        report["status"] = (
            "error"
            if report["falhas"]
            else "partial"
            if any(d["recursos_pendentes"] for d in report.get("datasets", []))
            else "ok"
        )
        store.finish_run(run, report["status"], report)
        return report
    except BaseException:
        store.finish_run(run, "interrupted", {"erro": "Execução interrompida; retomar recursos pendentes."})
        raise


def tjsc_field_label(label) -> str:
    # Copy-button icon text is UI, not part of the field name.
    for control in label.select(".copiarCampoResultado"):
        control.decompose()
    return label.get_text(" ", strip=True)


def validate_tjsc_page(content: bytes, organ: int | str) -> dict:
    """organ: portal name of the filtered organ, or the number of a Civil Law Chamber."""
    expected = name(organ)
    soup = BeautifulSoup(content, "html.parser")
    html = soup.get_text(" ", strip=True)
    challenge = ("enable javascript", "support id", "verificação de segurança", "captcha")
    if any(marker in html.lower() for marker in challenge):
        raise FloraError(
            "acesso_bloqueado", "Portal TJSC apresentou verificação de acesso; coleta não validada."
        )
    total = soup.select_one("#hdnTotalResultado")
    cards = soup.select(".resultadoItem")
    # The portal omits the hidden value on genuine zero-result pages.
    explicit_zero = any(h.get_text(" ", strip=True) == "0 documentos encontrados" for h in soup.select("h2"))
    if total is not None and not total.get("value") and explicit_zero and not cards:
        return {
            "total_informado": 0,
            "documentos_na_pagina": 0,
            "paginacao_validada": False,
            "ingestao": False,
        }
    if not total or not str(total.get("value", "")).isdigit():
        raise FloraError("formato_invalido", "Portal TJSC sem contagem de resultados reconhecível.")
    if int(total["value"]) and not cards:
        raise FloraError(
            "formato_invalido", "Portal declara resultados, mas não contém documentos reconhecíveis."
        )
    for card in cards:
        fields = {}
        for label in card.select(".resLabel"):
            value = label.find_next_sibling(class_="resValue")
            if value:
                fields[tjsc_field_label(label)] = value.get_text("\n", strip=True)
        if fields.get("ÓRGÃO JULGADOR") != expected:
            raise FloraError("filtro_nao_respeitado", "TJSC devolveu documento de outro órgão.")
        if not card.get("id", "").startswith("resultado") or not fields.get("EMENTA"):
            raise FloraError("formato_invalido", "Documento TJSC sem identificador ou ementa.")
    return {
        "total_informado": int(total["value"]),
        "documentos_na_pagina": len(cards),
        "paginacao_validada": False,
        "ingestao": False,
    }


def probe_tjsc(config: Config, store: Store, http: httpx.Client) -> dict:
    run = store.start_run("TJSC-probe")
    result = {"execucao": run, "eventos": [], "ingestao": False}
    for organ in PADRAO:
        event = {**identity(organ), "verificado_em": now()}
        try:
            content = download(
                http,
                TJSC_SEARCH,
                4 * 1024 * 1024,
                method="POST",
                data={
                    "txtPesquisa": "",
                    "selOrgao[]": organ,
                    "selOrigem[]": "1",
                    "selTipoDocumento[]": "1",
                    "rdoCampo": "E",
                    "hdnPaginaAtual": "1",
                    "selTamanhoPagina": "10",
                },
            )
            evidence = config.data_dir / "probes" / run
            evidence.mkdir(parents=True, exist_ok=True)
            (evidence / f"{dataset(organ)}.html").write_bytes(content)
            event["sha256"] = digest(content)
            event.update(validate_tjsc_page(content, organ))
            event["status"] = "pagina_validada"
        except (FloraError, httpx.HTTPError) as exc:
            event.update(status="error", codigo=getattr(exc, "code", "erro_http"), erro=str(exc))
        result["eventos"].append(event)
        time.sleep(config.request_delay)
    result["status"] = "error" if any(e["status"] == "error" for e in result["eventos"]) else "partial"
    store.finish_run(run, result["status"], result)
    return result
