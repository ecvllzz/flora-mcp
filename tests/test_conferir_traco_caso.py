"""Conferência de traço de caso, sobre repositórios temporários.

Os traços são montados por concatenação, para este arquivo passar pela própria conferência.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "conferir_traco_caso.py"
spec = importlib.util.spec_from_file_location("conferir_traco_caso", SCRIPT)
assert spec and spec.loader
conferir = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = conferir
spec.loader.exec_module(conferir)

PASTA_CASOS = "Cas" + "os/"
PASTA_CASOS_WINDOWS = "Cas" + "os\\\\"
PASTA_CASO = "AP" + "L_5001234"


def _ambiente() -> dict[str, str]:
    """Sem as variáveis que o hook herda, que apontariam o git para o repositório real."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _git(raiz: Path, *args: str) -> str:
    comando = [
        "git",
        "-C",
        str(raiz),
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t",
        "-c",
        "commit.gpgsign=false",
    ]
    return subprocess.run(
        [*comando, *args], capture_output=True, text=True, check=True, env=_ambiente()
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    for variavel in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(variavel)
    raiz = tmp_path / "repo"
    raiz.mkdir()
    _git(raiz, "init", "-q")
    (raiz / "limpo.txt").write_text("nada aqui\n", encoding="utf-8")
    _git(raiz, "add", ".")
    _git(raiz, "commit", "-q", "-m", "inicio")
    return raiz


def _commit(raiz: Path, nome: str, texto: str, mensagem: str = "muda") -> str:
    caminho = raiz / nome
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(texto, encoding="utf-8")
    _git(raiz, "add", ".")
    _git(raiz, "commit", "-q", "-m", mensagem)
    return _git(raiz, "rev-parse", "HEAD")


@pytest.mark.parametrize(
    "texto",
    [
        f'"path": "{PASTA_CASOS}x"',
        f'"path": "{PASTA_CASOS_WINDOWS}x"',
        f"D:/Vault/{PASTA_CASOS.lower()}x",
        f"/{PASTA_CASO}_Nome",
        "AD" + "_12",
        "ED" + "_12",
        "AI" + "_12",
        "HC" + "_12",
        "EDHC" + "_12",
    ],
)
def test_acha_traco(texto):
    assert conferir.achar(texto.encode())


@pytest.mark.parametrize(
    "texto",
    ["ocasos/x", "acasos\\x", "Casos de uso", "LOAD_1", "MAIL_2", "AI_x", "ED_", "APL 5001234", "RAID_5"],
)
def test_nao_acha_o_que_nao_e_traco(texto):
    assert conferir.achar(texto.encode()) == []


def test_indice_limpo(repo):
    assert conferir.conferir_indice(repo) == []


def test_indice_recusa_conteudo_preparado_e_nao_repete_o_trecho(repo):
    (repo / "conjunto.json").write_text(f'{{\n"p": "{PASTA_CASOS}{PASTA_CASO}"\n}}\n', encoding="utf-8")
    assert conferir.conferir_indice(repo) == []
    _git(repo, "add", ".")
    problemas = conferir.conferir_indice(repo)
    assert "conjunto.json:2: caminho de casos" in problemas
    assert "conjunto.json:2: pasta de caso" in problemas
    assert not any(PASTA_CASO in p for p in problemas)


def test_indice_recusa_nome_de_arquivo_sem_repetir_o_nome(repo):
    nome = f"docs/{PASTA_CASO}_Partes.txt"
    (repo / "docs").mkdir()
    (repo / nome).write_text("nada\n", encoding="utf-8")
    _git(repo, "add", ".")
    assert conferir.conferir_indice(repo) == ["docs/<traço>: traço no nome do arquivo"]


def test_indice_ignora_binario(repo):
    (repo / "b.bin").write_bytes(b"\0" + PASTA_CASOS.encode())
    _git(repo, "add", ".")
    assert conferir.conferir_indice(repo) == []


def test_arvore_de_ref(repo):
    assert conferir.conferir_arvore("HEAD", repo) == []
    _commit(repo, "x.txt", PASTA_CASOS)
    assert conferir.conferir_arvore("HEAD", repo) == ["HEAD: x.txt:1: caminho de casos"]


def test_commits_acham_mensagem_acrescimo_e_nome(repo):
    base = _git(repo, "rev-parse", "HEAD")
    mensagem = _commit(repo, "a.txt", "limpo\n", f"cita {PASTA_CASO}")
    acrescimo = _commit(repo, "b.txt", f"{PASTA_CASOS}x\n")
    nome = _commit(repo, f"{PASTA_CASO}.txt", "limpo\n")
    problemas = conferir.conferir_commits(f"{base}..HEAD", raiz=repo)
    assert f"commit {mensagem[:10]}: mensagem: pasta de caso" in problemas
    assert f"commit {acrescimo[:10]}: b.txt: caminho de casos" in problemas
    assert f"commit {nome[:10]}: <traço>: traço no nome do arquivo" in problemas


def test_commits_acham_nome_de_arquivo_vazio(repo):
    base = _git(repo, "rev-parse", "HEAD")
    vazio = _commit(repo, f"docs/{PASTA_CASO}.txt", "")
    assert conferir.conferir_commits(f"{base}..HEAD", raiz=repo) == [
        f"commit {vazio[:10]}: docs/<traço>: traço no nome do arquivo"
    ]


def test_commit_que_retira_o_traco_passa(repo):
    _commit(repo, "a.txt", f"{PASTA_CASOS}x\n")
    _commit(repo, f"{PASTA_CASO}.txt", "limpo\n")
    base = _git(repo, "rev-parse", "HEAD")
    _commit(repo, "a.txt", "limpo\n")
    _git(repo, "rm", "-q", f"{PASTA_CASO}.txt")
    _git(repo, "commit", "-q", "-m", "retira")
    assert conferir.conferir_commits(f"{base}..HEAD", raiz=repo) == []


def test_merge_com_traco_na_resolucao(repo):
    principal = _git(repo, "branch", "--show-current")
    _git(repo, "switch", "-q", "-c", "lado")
    _commit(repo, "lado.txt", "limpo\n")
    _git(repo, "switch", "-q", principal)
    base = _commit(repo, "outro.txt", "limpo\n")
    _git(repo, "merge", "-q", "--no-commit", "--no-ff", "lado")
    (repo / "lado.txt").write_text(f"{PASTA_CASOS}x\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "merge")
    problemas = conferir.conferir_commits(f"{base}..HEAD", raiz=repo)
    assert any("lado.txt: caminho de casos" in p for p in problemas)


def test_envio_olha_so_o_que_nao_esta_no_remoto(repo, tmp_path):
    remoto = tmp_path / "remoto.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remoto)], check=True, env=_ambiente())
    _git(repo, "remote", "add", "origin", str(remoto))
    velho = _commit(repo, "velho.txt", f"{PASTA_CASOS}x\n")
    _git(repo, "push", "-q", "origin", "HEAD:refs/heads/velho")
    linha_velha = f"refs/heads/velho {velho} refs/heads/velho {velho}"
    assert conferir.conferir_envio("origin", [linha_velha], repo) == []

    novo = _commit(repo, "novo.txt", f"{PASTA_CASO}\n")
    linha = f"refs/heads/novo {novo} refs/heads/novo {conferir.ZERO}"
    assert conferir.conferir_envio("origin", [linha], repo) == [
        f"commit {novo[:10]}: novo.txt: pasta de caso"
    ]


def test_envio_de_apagamento_nao_confere(repo):
    linha = f"(delete) {conferir.ZERO} refs/heads/velho {'1' * 40}"
    assert conferir.conferir_envio("origin", [linha, ""], repo) == []


def test_git_falho_barra(repo):
    with pytest.raises(subprocess.CalledProcessError):
        conferir.conferir_arvore("nao-existe", repo)


def test_o_proprio_repositorio_esta_limpo():
    """A conferência e os testes não podem conter o que recusam."""
    for arquivo in (SCRIPT, Path(__file__)):
        assert conferir.achar(arquivo.read_bytes()) == []
