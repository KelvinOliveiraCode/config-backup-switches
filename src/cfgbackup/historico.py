"""Historico de mudancas em Markdown.

Change history in Markdown.

O historico responde a tres perguntas que so o registro responde:

1. **Quem** mudou o que, e quando.
2. **Por que**: a diff fica embutida, entao ninguem precisa abrir o backup.
3. **O que** ja era esperado na epoca, e o que apareceu de surpresa.

O item 3 e o que separa um historico util de um arquivo de log. Um historico
que so registra mudancas inesperadas e um lista de sustos, e nao serve para
auditoria. Um historico que registra **tudo**, com o estado de cada mudanca,
permite responder depois: "essa regra foi declarada por alguem e aprovada?".

A data entra por parametro, nunca por ``datetime.now()``. Um historico com a
hora da execucao muda a cada run, o que quebra o ``git diff`` e transforma o
exemplo versionado em uma fonte de ruido.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .diferenca import (
    ESPERADA,
    INESPERADA,
    SEM_MUDANCA,
    Diff,
)


# Marcadores do arquivo.
TITULO = "# Historico de mudancas de configuracao"
AVISO = (
    "> Documento gerado por `cfgbackup`. As configuracoes sao ficticias:\n"
    "> nenhum equipamento real e acessado."
)


class OperadorVazio(ValueError):
    """O registro foi criado sem dizer quem fez a mudanca."""

    def __init__(self) -> None:
        super().__init__(
            "operador e obrigatorio: um historico sem autor nao responde "
            "a pergunta mais importante do registro"
        )


@dataclass(frozen=True)
class Registro:
    """Uma entrada do historico.

    One history entry.

    Attributes:
        data: Data e hora, no formato ``AAAA-MM-DD HH:MM``.
        operador: Quem executou a coleta.
        equipamento: Hostname comparado.
        diff: Resultado da comparacao.
    """

    data: str
    operador: str
    equipamento: str
    diff: Diff

    @property
    def estado(self) -> str:
        """O estado da comparacao, com rotulo legivel.

        The comparison state, with a readable label.
        """
        return self.diff.estado

    @property
    def rotulo(self) -> str:
        """O estado como aparece no Markdown.

        The state as it appears in Markdown.
        """
        return {
            SEM_MUDANCA: "sem mudanca",
            ESPERADA: "mudanca esperada",
            INESPERADA: "MUDANCA INESPERADA",
        }[self.estado]

    def para_markdown(self) -> str:
        """Renderiza a entrada como secao Markdown.

        Render the entry as a Markdown section.
        """
        d = self.diff
        partes = [
            f"## {self.equipamento} - {self.rotulo}",
            "",
            f"- **data**: {self.data}",
            f"- **operador**: {self.operador}",
            f"- **estado**: `{d.estado}`",
            f"- **mudancas**: {len(d.mudancas)} "
            f"({len(d.esperadas)} esperada(s), {len(d.inesperadas)} inesperada(s))",
            "",
        ]

        if not d.mudancas:
            partes.append(
                "As configuracoes normalizadas sao identicas. "
                "Nenhuma linha sobreviveu a tabela de normalizacao como "
                "diferenca."
            )
            partes.append("")
            return "\n".join(partes)

        partes.append("```diff")
        partes.append(d.texto())
        partes.append("```")
        partes.append("")

        if d.esperadas:
            partes.append("### Mudancas declaradas previamente")
            partes.append("")
            for m in d.esperadas:
                partes.append(f"- {m.resumo()}")
            partes.append("")

        if d.inesperadas:
            partes.append("### Mudancas nao declaradas (drift)")
            partes.append("")
            for m in d.inesperadas:
                partes.append(f"- {m.resumo()}")
            partes.append("")

        return "\n".join(partes)


def cabecalho() -> str:
    """O comeco do arquivo de historico.

    The start of the history file.
    """
    return f"{TITULO}\n\n{AVISO}\n\n---\n"


def registrar(
    caminho: str | Path,
    data: str,
    operador: str,
    diffs: Iterable[Diff],
) -> int:
    """Acrescenta as comparacoes ao historico.

    Append the comparisons to the history.

    Cria o arquivo com o cabecalho se ele ainda nao existir. Um arquivo
    recriado a cada execucao perderia o registro anterior, que e justamente o
    que um historico existe para guardar.

    Args:
        caminho: Caminho do arquivo Markdown.
        data: Data e hora do registro.
        operador: Quem executou.
        diffs: Comparacoes a registrar.

    Returns:
        Quantos registros foram acrescentados.

    Raises:
        OperadorVazio: Se o operador nao for informado.
    """
    if not operador.strip():
        raise OperadorVazio()

    destino = Path(caminho)
    destino.parent.mkdir(parents=True, exist_ok=True)

    novo = not destino.exists()
    with destino.open("a", encoding="utf-8", newline="\n") as fh:
        if novo:
            fh.write(cabecalho())

        # Do mais recente para o mais antigo: quem abre o historico quer o
        # ultimo evento primeiro, nao a serie inteira.
        acrescentados = 0
        for diff in sorted(
            diffs, key=lambda d: d.equipamento, reverse=True
        ):
            fh.write(
                Registro(
                    data=data, operador=operador, equipamento=diff.equipamento, diff=diff
                ).para_markdown()
            )
            fh.write("---\n\n")
            acrescentados += 1

    return acrescentados


def ler(caminho: str | Path) -> str:
    """Le o historico inteiro.

    Read the whole history.
    """
    return Path(caminho).read_text(encoding="utf-8")


def contar_registros(caminho: str | Path) -> int:
    """Conta as secoes de equipamento registradas.

    Count the recorded equipment sections.
    """
    if not Path(caminho).exists():
        return 0
    return sum(
        1 for linha in Path(caminho).read_text(encoding="utf-8").splitlines()
        if linha.startswith("## ")
    )