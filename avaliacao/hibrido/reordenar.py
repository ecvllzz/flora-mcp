"""Notas de reordenacao para os 30 primeiros de cada lista exportada por avaliar_hibrido.py --exportar-pares.

Backends:
  qwen3  Qwen3-Reranker (0.6B em fp16; 4B pede 8 GB e pode nao caber), formato do cartao do modelo
  cross  sentence-transformers CrossEncoder (por exemplo BAAI/bge-reranker-v2-m3)
Confira o formato do qwen3 contra o cartao do modelo baixado antes de confiar no resultado.

Uso: python reordenar.py --pares pares.json --saida rr.json --backend qwen3 --modelo Qwen/Qwen3-Reranker-0.6B
"""

import argparse
import time

from comum import gravar_json, ler_json

TAREFA = "Dada uma questão jurídica, diga se a ementa do acórdão decide essa questão"
PREFIXO = (
    "<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and "
    'the Instruct provided. Note that the answer can only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
)
SUFIXO = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"


def qwen3(modelo, lote):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(modelo, padding_side="left")
    m = AutoModelForCausalLM.from_pretrained(modelo, torch_dtype=torch.float16).cuda().eval()
    sim, nao = tok.convert_tokens_to_ids("yes"), tok.convert_tokens_to_ids("no")

    def notas(consulta, textos):
        out = []
        for n in range(0, len(textos), lote):
            entradas = [
                f"{PREFIXO}<Instruct>: {TAREFA}\n<Query>: {consulta}\n<Document>: {t}{SUFIXO}"
                for t in textos[n : n + lote]
            ]
            enc = tok(entradas, padding=True, truncation=True, max_length=2048, return_tensors="pt").to(
                "cuda"
            )
            with torch.no_grad():
                logits = m(**enc).logits[:, -1, :]
            par = torch.stack([logits[:, nao], logits[:, sim]], dim=1).float()
            out += torch.nn.functional.log_softmax(par, dim=1)[:, 1].exp().tolist()
        return out

    return notas


def cross(modelo, lote):
    from sentence_transformers import CrossEncoder

    m = CrossEncoder(modelo, device="cuda", max_length=1024)
    return lambda consulta, textos: m.predict([(consulta, t) for t in textos], batch_size=lote).tolist()


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--pares", required=True)
    a.add_argument("--saida", required=True)
    a.add_argument("--backend", choices=("qwen3", "cross"), required=True)
    a.add_argument("--modelo", required=True)
    a.add_argument("--lote", type=int, default=8)
    args = a.parse_args()
    notas = {"qwen3": qwen3, "cross": cross}[args.backend](args.modelo, args.lote)
    saida, inicio = {}, time.time()
    pares = ler_json(args.pares)
    for n, item in enumerate(pares, 1):
        docs = item["documentos"]
        saida[item["chave"]] = dict(
            zip([d["id"] for d in docs], notas(item["consulta"], [d["texto"] for d in docs]), strict=True)
        )
        if n % 20 == 0:
            print(f"{n}/{len(pares)} listas, {(time.time() - inicio) / n:.1f} s por lista", flush=True)
    gravar_json(args.saida, saida)
    print(
        "pronto:", len(saida), "listas;", round((time.time() - inicio) / max(len(pares), 1), 2), "s por lista"
    )


if __name__ == "__main__":
    main()
