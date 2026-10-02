"""Confere que o doc descreve a tabela real: nomes, acoes, padroes e secoes."""

import pathlib
import re
import sys

sys.path.insert(0, "src")

from cfgbackup.normalizador import REGRAS_PADRAO

ERROS: list[str] = []


def conferir_doc(doc_path: str, rotulo: str) -> None:
    texto = pathlib.Path(doc_path).read_text(encoding="utf-8")

    linhas = re.findall(r"^\| `([a-z-]+)` \| (remover|substituir) \|", texto, re.M)
    tabela = [(r.nome, r.acao) for r in REGRAS_PADRAO]

    if linhas != tabela:
        ERROS.append(f"{rotulo}: tabela divergente")
        ERROS.append(f"  so no doc : {sorted(set(linhas) - set(tabela))}")
        ERROS.append(f"  so no cod : {sorted(set(tabela) - set(linhas))}")
        if set(linhas) == set(tabela):
            ERROS.append("  a ordem difere da tabela do codigo")

    secoes = re.findall(r"^## `([a-z-]+)`", texto, re.M)
    faltando = [n for n, _ in tabela if n not in secoes]
    if faltando:
        ERROS.append(f"{rotulo}: sem secao para {faltando}")

    for regra in REGRAS_PADRAO:
        if regra.padrao not in texto:
            ERROS.append(
                f"{rotulo}: padrao de {regra.nome} nao aparece literalmente\n"
                f"  codigo: {regra.padrao}"
            )


conferir_doc("docs/o-que-nao-comparar.md", "o-que-nao-comparar")

if ERROS:
    print("doc divergente da tabela:")
    for e in ERROS:
        print("  -", e)
    raise SystemExit(1)

print(f"ok: o doc descreve as {len(REGRAS_PADRAO)} regras, na ordem do codigo")