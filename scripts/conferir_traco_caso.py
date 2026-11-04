"""Recusa traço de caso do gabinete no que vai ao repositório, que é público.

Procura caminhos da pasta de casos do vault e nomes de pasta de caso (sigla da classe, sublinhado e
número) nos caminhos, no conteúdo de texto e nas mensagens de commit. O relatório diz onde achou e
nunca repete o trecho, porque a saída do hook vai parar em terminais e registros.

    conferir_traco_caso.py                 confere o índice (o que o próximo commit grava)
    conferir_traco_caso.py --ref REF       confere a árvore de REF e os commits dele fora do remoto
    conferir_traco_caso.py --envio REMOTO  lê da entrada as linhas do hook pre-push e confere os
                                           commits que ainda não estão em REMOTO

Sai com 0 sem traço, 1 com traço e diferente disso se o git falhar, o que também barra o hook.
Só biblioteca padrão: o hook roda em worktrees de qualquer branch, sem depender do ambiente deles.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

PADROES = {
    "caminho de casos": re.compile(rb"(?<![A-Za-z0-9])(?i:casos)[/\x5c]"),
    "pasta de caso": re.compile(rb"(?<![A-Za-z0-9])(?:APL|AD|ED|AI|HC|EDHC)_[0-9]"),
}
ZERO = "0" * 40
LIMITE_SONDA_BINARIO = 8000


def achar(dados: bytes) -> list[tuple[str, int]]:
    """Cada padrão que casa em `dados`, com a linha (1 em diante) da primeira ocorrência."""
    achados = []
    for nome, padrao in PADROES.items():
        casamento = padrao.search(dados)
        if casamento:
            achados.append((nome, dados.count(b"\n", 0, casamento.start()) + 1))
    return achados


def git(raiz: Path | None, *args: str, entrada: bytes | None = None) -> bytes:
    prefixo = ["git", "-C", str(raiz)] if raiz else ["git"]
    return subprocess.run([*prefixo, *args], input=entrada, capture_output=True, check=True).stdout


def caminho_mascarado(caminho: bytes) -> str:
    """O caminho até o começo do traço; o resto pode trazer número e nome das partes."""
    inicio = min(m.start() for p in PADROES.values() if (m := p.search(caminho)))
    return caminho[:inicio].decode("utf-8", "backslashreplace") + "<traço>"


def _conferir_blobs(raiz: Path | None, itens: list[tuple[bytes, str]]) -> list[str]:
    """Confere caminhos e conteúdos de pares (caminho, sha do blob), lidos de uma vez só."""
    problemas = []
    for caminho, _ in itens:
        if any(p.search(caminho) for p in PADROES.values()):
            problemas.append(f"{caminho_mascarado(caminho)}: traço no nome do arquivo")
    saida = git(raiz, "cat-file", "--batch", entrada="".join(f"{s}\n" for _, s in itens).encode())
    posicao = 0
    for caminho, _ in itens:
        fim_cabecalho = saida.index(b"\n", posicao)
        tamanho = int(saida[posicao:fim_cabecalho].split()[2])
        dados = saida[fim_cabecalho + 1 : fim_cabecalho + 1 + tamanho]
        posicao = fim_cabecalho + 1 + tamanho + 1
        if b"\0" in dados[:LIMITE_SONDA_BINARIO]:
            continue
        rotulo = caminho.decode("utf-8", "backslashreplace")
        problemas.extend(f"{rotulo}:{linha}: {nome}" for nome, linha in achar(dados))
    return problemas


def _sem_submodulos(linhas: list[bytes]) -> list[tuple[bytes, str]]:
    itens = []
    for linha in linhas:
        cabecalho, caminho = linha.split(b"\t", 1)
        modo, *resto = cabecalho.split()
        if modo != b"160000":
            sha = next(campo for campo in resto if len(campo) >= 40)
            itens.append((caminho, sha.decode()))
    return itens


def conferir_indice(raiz: Path | None = None) -> list[str]:
    return _conferir_blobs(raiz, _sem_submodulos(git(raiz, "ls-files", "-s", "-z").split(b"\0")[:-1]))


def conferir_arvore(ref: str, raiz: Path | None = None) -> list[str]:
    linhas = git(raiz, "ls-tree", "-r", "-z", ref).split(b"\0")[:-1]
    return [f"{ref}: {p}" for p in _conferir_blobs(raiz, _sem_submodulos(linhas))]


def _conferir_diff(curto: str, diff: bytes) -> list[str]:
    """Só linhas e caminhos acrescentados: tirar o traço de um arquivo não pode ser recusado."""
    problemas = []
    for secao in re.split(rb"^diff --git ", diff, flags=re.MULTILINE)[1:]:
        cabecalho, _, corpo = secao.partition(b"\n")
        if corpo.startswith(b"deleted file mode"):
            continue
        # `a/P b/P`, com --no-renames: a segunda metade é o caminho, mesmo em arquivo vazio ou binário.
        caminho = cabecalho[(len(cabecalho) + 1) // 2 :].strip(b'"')[2:]
        rotulo = caminho.decode("utf-8", "backslashreplace")
        if any(p.search(caminho) for p in PADROES.values()):
            rotulo = caminho_mascarado(caminho)
            problemas.append(f"commit {curto}: {rotulo}: traço no nome do arquivo")
        for linha in corpo.split(b"\n"):
            if linha.startswith(b"+") and not linha.startswith((b"+++ b/", b'+++ "b/')):
                problemas.extend(f"commit {curto}: {rotulo}: {nome}" for nome, _ in achar(linha))
    return list(dict.fromkeys(problemas))


def conferir_commits(*selecao: str, raiz: Path | None = None) -> list[str]:
    """Mensagem e acréscimos de cada commit da seleção, que usa a sintaxe de `git log`."""
    saida = git(
        raiz,
        "log",
        "--format=%x00%H%x00%B%x00",
        "-p",
        "-U0",
        "--no-color",
        "--no-ext-diff",
        "--no-textconv",
        "--no-renames",
        "--diff-merges=first-parent",
        *selecao,
        "--",
    )
    partes = saida.split(b"\0")
    problemas = []
    for indice in range(1, len(partes) - 2, 3):
        curto = partes[indice][:10].decode()
        problemas.extend(f"commit {curto}: mensagem: {nome}" for nome, _ in achar(partes[indice + 1]))
        problemas.extend(_conferir_diff(curto, partes[indice + 2]))
    return problemas


def conferir_envio(remoto: str, linhas: list[str], raiz: Path | None = None) -> list[str]:
    """Linhas do pre-push: `ref-local sha-local ref-remota sha-remoto`."""
    problemas = []
    for linha in linhas:
        if not linha.strip():
            continue
        _, sha_local, _, _ = linha.split()
        if sha_local != ZERO:
            problemas.extend(conferir_commits(sha_local, "--not", f"--remotes={remoto}", raiz=raiz))
    return list(dict.fromkeys(problemas))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--ref", help="Confere a árvore de REF e os commits dele fora de origin")
    parser.add_argument("--envio", metavar="REMOTO", help="Modo do hook pre-push; lê as linhas da entrada")
    args = parser.parse_args()
    if args.envio:
        problemas = conferir_envio(args.envio, sys.stdin.read().splitlines())
    elif args.ref:
        problemas = conferir_arvore(args.ref) + conferir_commits(args.ref, "--not", "--remotes=origin")
    else:
        problemas = conferir_indice()
    if problemas:
        print("Conferência de traço de caso: RECUSADO. O repositório é público; retire antes de seguir.")
        print("\n".join(f"  {p}" for p in problemas))
        return 1
    print("Conferência de traço de caso: nada encontrado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
