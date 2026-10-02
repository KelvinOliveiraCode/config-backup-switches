"""Diff entre duas configuracoes e classificacao da mudanca.

Diff between two configurations, and classification of the change.

A diferenca contra um backup anterior tem **tres** estados, e a distincao e o
ponto inteiro do modulo:

| Estado | Significado | Alerta |
|--------|-------------|--------|
| sem mudanca | as configuracoes normalizadas sao iguais | nao |
| esperada | a mudanca foi declarada antes de acontecer | nao |
| inesperada | alguem mexeu fora do processo | **sim** |

Sem o estado do meio, todo alerta de configuracao vira alarme. A primeira vez
que alguem adiciona uma rota planejada, o sistema avisa; da segunda vez, o
equipe silencia o alerta - e nao porque o problema sumiu, mas porque o alerta
parou de significar alguma coisa. Por isso a mudanca esperada e declarada, com
motivo e prazo, e por isso ela nao alerta.

O estado **inesperado** e drift: configuracao que mudou sem ninguem ter
anunciado.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Iterable


SEM_MUDANCA = "sem_mudanca"
ESPERADA = "esperada"
INESPERADA = "inesperada"


class MudancaEsperada:
    """Uma mudanca declarada previamente.

    A change declared in advance.

    Attributes:
        padrao: Expressao regular que casa com a linha afetada.
        motivo: Por que a mudanca era esperada.
        autor: QuemPidiu.
        ate: Data limite da janela de mudanca, no formato ``AAAA-MM-DD``.
    """

    def __init__(
        self,
        padrao: str,
        motivo: str,
        autor: str = "desconhecido",
        ate: str | None = None,
    ) -> None:
        self.padrao = padrao
        self.motivo = motivo
        self.autor = autor
        self.ate = ate
        self._compilado = re.compile(padrao)

    def casa(self, *linhas: str | None) -> bool:
        """Diz se a mudanca casa com a declaracao.

        Whether the change matches the declaration.

        Args:
            *linhas: Linhas envolvidas na mudanca (antes, depois, ou ambas).

        Returns:
            Verdadeiro se alguma das linhas casar com o padrao.
        """
        return any(linha is not None and self._compilado.search(linha) for linha in linhas)

    def para_dict(self) -> dict[str, str | None]:
        """Serializa a declaracao.

        Serialize the declaration.
        """
        return {
            "padrao": self.padrao,
            "motivo": self.motivo,
            "autor": self.autor,
            "ate": self.ate,
        }


@dataclass(frozen=True)
class Mudanca:
    """Uma linha que mudou entre as duas configuracoes.

    A single changed line between the two configurations.

    Attributes:
        tipo: ``adicionada``, ``removida`` ou ``substituida``.
        antes: Conteudo anterior, ou ``None`` se foi adicionada.
        depois: Conteudo novo, ou ``None`` se foi removida.
        estado: Um dos tres estados deste modulo.
        motivo: Motivo declarado, quando o estado e ``esperada``.
    """

    tipo: str
    antes: str | None
    depois: str | None
    estado: str = INESPERADA
    motivo: str | None = None

    @property
    def esperada(self) -> bool:
        """A mudanca foi declarada antes.

        Whether the change was declared in advance.
        """
        return self.estado == ESPERADA

    @property
    def alerta(self) -> bool:
        """A mudanca deve gerar alerta.

        Whether the change should raise an alert.
        """
        return self.estado == INESPERADA

    def resumo(self) -> str:
        """Uma linha legivel sobre a mudanca.

        A readable one-liner about the change.
        """
        marca = {"adicionada": "+", "removida": "-", "substituida": "~"}[self.tipo]
        if self.tipo == "substituida":
            return f"{marca} {self.antes.strip()}  ->  {self.depois.strip()}"
        alvo = (self.depois if self.depois is not None else self.antes) or ""
        sufixo = f"  (esperada: {self.motivo})" if self.motivo else ""
        return f"{marca} {alvo.strip()}{sufixo}"


@dataclass(frozen=True)
class Diff:
    """O resultado da comparacao de um equipamento.

    The comparison result for one device.

    Attributes:
        equipamento: Hostname comparado.
        mudancas: Todas as linhas que mudaram.
    """

    equipamento: str
    mudancas: tuple[Mudanca, ...] = ()

    @property
    def estado(self) -> str:
        """O estado geral, o pior entre as mudancas.

        The overall state, the worst among the changes.
        """
        if not self.mudancas:
            return SEM_MUDANCA
        if any(m.alerta for m in self.mudancas):
            return INESPERADA
        return ESPERADA

    @property
    def alerta(self) -> bool:
        """A comparacao exige atencao.

        Whether the comparison demands attention.
        """
        return self.estado == INESPERADA

    @property
    def inesperadas(self) -> tuple[Mudanca, ...]:
        """So as mudancas nao declaradas.

        Only the undeclared changes.
        """
        return tuple(m for m in self.mudancas if m.alerta)

    @property
    def esperadas(self) -> tuple[Mudanca, ...]:
        """So as mudancas declaradas.

        Only the declared changes.
        """
        return tuple(m for m in self.mudancas if m.esperada)

    def texto(self) -> str:
        """Renderiza a diff em formato unified.

        Render the diff in unified format.
        """
        if not self.mudancas:
            return "sem mudancas"

        antes = [m.antes for m in self.mudancas if m.antes is not None]
        depois = [m.depois for m in self.mudancas if m.depois is not None]

        linhas = difflib.unified_diff(
            antes,
            depois,
            fromfile=f"{self.equipamento} (anterior)",
            tofile=f"{self.equipamento} (atual)",
            lineterm="",
            n=0,
        )
        return "\n".join(linhas)

    def para_dict(self) -> dict[str, object]:
        """Serializa o resultado.

        Serialize the result.
        """
        return {
            "equipamento": self.equipamento,
            "estado": self.estado,
            "alerta": self.alerta,
            "total_mudancas": len(self.mudancas),
            "inesperadas": len(self.inesperadas),
            "esperadas": len(self.esperadas),
            "mudancas": [
                {
                    "tipo": m.tipo,
                    "antes": m.antes,
                    "depois": m.depois,
                    "estado": m.estado,
                    "motivo": m.motivo,
                }
                for m in self.mudancas
            ],
        }


def _linhas(texto: str) -> list[str]:
    """Quebra um texto em linhas sem marcas de tempo.

    Split text into lines without timestamps.
    """
    return [linha for linha in texto.splitlines() if linha.strip()]


def comparar(
    equipamento: str,
    anterior: str,
    atual: str,
    esperadas: Iterable[MudancaEsperada] = (),
) -> Diff:
    """Compara duas configuracoes ja normalizadas.

    Compare two already-normalized configurations.

    O emparelhamento usa :class:`difflib.SequenceMatcher`, que agrupa blocos
    de linhasiguais e reporta o resto como remocao mais insercao. Uma linha
    alterada aparece como duas mudancas (removida e adicionada) em vez de uma
    substituicao, o que e ruido: o relatorio mostraria dez alteracoes para
    cinco mudancas reais. Por isso pares ``removida``/``adicionada`` com o
    mesmo conteudo normalizado sao fundidos em ``substituida``.

    Args:
        equipamento: Hostname comparado.
        anterior: Configuracao anterior, normalizada.
        atual: Configuracao atual, normalizada.
        esperadas: Mudancas declaradas previamente.

    Returns:
        O resultado da comparacao.
    """
    declaradas = list(esperadas)
    antes = _linhas(anterior)
    depois = _linhas(atual)

    brutas: list[Mudanca] = []
    casador = difflib.SequenceMatcher(a=antes, b=depois, autojunk=False)

    for tag, i1, i2, j1, j2 in casador.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            # Emparelha por posicao: o que sobrar e insercao ou remocao pura.
            pares = min(i2 - i1, j2 - j1)
            for k in range(pares):
                brutas.append(Mudanca("substituida", antes[i1 + k], depois[j1 + k]))
            for k in range(pares, i2 - i1):
                brutas.append(Mudanca("removida", antes[i1 + k], None))
            for k in range(pares, j2 - j1):
                brutas.append(Mudanca("adicionada", None, depois[j1 + k]))
        elif tag == "delete":
            for k in range(i1, i2):
                brutas.append(Mudanca("removida", antes[k], None))
        elif tag == "insert":
            for k in range(j1, j2):
                brutas.append(Mudanca("adicionada", None, depois[k]))

    classificadas: list[Mudanca] = []
    for mudanca in brutas:
        declarada = next(
            (d for d in declaradas if d.casa(mudanca.antes, mudanca.depois)), None
        )
        classificadas.append(
            Mudanca(
                tipo=mudanca.tipo,
                antes=mudanca.antes,
                depois=mudanca.depois,
                estado=ESPERADA if declarada else INESPERADA,
                motivo=declarada.motivo if declarada else None,
            )
        )

    return Diff(equipamento, tuple(classificadas))