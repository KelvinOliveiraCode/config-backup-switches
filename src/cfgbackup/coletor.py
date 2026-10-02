"""Coleta de configuracao, com normalizacao obrigatoria antes de gravar.

Configuration collection, with mandatory normalization before writing.

O fluxo tem tres etapas e a ordem nao e negociavel:

```
SNMP ou HTTP (simulado)  ->  bruto  ->  normalizado
```

Grava **os dois** arquivos. O bruto e o que o equipamento respondeu, e ele e o
unico jeito de descobrir que a tabela de normalizacao esta errada: se a regra
removeu demais, so o bruto mostra o que sumiu. Guardar so o normalizado faz o
erro ser invisivel ate o dia em que voce precisar do valor original.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .normalizador import Normalizador
from .simulador import EquipamentoDesconhecido, Simulador


# Sufixo do arquivo bruto e do normalizado.
SUFIXO_BRUTO = ".txt"
SUFIXO_NORMALIZADO = ".normalizado.txt"


class ListaInvalida(ValueError):
    """O arquivo de equipamentos nao tem o formato esperado."""

    def __init__(self, mensagem: str) -> None:
        super().__init__(mensagem)


@dataclass(frozen=True)
class EquipamentoDef:
    """Um equipamento declarado no arquivo de inventario.

    A device declared in the inventory file.

    Attributes:
        hostname: Nome do aparelho.
        tipo: ``switch`` ou ``firewall``.
        via: TransportePreferred da coleta, ``http`` ou ``snmp``.
        comunidade: Comunidade SNMP ficticia.
    """

    hostname: str
    tipo: str
    via: str = "http"
    comunidade: str = "LABCOMUNIDADE"


@dataclass(frozen=True)
class Coleta:
    """O resultado de coletar um equipamento.

    The result of collecting one device.

    Attributes:
        equipamento: Hostname coletado.
        via: Transporte usado.
        bruto: Texto como o aparelho respondeu.
        normalizado: Texto depois da normalizacao.
        regras_acionadas: Nomes das regras que mexeram no texto.
    """

    equipamento: str
    via: str
    bruto: str
    normalizado: str
    regras_acionadas: tuple[str, ...] = ()

    @property
    def linhas_brutas(self) -> int:
        """Quantas linhas o aparelho devolveu.

        How many lines the device returned.
        """
        return len(self.bruto.splitlines())

    @property
    def linhas_normalizadas(self) -> int:
        """Quantas linhas sobraram.

        How many lines survived.
        """
        return len(self.normalizado.splitlines())

    @property
    def linhas_removidas(self) -> int:
        """Quantas linhas a normalizacao eliminou.

        How many lines normalization removed.
        """
        return self.linhas_brutas - self.linhas_normalizadas

    def para_dict(self) -> dict[str, object]:
        """Serializa a coleta.

        Serialize the collection.
        """
        return {
            "equipamento": self.equipamento,
            "via": self.via,
            "linhas_brutas": self.linhas_brutas,
            "linhas_normalizadas": self.linhas_normalizadas,
            "linhas_removidas": self.linhas_removidas,
            "regras": list(self.regras_acionadas),
        }


def carregar_equipamentos(caminho: str | Path) -> list[EquipamentoDef]:
    """Le o arquivo YAML de equipamentos.

    Read the equipment YAML file.

    Args:
        caminho: Caminho do arquivo.

    Returns:
        A lista de equipamentos, ordenada por hostname para saida estavel.

    Raises:
        ListaInvalida: Se o arquivo nao for uma lista, ou se um item estiver
            sem hostname, ou com tipo desconhecido.
    """
    import yaml

    caminho = Path(caminho)
    if not caminho.exists():
        raise ListaInvalida(f"arquivo nao encontrado: {caminho}")

    bruto = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    if bruto is None:
        return []
    if not isinstance(bruto, list):
        raise ListaInvalida(
            f"o arquivo deve conter uma lista de equipamentos, veio {type(bruto).__name__}"
        )

    equipamentos: list[EquipamentoDef] = []
    vistos: set[str] = set()

    for item in bruto:
        if not isinstance(item, dict):
            raise ListaInvalida(f"item nao e um mapa: {item!r}")

        hostname = str(item.get("hostname", "")).strip()
        if not hostname:
            raise ListaInvalida(f"item sem hostname: {item!r}")

        if hostname in vistos:
            raise ListaInvalida(f"hostname repetido: {hostname}")
        vistos.add(hostname)

        tipo = str(item.get("tipo", "")).strip().lower()
        if tipo not in ("switch", "firewall"):
            raise ListaInvalida(
                f"{hostname}: tipo invalido {tipo!r} (use 'switch' ou 'firewall')"
            )

        via = str(item.get("via", "http")).strip().lower()
        if via not in ("http", "snmp"):
            raise ListaInvalida(
                f"{hostname}: via invalida {via!r} (use 'http' ou 'snmp')"
            )

        equipamentos.append(
            EquipamentoDef(
                hostname=hostname,
                tipo=tipo,
                via=via,
                comunidade=str(item.get("comunidade", "LABCOMUNIDADE")).strip(),
            )
        )

    return sorted(equipamentos, key=lambda e: e.hostname)


def coletar(
    definicoes: Iterable[EquipamentoDef],
    simulador: Simulador | None = None,
    destino: str | Path | None = None,
    normalizador: Normalizador | None = None,
) -> list[Coleta]:
    """Coleta a configuracao de cada equipamento declarado.

    Collect each declared device's configuration.

    Args:
        definicoes: Equipamentos a coletar.
        simulador: Simulador a usar. O padrao e um simulador novo.
        destino: Diretorio onde gravar os arquivos. Se ``None``, nao grava.
        normalizador: Tabela de normalizacao. O padrao e a tabela embutida.

    Returns:
        Uma coleta por equipamento, ordenada por hostname.

    Raises:
        EquipamentoDesconhecido: Se o inventario citar um aparelho que o
            simulador nao tem. A lista e a fonte da verdade do que existe;
            um hostname a mais no inventario e um erro de inventario, nao um
            equipamento para inventar.
    """
    sim = simulador if simulador is not None else Simulador()
    norm = normalizador if normalizador is not None else Normalizador()

    saida = Path(destino) if destino is not None else None
    if saida is not None:
        saida.mkdir(parents=True, exist_ok=True)

    coletas: list[Coleta] = []
    for definicao in sorted(definicoes, key=lambda d: d.hostname):
        bruto = sim.coletar(definicao.hostname, definicao.via)
        normalizado = norm.normalizar(bruto)

        coleta = Coleta(
            equipamento=definicao.hostname,
            via=definicao.via,
            bruto=bruto,
            normalizado=normalizado,
            regras_acionadas=tuple(norm.regras_que_agiram(bruto)),
        )
        coletas.append(coleta)

        if saida is not None:
            (saida / f"{definicao.hostname}{SUFIXO_BRUTO}").write_text(
                bruto, encoding="utf-8"
            )
            (saida / f"{definicao.hostname}{SUFIXO_NORMALIZADO}").write_text(
                normalizado, encoding="utf-8"
            )

    return coletas


def carregar_normalizado(caminho: str | Path) -> dict[str, str]:
    """Le os arquivos normalizados de um diretorio de saida.

    Read the normalized files from an output directory.

    Args:
        caminho: Diretorio com as coletas.

    Returns:
        Mapa ``hostname -> configuracao normalizada``, ordenado por hostname.

    Raises:
        ListaInvalida: Se o diretorio nao existir ou nao tiver nenhum arquivo
            normalizado. Um diretorio vazio nao e "sem mudancas": e ausencia
            de dado, e a distincao importa porque um backup que nao achou nada
            parece um backup que nao mudou nada.
    """
    caminho = Path(caminho)
    if not caminho.exists():
        raise ListaInvalida(f"diretorio nao encontrado: {caminho}")

    resultado: dict[str, str] = {}
    for arquivo in sorted(caminho.glob(f"*{SUFIXO_NORMALIZADO}")):
        hostname = arquivo.name[: -len(SUFIXO_NORMALIZADO)]
        resultado[hostname] = arquivo.read_text(encoding="utf-8")

    if not resultado:
        raise ListaInvalida(
            f"nenhum arquivo {SUFIXO_NORMALIZADO} em {caminho}: "
            "a coleta nao foi feita, ou foi feita em outro formato"
        )

    return resultado