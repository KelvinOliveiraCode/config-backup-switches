"""CLI do cfgbackup - backup de configuracao com deteccao de mudanca.

CLI for cfgbackup - configuration backup with change detection.

Tres subcomandos, na ordem em que se usa:

```
coletar  ->  grava bruto e normalizado
comparar ->  diff entre duas coletas, e classifica a mudanca
regras   ->  mostra a tabela de normalizacao e o motivo de cada regra
```

O ``regras`` existe por um motivo que so aparece depois de rodar o alerta
pela terceira vez: quando o relatorio diz "12 mudancas" e nao se sabe quais
linhas deviam ter sumido, nao ha como depurar. A tabela com motivo e o que
responde essa pergunta antes dela ser perguntada.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from .coletor import (
    Coleta,
    EquipamentoDef,
    ListaInvalida,
    SUFIXO_BRUTO,
    SUFIXO_NORMALIZADO,
    carregar_equipamentos,
    coletar,
    carregar_normalizado,
)
from typing import NamedTuple

from .diferenca import (
    ESPERADA,
    INESPERADA,
    SEM_MUDANCA,
    Diff,
    MudancaEsperada,
    comparar,
)
from .historico import OperadorVazio, registrar
from .normalizador import Normalizador
from .simulador import EquipamentoDesconhecido, Simulador


# Data fixa usada quando o operador nao passa uma. Um historico com a hora da
# execucao muda a cada run e quebra o git diff, entao o padrao do projeto e
# deterministico e a mudanca de data e explicita.
DATA_PADRAO = "2026-01-15 14:00"
OPERADOR_PADRAO = "operador-local"

ESTADO_ROTULO = {
    SEM_MUDANCA: "sem mudanca",
    ESPERADA: "mudanca esperada",
    INESPERADA: "MUDANCA INESPERADA",
}


def _diff_por_equipamento(
    anterior: dict[str, str],
    atual: dict[str, str],
    esperadas: dict[str, list[MudancaEsperada]],
) -> list[Diff]:
    """Compara as duas coletas.

    Compare the two collections.

    A ordem dos equipamentos e a ordem do arquivo, para o resultado nao mudar
    entre execucoes so por causa de como o sistema de arquivos enumerou.
    """
    todos = sorted(set(anterior) | set(atual))
    return [
        comparar(host, anterior.get(host, ""), atual.get(host, ""), esperadas.get(host, []))
        for host in todos
    ]


class DeclaracaoExpirada(NamedTuple):
    """Uma declaracao que existia, mas cuja janela ja passou.

    A declaration that existed but whose window has closed.

    A declaracao expirada e a unica forma de o alerta explicar a si mesmo: sem
    ela, a mudanca volta a ser drift mudo, e o operador ve um alerta sem pista
    de que existia uma janela declarada - ou seja, sem como saber se renova a
    declaracao ou se investiga.

    Declarations that closed are reported instead of silently dropped, because
    an alert nobody can act on is the same as no alert at all.
    """

    equipamento: str
    padrao: str
    motivo: str
    autor: str
    ate: str


def _aplica_padrao(declaracao: MudancaEsperada, data: str | None) -> MudancaEsperada:
    """Devolve a declaracao, expirada se a janela passou.

    Return the declaration, expired if its window has passed.

    Uma declaracao com prazo e uma promessa: "isso vai mudar ate o dia 20".
    Passado o dia 20, a mudanca que ela descreve nao e mais esperada - vira
    drift, e e isso que se quer. Sem essa checagem, o prazo no YAML e apenas
    um comentario, e o `--ate` vira enfeite que ninguem precisa preencher
    direito.

    Args:
        declaracao: A declaracao original.
        data: Data de referencia, ``AAAA-MM-DD HH:MM``. Quando ``None``, a
            janela nao e avaliada e a declaracao vale.

    Returns:
        A propria declaracao, ou uma copia com ``padrao`` que nunca casa.
    """
    if not declaracao.ate or data is None:
        return declaracao

    try:
        alvo = datetime.strptime(declaracao.ate, "%Y-%m-%d")
    except ValueError:
        # Prazo ilegivel e um erro de inventario, e adivinhar a partir dele
        # significa aceitar uma declaracao sem prazo de um jeito silencioso.
        raise ListaInvalida(
            f"prazo invalido em {declaracao.autor!r}: {declaracao.ate!r} "
            "(use AAAA-MM-DD)"
        ) from None

    agora = datetime.strptime(data[:10], "%Y-%m-%d")
    if agora > alvo:
        return MudancaEsperada(
            padrao=r"(?!)",  # nunca casa
            motivo=f"{declaracao.motivo} (janela encerrada em {declaracao.ate})",
            autor=declaracao.autor,
            ate=declaracao.ate,
        )
    return declaracao


def _carrega_esperadas(
    caminho: str | Path | None,
    data: str | None = None,
    expiradas: list[DeclaracaoExpirada] | None = None,
) -> dict[str, list[MudancaEsperada]]:
    """Le as mudancas declaradas de um YAML.

    Read the declared changes from a YAML file.

    Args:
        caminho: Caminho do arquivo, ou ``None``.
        data: Data de referencia, usada para expirar declaracoes com prazo.
        expiradas: Lista onde as declaracoes vencidas sao acumuladas, para que
            o relatorio diga por que a janela fechou. Mutavel de proposito:
            a assinatura com retorno unico fica mais simples para quem so
            quer o mapa.

    Returns:
        Mapa ``hostname -> lista de declaracoes``.

    Raises:
        ListaInvalida: Se o arquivo estiver malformado.
    """
    if not caminho:
        return {}

    import yaml

    bruto = yaml.safe_load(Path(caminho).read_text(encoding="utf-8")) or {}
    if not isinstance(bruto, dict):
        raise ListaInvalida("o arquivo de mudancas esperadas deve ser um mapa")

    resultado: dict[str, list[MudancaEsperada]] = {}
    for host, itens in bruto.items():
        if not isinstance(itens, list):
            raise ListaInvalida(f"{host}: a lista de esperadas esta malformada")
        declaracoes = []
        for item in itens:
            if not isinstance(item, dict):
                continue
            original = MudancaEsperada(
                padrao=str(item.get("padrao", "")),
                motivo=str(item.get("motivo", "")),
                autor=str(item.get("autor", "desconhecido")),
                ate=(str(item["ate"]) if item.get("ate") else None),
            )
            aplicada = _aplica_padrao(original, data)
            if expiradas is not None and aplicada is not original and original.ate:
                expiradas.append(
                    DeclaracaoExpirada(
                        equipamento=str(host),
                        padrao=original.padrao,
                        motivo=original.motivo,
                        autor=original.autor,
                        ate=original.ate,
                    )
                )
            declaracoes.append(aplicada)
        resultado[str(host)] = declaracoes

    return resultado


def _linha_coleta(coleta: Coleta) -> str:
    """Uma linha de resumo de uma coleta.

    A one-line summary of a collection.
    """
    return (
        f"  {coleta.equipamento:<14} via {coleta.via:<5} "
        f"{coleta.linhas_brutas:>4} linhas -> {coleta.linhas_normalizadas:>4} "
        f"normalizadas ({coleta.linhas_removidas} removidas)"
    )


def _cmd_coletar(args: argparse.Namespace) -> int:
    """Coleta a configuracao dos equipamentos declarados.

    Collect the declared devices' configuration.

    Returns:
        0 em sucesso, 2 em erro de entrada.
    """
    definicoes = carregar_equipamentos(args.equipamentos)
    if not definicoes:
        print(f"nenhum equipamento declarado em {args.equipamentos}", file=sys.stderr)
        return 2

    simulador = Simulador(semente=args.semente)
    # Dois ticks de padrao deixam o aparelho com passado, como um equipamento
    # que ja estava em producao antes do primeiro backup. O primeiro backup
    # de um equipamento com zero segundos de uptime nao parece com equipamento.
    simulador.avancar(args.ticks)

    destino = Path(args.saida)
    coletas = coletar(definicoes, simulador, destino, Normalizador())

    print(f"coleta de {len(coletas)} equipamento(s) em {destino}")
    for c in coletas:
        print(_linha_coleta(c))

    regras = sorted({r for c in coletas for r in c.regras_acionadas})
    print(f"\nregras de normalizacao acionadas: {len(regras)}")
    for nome in regras:
        print(f"  - {nome}")

    print(f"\nbrutos em *{SUFIXO_BRUTO}, normalizados em *{SUFIXO_NORMALIZADO}")
    print("nenhum equipamento real foi acessado: a coleta sai do simulador")
    return 0


def _cmd_comparar(args: argparse.Namespace) -> int:
    """Compara duas coletas e registra no historico.

    Compare two collections and write the history.

    Returns:
        0 se nao houver mudanca inesperada, 1 se houver.
    """
    anterior = carregar_normalizado(args.anterior)
    atual = carregar_normalizado(args.atual)
    expiradas: list[DeclaracaoExpirada] = []
    esperadas = _carrega_esperadas(args.esperadas, args.data, expiradas)

    diffs = _diff_por_equipamento(anterior, atual, esperadas)

    print(f"anterior: {args.anterior}")
    print(f"atual   : {args.atual}\n")

    for d in diffs:
        print(f"{d.equipamento}: {ESTADO_ROTULO[d.estado]}")
        for m in d.mudancas:
            print(f"    {m.resumo()}")
        if not d.mudancas:
            print("    nenhuma linha mudou depois da normalizacao")
        print()

    if expiradas:
        print("declaracoes com a janela encerrada:")
        for e in expiradas:
            print(f"    {e.equipamento}  padrao={e.padrao}  por {e.autor}")
            print(f"      motivo: {e.motivo}")
            print(f"      janela encerrada em {e.ate}")
        print()

    if args.historico:
        n = registrar(
            args.historico,
            data=args.data,
            operador=args.operador,
            diffs=diffs,
        )
        print(f"{n} registro(s) acrescentados a {args.historico}")

    alertas = [d for d in diffs if d.alerta]
    if alertas:
        print(
            f"\nALERTA: {len(alertas)} equipamento(s) com mudanca inesperada: "
            + ", ".join(d.equipamento for d in alertas)
        )
        return 1

    print("\nsem mudanca inesperada")
    return 0


def _cmd_regras(args: argparse.Namespace) -> int:
    """Mostra a tabela de normalizacao com o motivo de cada regra.

    Show the normalization table with each rule's reason.

    Returns:
        0 sempre.
    """
    norm = Normalizador()
    tabela = norm.tabela()

    if args.texto:
        for linha in tabela:
            print(f"{linha['nome']}  ({linha['acao']})")
            print(f"    padrao: {linha['padrao']}")
            print(f"    motivo: {linha['motivo']}")
            print()
        return 0

    print(f"{len(tabela)} regra(s) de normalizacao\n")
    for linha in tabela:
        print(f"{linha['nome']:<26} {linha['acao']}")

    print("\ncom --texto, mostra o padrao e o motivo de cada regra")
    print("motivo em docs/o-que-nao-comparar.md")
    return 0


def construir_parser() -> argparse.ArgumentParser:
    """Monta o parser de argumentos.

    Build the argument parser.
    """
    parser = argparse.ArgumentParser(
        prog="cfgbackup",
        description=(
            "Coleta configuracao de equipamentos ficticios, normaliza e detecta "
            "mudanca gerenciada. "
            "Collects fictitious device configuration, normalizes it and "
            "detects managed change."
        ),
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    p_col = sub.add_parser("coletar", help="Coleta a configuracao dos equipamentos.")
    p_col.add_argument(
        "--equipamentos", default="dados/equipamentos.yaml",
        help="YAML com a lista de equipamentos.",
    )
    p_col.add_argument("--saida", default="saida/", help="Diretorio de saida.")
    p_col.add_argument(
        "--ticks", type=int, default=7,
        help="Passos do relogio do simulador. Define o uptime e os contadores.",
    )
    p_col.add_argument(
        "--semente", type=int, default=20260115,
        help="Semente do simulador. Fixa o conteudo volatil.",
    )
    p_col.set_defaults(func=_cmd_coletar)

    p_cmp = sub.add_parser("comparar", help="Compara duas coletas.")
    p_cmp.add_argument("--anterior", required=True, help="Diretorio da coleta anterior.")
    p_cmp.add_argument("--atual", required=True, help="Diretorio da coleta atual.")
    p_cmp.add_argument("--esperadas", help="YAML com as mudancas ja declaradas.")
    p_cmp.add_argument("--historico", help="Arquivo Markdown onde registrar.")
    p_cmp.add_argument("--data", default=DATA_PADRAO, help="Data do registro.")
    p_cmp.add_argument("--operador", default=OPERADOR_PADRAO, help="Quem coletou.")
    p_cmp.set_defaults(func=_cmd_comparar)

    p_reg = sub.add_parser("regras", help="Mostra a tabela de normalizacao.")
    p_reg.add_argument(
        "--texto", action="store_true",
        help="Mostra padrao e motivo de cada regra.",
    )
    p_reg.set_defaults(func=_cmd_regras)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada da CLI.

    CLI entry point.
    """
    parser = construir_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (
        ListaInvalida,
        EquipamentoDesconhecido,
        OperadorVazio,
        OSError,
    ) as exc:
        print(f"Erro / error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())