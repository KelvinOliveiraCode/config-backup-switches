"""Grava o exemplo do historico com os quatro estados, de forma deterministica."""

import sys
from pathlib import Path

sys.path.insert(0, "src")

from cfgbackup.coletor import (
    carregar_equipamentos,
    carregar_normalizado,
    coletar,
)
from cfgbackup.diferenca import MudancaEsperada, comparar
from cfgbackup.historico import registrar
from cfgbackup.normalizador import Normalizador
from cfgbackup.simulador import Simulador

DEFINICOES = carregar_equipamentos("dados/equipamentos.yaml")

# Drift: tres linhas que ninguem declarou.
DRIFT = {
    "SW-LAB-01": "spanning-tree mode rapid-pvst",
    "FW-LAB-01": "access-list 100 permit tcp any any eq 8080",
    "SW-LAB-02": "line vty 0 4",
}
# Esperada: uma linha com prazo que ainda nao venceu.
ESPERADA = ("SW-LAB-02", " exec-timeout 5 0")

saida = Path("exemplos/historico-exemplo.md")
if saida.exists():
    saida.unlink()

print("=== 1) baseline limpo ===")
sim1 = Simulador()
sim1.avancar(7)
anterior = {c.equipamento: c.normalizado for c in coletar(DEFINICOES, sim1, None, Normalizador())}

limpos = [
    comparar(h, anterior[h], anterior[h])
    for h in sorted(anterior)
]
registrar(saida, "2026-01-15 14:00", "sistema de backup", limpos)
for d in limpos:
    print(f"   {d.equipamento}: {d.estado}")

print()
print("=== 2) com drift e uma mudanca declarada ===")
sim2 = Simulador()
sim2.avancar(11)
for host, linha in DRIFT.items():
    sim2.alterar(host, linha)
sim2.alterar(ESPERADA[0], ESPERADA[1])
atual = {c.equipamento: c.normalizado for c in coletar(DEFINICOES, sim2, None, Normalizador())}

declaracao = MudancaEsperada(
    padrao=r"^\s+exec-timeout",
    motivo="reducao do timeout de sessao conforme politica de seguranca de 2026-01",
    autor="kelvin",
    ate="2026-03-01",
)
diffs = [
    comparar(h, anterior[h], atual[h], [declaracao] if h == ESPERADA[0] else [])
    for h in sorted(anterior)
]
registrar(saida, "2026-01-20 09:30", "kelvin", diffs)
for d in diffs:
    print(f"   {d.equipamento}: {d.estado}, {len(d.mudancas)} mudanca(s), "
          f"{len(d.esperadas)} esperada(s)")

print()
print(f"gravado em {saida}: {len(saida.read_text(encoding='utf-8').splitlines())} linhas")