"""Vetoriza o corpus e as consultas do conjunto com um modelo: <nome>-docs.npy e <nome>-consultas.json.

Vetores normalizados (produto interno = cosseno), float16, na ordem de corpus-meta.json. Backends:
  st        sentence-transformers na GPU (modelos de ate cerca de 1,5 bilhao de parametros em fp16)
  gguf      llama-cpp-python com CUDA (4 a 8 bilhoes quantizados; o mesmo arquivo serve a CPU depois)
  servidor  llama-server do llama.cpp ja aberto com --embedding --pooling last; --modelo e a URL base
            (no Windows o llama-cpp-python com CUDA pre-compilado nao le Qwen3)
  voyage    API da Voyage AI (chave em VOYAGE_API_KEY; use o perfil nenhum, o input_type faz o papel do
            prefixo); o texto sai da maquina, so para o teste com ementas publicas autorizado na R5
  aleatorio vetores por hash, so para ensaiar o encanamento do kit sem modelo

Perfis de instrucao (o que vai antes da consulta e do documento):
  qwen3   consulta "Instruct: <tarefa>\\nQuery:<texto>", documento sem prefixo (Qwen3-Embedding e JUA)
  gemma   consulta "task: search result | query: <texto>", documento "title: none | text: <texto>"
  e5      consulta "query: <texto>", documento "passage: <texto>" (multilingual-e5)
  nenhum  sem prefixo

Uso: python indexar.py --corpus <pasta> --conjunto <conjunto.json> --nome <rotulo> --backend st
       --modelo <id HF> [--perfil qwen3] [--tarefa "..."] [--max-caracteres 6000] [--lote 16]
       [--so-consultas]
"""

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

from comum import gravar_json, ler_json

TAREFA = "Dada uma questão jurídica, recupere ementas de acórdãos brasileiros que a decidem"
PERFIS = {
    "qwen3": (lambda q, t: f"Instruct: {t}\nQuery:{q}", lambda d: d),
    "gemma": (lambda q, t: f"task: search result | query: {q}", lambda d: f"title: none | text: {d}"),
    "e5": (lambda q, t: f"query: {q}", lambda d: f"passage: {d}"),
    "nenhum": (lambda q, t: q, lambda d: d),
}


def normalizar(m):
    m = np.asarray(m, dtype=np.float32)
    return m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-12)


class Aleatorio:
    def __init__(self, dim):
        self.dim = dim

    def __call__(self, textos):
        out = []
        for t in textos:
            semente = int.from_bytes(hashlib.sha256(t.encode()).digest()[:8], "little")
            out.append(np.random.default_rng(semente).standard_normal(self.dim))
        return normalizar(out)


class SentenceTransformers:
    def __init__(self, modelo, lote):
        from sentence_transformers import SentenceTransformer

        self.m = SentenceTransformer(modelo, device="cuda", model_kwargs={"torch_dtype": "float16"})
        self.lote = lote

    def __call__(self, textos):
        return normalizar(self.m.encode(textos, batch_size=self.lote, normalize_embeddings=True))


class Gguf:
    def __init__(self, arquivo, lote):
        from llama_cpp import Llama

        # Qwen3-Embedding usa o ultimo token (pooling LAST); confira no cartao do modelo GGUF usado.
        self.m = Llama(
            model_path=arquivo,
            embedding=True,
            n_gpu_layers=-1,
            n_ctx=8192,
            n_batch=2048,
            pooling_type=3,
            verbose=False,
        )
        self.lote = lote

    def __call__(self, textos):
        return normalizar([self.m.embed(t) for t in textos])


class Servidor:
    def __init__(self, url, lote):
        self.url = url.rstrip("/") + "/v1/embeddings"
        self.lote = lote

    def __call__(self, textos):
        out = []
        for n in range(0, len(textos), self.lote):
            corpo = json.dumps({"input": textos[n : n + self.lote]}).encode()
            pedido = urllib.request.Request(self.url, corpo, {"Content-Type": "application/json"})
            with urllib.request.urlopen(pedido, timeout=600) as r:
                dados = sorted(json.load(r)["data"], key=lambda d: d["index"])
            out += [d["embedding"] for d in dados]
        return normalizar(out)


class Voyage:
    URL = "https://api.voyageai.com/v1/embeddings"

    def __init__(self, modelo, lote):
        self.modelo, self.lote = modelo, lote
        self.chave = os.environ["VOYAGE_API_KEY"]
        self.tipo = "document"
        self.tokens = 0

    def pedir(self, textos):
        corpo = json.dumps({"input": textos, "model": self.modelo, "input_type": self.tipo}).encode()
        cabecalho = {"Content-Type": "application/json", "Authorization": f"Bearer {self.chave}"}
        for tentativa in range(8):
            try:
                with urllib.request.urlopen(
                    urllib.request.Request(self.URL, corpo, cabecalho), timeout=300
                ) as r:
                    resposta = json.load(r)
                self.tokens += resposta["usage"]["total_tokens"]
                return [d["embedding"] for d in sorted(resposta["data"], key=lambda d: d["index"])]
            except urllib.error.HTTPError as e:
                if e.code != 429 and e.code < 500 or tentativa == 7:
                    raise
                time.sleep(2**tentativa)
        return None

    def __call__(self, textos):
        out = []
        for n in range(0, len(textos), self.lote):
            out += self.pedir(textos[n : n + self.lote])
        return normalizar(out)


def em_lotes(codificar, textos, lote, rotulo):
    ordem = sorted(range(len(textos)), key=lambda i: len(textos[i]))  # comprimentos parecidos por lote
    saida = [None] * len(textos)
    inicio = time.time()
    for n in range(0, len(ordem), lote * 32):
        bloco = ordem[n : n + lote * 32]
        for i, v in zip(bloco, codificar([textos[i] for i in bloco]), strict=True):
            saida[i] = v
        feito = min(n + lote * 32, len(ordem))
        taxa = feito / max(time.time() - inicio, 1e-6)
        faltam = (len(ordem) - feito) / taxa / 60
        print(f"{rotulo}: {feito}/{len(ordem)} ({taxa:.1f}/s, faltam {faltam:.1f} min)", flush=True)
    return np.stack(saida)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--corpus", required=True)
    a.add_argument("--conjunto", required=True)
    a.add_argument("--nome", required=True)
    a.add_argument("--backend", choices=("st", "gguf", "servidor", "voyage", "aleatorio"), required=True)
    a.add_argument(
        "--modelo", help="id do Hugging Face (st), caminho do .gguf (gguf), URL (servidor) ou modelo (voyage)"
    )
    a.add_argument("--perfil", choices=tuple(PERFIS), default="qwen3")
    a.add_argument("--tarefa", default=TAREFA, help="instrucao da consulta no perfil qwen3")
    a.add_argument("--max-caracteres", type=int, default=6000)
    a.add_argument("--lote", type=int, default=16)
    a.add_argument("--dim", type=int, default=64, help="so para o backend aleatorio")
    a.add_argument("--so-consultas", action="store_true")
    args = a.parse_args()
    corpus = Path(args.corpus)
    meta = ler_json(corpus / "corpus-meta.json")
    conjunto = ler_json(args.conjunto)
    codificar = {
        "aleatorio": lambda: Aleatorio(args.dim),
        "st": lambda: SentenceTransformers(args.modelo, args.lote),
        "gguf": lambda: Gguf(args.modelo, args.lote),
        "servidor": lambda: Servidor(args.modelo, args.lote),
        "voyage": lambda: Voyage(args.modelo, args.lote),
    }[args.backend]()
    consulta, documento = PERFIS[args.perfil]
    inicio = time.time()
    if not args.so_consultas:
        textos, ids = [], []
        with open(corpus / "corpus-textos.jsonl", encoding="utf-8") as f:
            for linha in f:
                d = json.loads(linha)
                ids.append(d["id"])
                textos.append(documento(d["texto"][: args.max_caracteres]))
        assert ids == [m["id"] for m in meta["itens"]], "corpus-textos fora da ordem de corpus-meta"
        docs = em_lotes(codificar, textos, args.lote, "documentos")
        np.save(corpus / f"{args.nome}-docs.npy", docs.astype(np.float16))
    tempo_docs = round(time.time() - inicio, 1)
    chaves, textos = [], []
    for p in conjunto["perguntas"]:
        for f in conjunto["formulacoes"]:
            if p.get(f):
                chaves.append([p["id"], f])
                textos.append(consulta(p[f], args.tarefa))
    if isinstance(codificar, Voyage):
        codificar.tipo = "query"
    t0 = time.time()
    q = em_lotes(codificar, textos, args.lote, "consultas")
    por_consulta_ms = round((time.time() - t0) / max(len(textos), 1) * 1000, 1)
    gravar_json(
        corpus / f"{args.nome}-consultas.json",
        {
            "nome": args.nome,
            "backend": args.backend,
            "modelo": args.modelo,
            "perfil": args.perfil,
            "tarefa": args.tarefa if args.perfil == "qwen3" else None,
            "max_caracteres": args.max_caracteres,
            "publicacao": meta["publicacao"],
            "dim": int(q.shape[1]),
            "segundos_documentos": tempo_docs,
            "ms_por_consulta_em_lote": por_consulta_ms,
            "tokens_api": getattr(codificar, "tokens", None),
            "chaves": chaves,
            "vetores": q.astype(np.float32).round(6).tolist(),
        },
    )
    print(
        f"pronto: {args.nome}, dim {q.shape[1]}, documentos em {tempo_docs} s, {por_consulta_ms} ms/consulta"
    )


if __name__ == "__main__":
    main()
