from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


# Acoespossiveis de uma regra.
REMOVER = "remover"
SUBSTITUIR = "substituir"
PRESERVAR = "preservar"


@dataclass(frozen=True)


class Regra:
    """Uma regra de normalizacao, com o motivo pelo qual ela existe.

    A single normalization rule, with the reason it exists.

    Attributes:
        nome: Identificador estavel da regra, usado no relatorio.
        padrao: Expressao regular que casa com a linha a tratar.
        acao: ``remover``, ``substituir`` ou ``preservar``.
        motivo: Por que a linha nao deve entrar na comparacao.
        substituicao: Texto que substitui a linha, quando ``acao`` e
            ``substituir``. Um grupo nomeado ``valor`` e substituido por este
            texto.
    """

    nome: str
    padrao: str
    acao: str
    motivo: str
    substituicao: str | None = None

    def compila(self) -> re.Pattern[str]:
        """Devolve o padrao compilado.

        Return the compiled pattern.
        """
        return re.compile(self.padrao)


def _r(
    nome: str,
    padrao: str,
    acao: str,
    motivo: str,
    substituicao: str | None = None,
) -> Regra:
    """Atalho para construir uma regra.

    Shortcut to build a rule.
    """
    return Regra(nome, padrao, acao, motivo, substituicao)


#: Tabela de regras padrao. A ordem importa: as primeiras regras sao as mais
#: especificas, porque uma regra geral demais captura linhas que deviam ser
#: preservadas.
REGRAS_PADRAO: tuple[Regra, ...] = (
    _r(
        "data-ultima-mudanca",
        r"^!Last configuration change at .*$",
        REMOVER,
        "O equipamento carimba a hora da ultima mudanca a cada gravacao. "
        "Duas coletas da mesma configuracao tem horarios diferentes.",
    ),
    _r(
        "data-nvram",
        r"^!NVRAM config last updated at .*$",
        REMOVER,
        "Mesma razao da data de mudanca: marca de tempo do aparelho, nao "
        "configuracao.",
    ),
    _r(
        "comentario-de-marcacao",
        r"^!.*configuration (from )?flash.*$",
        REMOVER,
        "Aponta de qual arquivo a configuracao veio. Um backup no git e outro "
        "no repositorio do equipamento sao o mesmo estado.",
    ),
    _r(
        "versao-do-sistema",
        r"^!Software Version .*$",
        REMOVER,
        "A versao so muda quando ha atualizacao de firmware, que e mudanca "
        "planejada e verificada por outro processo. Se o conteudo das linhas "
        "iguais, a diferenca de texto nao informa nada.",
    ),
    _r(
        "uptime",
        r"^(\s*)(?:!(?:SNMP agent )?[Uu]ptime is |Uptime: )(.*)$",
        SUBSTITUIR,
        "O uptime avanca a cada segundo. Comparar texto de uptime produz "
        "mudanca em toda coleta, sempre.",
        substituicao=r"\1<UPTIME NORMALIZADO>",
    ),
    _r(
        "tempo-de-relogio",
        r"^(\s*)(Time source is ).*$",
        SUBSTITUIR,
        "A origem do relogio muda com a topologia de NTP. E estado do "
        "ambiente, nao da configuracao.",
        substituicao=r"\1\2<ORIGEM NORMALIZADA>",
    ),
    _r(
        "numero-de-serie",
        r"^(\s*)(serial (\w+) )(\S+).*$",
        SUBSTITUIR,
        "O numero de serie identifica o aparelho fisico. Dois backups do mesmo "
        "equipamento tem o mesmo serie - mas o equivalente de outro aparelho "
        "tem outro. E a linha que mais aparece em falso positivo quando a "
        "coleta troca de unidade sem o registro ser atualizado.",
        substituicao=r"\1\2<APARELHO>\3<SERIE NORMALIZADA>",
    ),
    _r(
        "endereco-mac-base",
        r"\b(?:[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}|[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2})\.[0-9a-fA-F]{2}(?:[0-9a-fA-F]{2}|[0-9a-fA-F]{2}:[0-9a-fA-F]{2})\b",
        SUBSTITUIR,
        "Os tres primeiros octetos do MAC identificam o fabricante. Os tres "
        "ultimos identificam a interface, que muda com o slot fisico. "
        "Comparar o endereco inteiro acusa troca de porta como mudanca de "
        "configuracao.",
        substituicao=r"\1.<INTERFACE NORMALIZADA>",
    ),
    _r(
        "contador-de-pacotes",
        r"^(\s*)(.*?)(\d+ packets input.*|\d+ packets output.*|\d+ bytes.*)$",
        SUBSTITUIR,
        "Contadores de trafego sobem a cada pacote. Um `show running-config` "
        "nao deveria conter contadores; quando contem, veio de `show tech` ou "
        "de um template que os interpolateou.",
        substituicao=r"\1\2<CONTADOR NORMALIZADO>",
    ),
    _r(
        "memoria",
        r"^(\s*)(.*?)(Free Memory|Used Memory|Total Memory).*$",
        SUBSTITUIR,
        "A quantidade de memoria disponivel muda com qualquer coisa. Nao e "
        "configuracao.",
        substituicao=r"\1\2\3: <MEMORIA NORMALIZADA>",
    ),
    _r(
        "buffer-de-log",
        r"^(\s*)(logging buffer: .*lines logged )(\d+).*$",
        SUBSTITUIR,
        "A contagem de linhas do buffer de log so cresce. Comparar ela faz "
        "toda alerta parecer mudanca de regra de log.",
        substituicao=r"\1\2<CONTADOR NORMALIZADO>",
    ),
    _r(
        "entrada-da-tabela-mac",
        r"^\s+\d+\s+"
        r"(?:[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}"
        r"|(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2})"
        r"\s+.*$",
        SUBSTITUIR,
        "A tabela MAC e estado operacional aprendido, nao configuracao: e "
        "montada pelo switch a partir de quem conversou com ele. Alem disso, "
        "ela muda de **ordem** a cada coleta, mesmo com os mesmos clientes. "
        "Por isso cada entrada vira uma linha igual: comparar linha a linha "
        "acusaria de 2 a 6 mudancas por coleta em um andar com tres APs. "
        "Depois da normalizacao, a tabela inteira vira um placeholder e o que "
        "sobe no relatorio e quantas entradas existem.",
        substituicao="  <TABELA MAC>",
    ),
    _r(
        "numero-de-conexao",
        r"^(\s*)(\d+)\s+(active|open)\s+.*$",
        SUBSTITUIR,
        "Numeracao de sessao e efemera, e a ordem delas muda a cada coleta. "
        "Cada sessao vira uma linha igual pelo mesmo motivo da tabela MAC.",
        substituicao="  <SESSAO>",
    ),
    _r(
        "hash-de-senha",
        r"^(\s*)(username \S+ (password|secret) \d) .*$",
        SUBSTITUIR,
        "O hash da senha muda a cada troca de senha e nunca deve ser "
        "comparado nem impresso em log ou historico. O que interessa e "
        "**existe** uma senha, e nao qual e.",
        substituicao=r"\1\2 <HASH OCULTO>",
    ),
    _r(
        "cabecalho-de-coleta",
        r"^(?:###\s*colhido via SNMP em \d+|#\s*exportado via HTTP em \d+)(?:\s*###.*|\s*#.*)?$",
        REMOVER,
        "O cabecalho que o simulador coloca na saida carrega o numero da "
        "coleta e, na via SNMP, o numero de serie. Uma mudanca de coluna no "
        "relatorio de diff e um acrescimo do coletor, nao uma mudanca de "
        "configuracao - e o serie nao deve circular em diff nem em log.",
    ),
    _r(
        "chave-criptografica",
        r"^(\s*)(snmp-server community \S+ \S+)( \S+)?.*$",
        SUBSTITUIR,
        "Comunidade SNMP e segredo: nao vai para log nem para historico "
        "versionado. O valor fica substituido, a presenca e o algoritmo "
        "continuam legiveis.",
        substituicao=r"\1\2 <SEGREDO OCULTO>",
    ),
)


class RegraDuplicada(ValueError):
    """Duas regras com o mesmo nome."""

    def __init__(self, nome: str) -> None:
        super().__init__(f"regra duplicada: {nome}")
        self.nome = nome


def _agrupa_repetidas(linhas: list[str]) -> list[str]:
    """Funde linhas consecutivas identicas em uma so, com a contagem.

    Collapse consecutive identical lines into one, with the count.

    Algumas linhas de configuracao representam um **conjunto** que muda de
    tamanho e de ordem: a tabela MAC, a tabela de sessoes. Normalizar cada
    linha para o mesmo placeholder nao basta, porque as linhas saem em ordem
    diferente a cada coleta - e uma diff linha a linha reporta quatro
    "mudancas" onde nada mudou.

    Fundir a sequencia transforma a tabela inteira em uma linha que carrega a
    contagem. A diff passa a reportar uma linha em vez de N, e o numero
    continua visivel. Fundir apenas repeticoes **consecutivas** e o que torna
    isso seguro: duas linhas de configuracao iguais que por acaso ficam lado a
    lado, como duas interfaces identicas, continuam sendo duas linhas, porque
    fundi-las esconderia uma duplicata real.

    A contagem entra em um marcador separado, e nao na propria linha, por uma
    razao pratica: a tabela MAC cresce e encolhe conforme os clientes entram e
    saem. A **quantidade** muda a cada coleta sem que ninguem tenha feito
    nada, e se a contagem fosse comparada ela viraria uma alerta por coleta -
    exatamente o problema que a normalizacao existe para eliminar. O conteudo
    da tabela e preservado como uma linha; quantas entradas existem e
    informacao do momento da coleta, nao da configuracao.

    Args:
        linhas: Linhas ja normalizadas.

    Returns:
        As linhas com repeticoes consecutivas fundidas.
    """
    saida: list[str] = []
    i = 0

    while i < len(linhas):
        atual = linhas[i]
        tem_quebra = atual.endswith("\n")
        corpo = atual.rstrip("\n")

        j = i + 1
        while j < len(linhas) and linhas[j].rstrip("\n") == corpo:
            j += 1

        repeticoes = j - i
        if repeticoes == 1:
            saida.append(atual)
        else:
            # A linha fica identica; so o marcador leva a contagem. Ver a
            # docstring da funcao para por que a quantidade nao entra no
            # corpo da linha.
            saida.append(
                corpo + ("\n" if tem_quebra else "")
            )

        i = j

    return saida


class Normalizador:
    """Aplica a tabela de regras a uma configuracao.

    Applies the rule table to a configuration.

    Args:
        regras: Tabela de regras. O padrao e :data:`REGRAS_PADRAO`.

    Raises:
        RegraDuplicada: Se dois nomes se repetirem. Nome repetido faria uma
            regra sobrescrever a outra em qualquer lugar que use o nome como
            chave - e o nome e o que aparece no relatorio.
    """

    def __init__(self, regras: Iterable[Regra] | None = None) -> None:
        tabela = tuple(regras) if regras is not None else REGRAS_PADRAO

        vistos: set[str] = set()
        for regra in tabela:
            if regra.nome in vistos:
                raise RegraDuplicada(regra.nome)
            vistos.add(regra.nome)

        self.regras = tabela

    def normalizar_linhas(self, linhas: Iterable[str]) -> list[str]:
        """Normaliza linha a linha e funde as repeticoes consecutivas.

        Normalize line by line, then collapse consecutive repeats.

        Sao duas etapas porque elas resolvem problemas diferentes. A primeira
        transforma cada linha volatil em um placeholder. A segunda existe
        porque a tabela MAC e a tabela de sessoes mudam de **ordem** a cada
        coleta: normalizar cada linha resolve o conteudo, mas nao a ordem, e
        uma diff linha a linha continuaria acusando quatro mudancas onde
        nada mudou.

        A substituicao acontece sobre a linha **sem** a quebra de linha final,
        e a quebra volta depois. Sem isso, um ``str.replace`` de placeholder
        naquela posicao consumia o ``\\n`` da ultima linha do bloco e colava o
        texto seguinte na mesma linha - o que produzia uma saida como
        ``<REPETIDA 3x>end`` e um alerta fantasma na primeira comparacao.

        A primeira regra que casa vence. Por isso a ordem da tabela importa:
        a regra de uptime vem antes da de memoria para que
        ``Uptime: 3 days`` nao seja capturada como se fosse uso de memoria.

        Args:
            linhas: Linhas da configuracao.

        Returns:
            As linhas que sobreviveram, normalizadas e com repeticoes
            consecutivas fundidas.
        """
        saida: list[str] = []

        for original in linhas:
            # Separa a quebra de linha ANTES de qualquer regra. Uma regra que
            # substitui a linha inteira perde o terminador junto, e a ultima
            # linha do arquivo acaba colada na seguinte.
            tem_quebra = original.endswith("\n")
            limpa = original.rstrip("\n")

            for regra in self.regras:
                if regra.acao == PRESERVAR:
                    continue

                casa = regra.compila().match(limpa)
                if not casa:
                    continue

                if regra.acao == REMOVER:
                    limpa = None  # type: ignore[assignment]
                    break

                if regra.substituicao is not None:
                    limpa = regra.compila().sub(regra.substituicao, limpa)
                break

            if limpa is not None:
                saida.append(limpa + ("\n" if tem_quebra else ""))

        return _agrupa_repetidas(saida)

    def normalizar(self, texto: str) -> str:
        """Normaliza uma configuracao inteira.

        Normalize a whole configuration.

        Args:
            texto: Configuracao como texto, com ou sem linha final.

        Returns:
            A configuracao normalizada, sempre terminada em quebra de linha
            quando havia alguma linha de entrada.
        """
        return "".join(self.normalizar_linhas(texto.splitlines(keepends=True)))

    def regras_que_agiram(self, texto: str) -> list[str]:
        """Lista as regras que realmente mudaram algo neste texto.

        List the rules that actually changed something in this text.

        Util para o relatorio: mostra **por que** a normalizacao alterou o
        arquivo, e nao apenas quantas linhas sobraram.

        Args:
            texto: Configuracao original.

        Returns:
            Nomes das regras que casaram, na ordem da tabela, sem repeticao.
        """
        usadas: list[str] = []

        for linha in texto.splitlines():
            for regra in self.regras:
                if regra.acao == PRESERVAR:
                    continue
                if regra.compila().search(linha):
                    if regra.nome not in usadas:
                        usadas.append(regra.nome)
                    break

        return usadas

    def motivo_da(self, nome: str) -> str:
        """Devolve o motivo de uma regra pelo nome.

        Return a rule's reason by name.

        Args:
            nome: Identificador da regra.

        Returns:
            O motivo declarado.

        Raises:
            KeyError: Se a regra nao existir na tabela.
        """
        for regra in self.regras:
            if regra.nome == nome:
                return regra.motivo
        raise KeyError(nome)

    def tabela(self) -> list[dict[str, str]]:
        """Exporta a tabela de regras, para documentacao e relatorio.

        Export the rule table, for documentation and reporting.

        Returns:
            Uma lista de dicionarios com nome, acao, padrao e motivo.
        """
        return [
            {
                "nome": r.nome,
                "acao": r.acao,
                "padrao": r.padrao,
                "motivo": r.motivo,
            }
            for r in self.regras
        ]

