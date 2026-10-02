"""Verificacao de encoding do repositorio cfgbackup.

Encoding gate for the cfgbackup repository.

Codigo, dado e configuracao em ASCII puro: um acento em ``.py`` e um risco
operacional no Windows sem ganho nenhum. Documentacao em Markdown aceita
acentos PT-BR e matematica, porque ela existe para ser lida em portugues.
CJK e o caractere de substituicao continuam proibidos em qualquer arquivo.

Exit code 0 = tudo limpo.
"""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

ASCII_PURO = {".py", ".json", ".yaml", ".yml", ".toml", ".cfg", ".txt"}
DOCUMENTACAO = {".md"}
BINARIOS = {".png", ".ico", ".jpg", ".jpeg", ".gif"}
IGNORADOS = {".git", "__pycache__", ".pytest_cache", ".venv", "venv", "htmlcov", "saida"}

# Matematica, pontuacao tipografica e as arvores de diretorio dos READMEs.
PERMITIDOS_MD = set(
    "\u00b0\u00b2\u00b3\u00ba"
    "\u00d7\u2212\u2248"
    "\u2264\u2265\u2260"
    "\u2013\u2014"
    "\u2018\u2019\u201c\u201d"
    "\u2026"
) | {chr(c) for c in range(0x2500, 0x2580)}


def classificar(caminho: Path) -> str:
    """Diz qual regra se aplica ao arquivo.

    Args:
        caminho: Caminho do arquivo.

    Returns:
        ``ascii``, ``markdown``, ``ignorado`` ou ``sem_regra``.
    """
    ext = caminho.suffix.lower()
    if ext in ASCII_PURO:
        return "ascii"
    if ext in DOCUMENTACAO:
        return "markdown"
    if ext in BINARIOS:
        return "ignorado"
    return "sem_regra"


def auditar(caminho: Path) -> list[str]:
    """Lista os problemas de encoding de um arquivo.

    Args:
        caminho: Caminho do arquivo.

    Returns:
        Lista de descricoes, vazia se o arquivo estiver limpo.
    """
    modo = classificar(caminho)
    if modo in ("ignorado", "sem_regra"):
        return []

    texto = caminho.read_text(encoding="utf-8", errors="replace")
    problemas: list[str] = []

    if "\ufffd" in texto:
        problemas.append("contem U+FFFD, o caractere de substituicao")

    for numero, linha in enumerate(texto.splitlines(), 1):
        for coluna, caractere in enumerate(linha, 1):
            ponto = ord(caractere)
            if ponto < 128:
                continue

            nome = unicodedata.name(caractere, "U+%04X" % ponto)

            if 0x3000 <= ponto <= 0x9FFF or 0xAC00 <= ponto <= 0xD7AF:
                problemas.append(f"linha {numero}, coluna {coluna}: CJK U+{ponto:04X}")
                continue

            if modo == "ascii":
                problemas.append(f"linha {numero}, coluna {coluna}: {nome} em codigo")
                continue

            if caractere in PERMITIDOS_MD:
                continue

            if 0xC0 <= ponto <= 0x17F:
                continue

            problemas.append(
                f"linha {numero}, coluna {coluna}: {nome} nao permitido em Markdown"
            )

    return problemas


def main() -> int:
    """Percorre o repositorio e reporta.

    Returns:
        0 se todos os arquivos estiverem limpos, 1 caso contrario.
    """
    problemas: list[str] = []
    auditados = 0

    for caminho in sorted(RAIZ.rglob("*")):
        if not caminho.is_file():
            continue
        if any(parte in IGNORADOS for parte in caminho.parts):
            continue
        modo = classificar(caminho)
        if modo in ("ignorado", "sem_regra"):
            continue

        auditados += 1
        achados = auditar(caminho)
        if achados:
            problemas.append(f"{caminho.relative_to(RAIZ)}: {len(achados)} ocorrencia(s)")
            problemas.extend(f"    {a}" for a in achados[:6])

    if problemas:
        print("encoding FALHOU:")
        print("\n".join(problemas))
        return 1

    print(
        f"encoding ok: {auditados} arquivo(s), nenhum U+FFFD, nenhum CJK, "
        "nenhum caractere nao-ASCII em codigo ou dado"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())