"""Prova de aceite do cfgbackup.

cfgbackup acceptance proof.

O criterio de aceite do projeto tem duas metades, e este script verifica as
duas:

1. **Duas coletas sem mexer em nada produzem "sem mudanca".** E o teste que
   separa uma ferramenta de backup de uma ferramenta de ruido. Se o uptime, a
   tabela MAC, os contadores ou a ordem das sessoes vazam para a diff, todo
   alerta passa a ser falso e o time silencia o sistema.
2. **Uma linha alterada fora do processo produz alerta**, com a diff correta e
   o historico registrando autor e data.

O script verifica ainda que uma mudanca **declarada** nao vira alerta: e a
metade que separa o sistema util do sistema que ninguem ouve depois da segunda
falsa sentida.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from cfgbackup.coletor import (  # noqa: E402
    carregar_equipamentos,
    coletar,
)
from cfgbackup.diferenca import (  # noqa: E402
    ESPERADA,
    INESPERADA,
    SEM_MUDANCA,
    MudancaEsperada,
    comparar,
)
from cfgbackup.historico import registrar  # noqa: E402
from cfgbackup.normalizador import Normalizador  # noqa: E402
from cfgbackup.simulador import Simulador  # noqa: E402

# Linha plantada como drift: uma mudanca real, feita fora do processo.
LINHA_DRIFT = "spanning-tree mode rapid-pvst"
# Linha plantada como mudanca esperada: foi declarada antes de acontecer.
LINHA_ESPERADA = "ip route 10.20.0.0 255.255.255.0 10.0.0.1"
HOST_ALVO = "SW-LAB-01"
DATA = "2026-01-15 14:00"
OPERADOR = "kelvin"


class Falha(Exception):
    """Uma condicao de aceite nao foi satisfeita."""


def checar(condicao: bool, mensagem: str) -> None:
    """Falha se a condicao for falsa.

    Fail if the condition is false.
    """
    if not condicao:
        raise Falha(mensagem)


def coletar_tick(tick: int, destino: Path) -> dict[str, str]:
    """Faz uma coleta no tick pedido e devolve os normalizados.

    Collect at the requested tick and return the normalized configs.

    Args:
        tick: Passo do relogio do simulador.
        destino: Diretorio onde gravar.

    Returns:
        Mapa ``hostname -> configuracao normalizada``.
    """
    definicoes = carregar_equipamentos(RAIZ / "dados" / "equipamentos.yaml")
    sim = Simulador()
    sim.avancar(tick)
    coletas = coletar(definicoes, sim, destino, Normalizador())
    return {c.equipamento: c.normalizado for c in coletas}


def principal() -> int:
    """Roda a prova de aceite.

    Run the acceptance proof.

    Returns:
        0 se as duas metades do criterio passarem.
    """
    falhas: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp)
        anterior = raiz / "anterior"
        atual = raiz / "atual"

        # ---------------- metade 1: sem mudanca ----------------
        print("1) duas coletas sem mexer em nada")
        antes = coletar_tick(7, anterior)
        depois = coletar_tick(8, atual)

        for host in sorted(antes):
            d = comparar(host, antes[host], depois[host])
            if d.estado != SEM_MUDANCA:
                falhas.append(
                    f"{host}: estado {d.estado}, esperado sem_mudanca; "
                    f"resumo: {d.texto()[:400]}"
                )
            else:
                print(f"   {host}: sem mudanca")

        # Uma terceira coleta, com um salto bem maior de ticks, para
        # confirmar que a ausencia de falso positivo nao e acaso do par 7/8.
        print("   (reforco: um salto de 23 ticks tambem tem de sair limpo)")
        antes_longe = coletar_tick(41, raiz / "a_longe")
        depois_longe = coletar_tick(64, raiz / "d_longe")
        for host in sorted(antes_longe):
            d = comparar(host, antes_longe[host], depois_longe[host])
            checar(
                d.estado == SEM_MUDANCA,
                f"{host} com 23 ticks de intervalo: estado {d.estado}, "
                f"esperado sem_mudanca",
            )
        print("   23 ticks de intervalo: sem mudanca nos tres equipamentos")

        # ---------------- metade 2: drift ----------------
        print("\n2) uma linha alterada fora do processo")
        sim = Simulador()
        sim.avancar(8)
        definicoes = carregar_equipamentos(RAIZ / "dados" / "equipamentos.yaml")
        coletas_alteradas = coletar(definicoes, sim, None, Normalizador())

        # O drift e aplicado no simulador e so aparece na coleta seguinte.
        # A coleta sem drift e a que serve de referencia.
        sem_drift = {
            c.equipamento: c.normalizado
            for c in coletar(definicoes, sim, None, Normalizador())
        }

        sim2 = Simulador()
        sim2.avancar(9)
        sim2.alterar(HOST_ALVO, LINHA_DRIFT)
        com_drift = {
            c.equipamento: c.normalizado
            for c in coletar(definicoes, sim2, None, Normalizador())
        }

        normalizados = com_drift

        d = comparar(HOST_ALVO, antes[HOST_ALVO], normalizados[HOST_ALVO])
        checar(d.estado == INESPERADA, f"{HOST_ALVO}: drift nao foi acusado")
        checar(len(d.mudancas) == 1, f"{HOST_ALVO}: esperado 1 mudanca, veio {len(d.mudancas)}")
        checar(
            LINHA_DRIFT in (d.mudancas[0].depois or ""),
            f"{HOST_ALVO}: a diff nao contem a linha plantada",
        )
        print(f"   {HOST_ALVO}: {d.estado}, {len(d.mudancas)} mudanca(s)")
        print(f"   diff: {d.texto()}")

        # O texto da diff precisa citar a linha.
        checar(LINHA_DRIFT in d.texto(), "a diff em texto nao mostra a linha plantada")

        # ---------------- metade 3: mudanca esperada ----------------
        print("\n3) uma mudanca declarada nao vira alerta")
        esperado = MudancaEsperada(
            padrao=r"^ ip route 10\.20\.0\.0",
            motivo="abertura de rota para o servidor de backup, janela de 15/01",
            autor=OPERADOR,
            ate="2026-01-20",
        )

        sim3 = Simulador()
        sim3.avancar(9)
        sim3.alterar(HOST_ALVO, LINHA_ESPERADA)
        com_esperada = {c.equipamento: c.normalizado for c in
                        coletar(definicoes, sim3, None, Normalizador())}

        d_esp = comparar(HOST_ALVO, antes[HOST_ALVO], com_esperada[HOST_ALVO], [esperado])
        checar(
            d_esp.estado == ESPERADA,
            f"a mudanca declarada deveria ser esperada, veio {d_esp.estado}",
        )
        checar(not d_esp.alerta, "a mudanca declarada disparou alerta")
        checar(len(d_esp.esperadas) == 1, "esperava 1 mudanca declarada")
        print(f"   {HOST_ALVO}: {d_esp.estado}, sem alerta, motivo: {d_esp.esperadas[0].motivo}")

        # ---------------- metade 4: historico ----------------
        print("\n4) o historico registra autor e data")
        arquivo = raiz / "historico.md"
        n = registrar(arquivo, DATA, OPERADOR, [d, d_esp])
        checar(n == 2, f"esperava 2 registros, vieram {n}")

        texto = arquivo.read_text(encoding="utf-8")
        checar(DATA in texto, "a data sumiu do historico")
        checar(OPERADOR in texto, "o operador sumiu do historico")
        checar(HOST_ALVO in texto, "o equipamento sumiu do historico")
        checar(LINHA_DRIFT in texto, "a linha plantada sumiu do historico")
        checar("drift" in texto.lower(), "o historico nao separa o que nao foi declarado")
        print(f"   {n} registros, {len(texto.splitlines())} linhas")

    if falhas:
        print("\nACEITE FALHOU:")
        for f in falhas:
            print("  -", f)
        return 1

    print("\nok: sem mudanca sem tocar em nada, alerta no drift, sem alerta no")
    print("declarado, e historico com autor e data")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())