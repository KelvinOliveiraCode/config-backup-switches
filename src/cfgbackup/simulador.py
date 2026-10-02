"""Simulador de equipamentos de rede com interface SNMP e HTTP ficticias.

Fictitious network equipment simulator with SNMP and HTTP interfaces.

**Nenhum equipamento real e acessado.** Este modulo gera configuracao de
aparelhos que nao existem, para que o fluxo de backup, normalizacao e diff
poder ser desenvolvido e testado sem tocar em rede.

A simulacao tem duas metades que reproduzem o problema real:

- **ruido**: campos que mudam a cada coleta porque o aparelho esta vivo -
  uptime, contadores, tabela MAC, data da ultima gravacao. E o que faz a
  normalizacao existir.
- **drift**: mudanca feita fora do processo, que so aparece quando se compara
  com o backup anterior. E o que o alerta precisa pegar.

O ``tick`` e um contador determinista: a mesma sequencia de ticks gera sempre a
mesma configuracao. Sem isso, "rodar duas vezes seguidas produz sem mudancas"
seria um teste que passa ou falha conforme o relogio.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


# Texto base de um switch Cisco ficticio. As linhas volatis ficam marcadas
# entre colchetes duplos e sao preenchidas pelo simulador a cada coleta.
BASE_SWITCH = """!Last configuration change at {data} by kelvin
!NVRAM config last updated at {data} from flash
version 15.2
!
hostname {hostname}
!
boot system flash:{imagem}
!
{uptime}
snmp-server community {comunidade} RO
snmp-server location {localizacao}
!
vlan {vlan_dados}
 name {vlan_dados_nome}
!
interface GigabitEthernet1/0/{porta_dados}
 description {descricao_dados}
 switchport access vlan {vlan_dados}
 switchport mode access
!
interface GigabitEthernet1/0/{porta_trunk}
 description {descricao_trunk}
 switchport trunk encapsulation dot1q
 switchport trunk allowed vlan {vlan_dados},{vlan_gerencia}
 switchport trunk native vlan {vlan_gerencia}
 switchport mode trunk
!
interface Vlan{vlan_gerencia}
 ip address {gateway} {mascara}
!
router ospf 1
 router-id {router_id}
 network {rede_ospf} {mascara_ospf} area 0
!
{tabela_mac}
line vty 0 4
 password {senha}
 login local
 transport input ssh
!
logging trap informational
logging buffer: size 512, level debugging, lines logged {linhas_log}
end"""


BASE_FIREWALL = """!Last configuration change at {data} by kelvin
!NVRAM config last updated at {data} from flash
version 15.2
!
hostname {hostname}
!
{uptime}
snmp-server community {comunidade} RO
!
interface GigabitEthernet0/0
 description {descricao_wan}
 ip address {ip_wan} {mascara_wan}
 ip nat outside
!
interface GigabitEthernet0/1
 description {descricao_lan}
 ip address {ip_lan} {mascara_lan}
 ip nat inside
!
ip nat inside source list LISTA_NAT interface GigabitEthernet0/0 overload
ip route 0.0.0.0 0.0.0.0 {gateway_wan}
!
access-list 100 permit ip {rede_lan} any
access-list 100 deny ip any any log
!
{conexoes}
end"""


class EquipamentoDesconhecido(KeyError):
    """O hostname pedido nao existe no simulador."""


class ValorAusente(ValueError):
    """O template pede um campo que os dados nao fornecem.

    Distinto de um erro de tipo, que seria outra coisa. Este aqui significa
    que o template e os dados estao fora de sincronia - e o tipo do equipamento
    e o lugar onde isso aparece, entao a excecao carrega o hostname.
    """


@dataclass
class Equipamento:
    """Um equipamento ficticio e sua configuracao base.

    A fictitious device and its base configuration.

    Attributes:
        hostname: Nome unico do aparelho.
        tipo: ``switch`` ou ``firewall``.
        serial: Numero de serie ficticio.
        base: Dicionario de valores usados no template.
        deriva: Linhas de configuracao alteradas fora do processo. E o drift.
        normalizado_esperado: Quantas linhas a configuracao deve ter depois
            da normalizacao. Serve de ancora para os testes.
    """

    hostname: str
    tipo: str
    serial: str
    base: dict[str, object] = field(default_factory=dict)
    deriva: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.base:
            self.base = self._base_padrao()

    def _base_padrao(self) -> dict[str, object]:
        """Monta os valores base conforme o tipo.

        Build the base values according to the type.
        """
        comum = {
            "data": "01/01/2026 09:00",
            "imagem": "c2960-lanbasek9-mz.151-2.S.bin",
            "comunidade": "LABCOMUNIDADE",
            "vlan_gerencia": 99,
            "gateway": "10.0.0.1",
            "mascara": "255.255.255.0",
            "senha": "$9$LABCONFIG$hash",
        }

        if self.tipo == "switch":
            comum.update({
                "vlan_dados": 10,
                "vlan_dados_nome": "DADOS",
                "porta_dados": 1,
                "descricao_dados": "PC-RECEPCAO",
                "porta_trunk": 24,
                "descricao_trunk": "TRUNK-PARA-CORE",
                "router_id": "10.0.0.1",
                "rede_ospf": "10.0.0.0",
                "mascara_ospf": "0.0.0.255",
                "localizacao": "LAB-SALA-1",
            })
        else:
            comum.update({
                "descricao_wan": "WAN-LAB",
                "ip_wan": "198.51.100.10",
                "mascara_wan": "255.255.255.252",
                "descricao_lan": "LAN-LAB",
                "ip_lan": "10.0.0.254",
                "mascara_lan": "255.255.255.0",
                "gateway_wan": "198.51.100.9",
                "rede_lan": "10.0.0.0",
            })

        return comum


class Simulador:
    """O conjunto de equipamentos ficticios.

    The set of fictitious devices.

    A colecao e deterministica: mesma semente e mesmo tick produzem a mesma
    configuracao, byte a byte. E o que permite testar "sem mudancas" sem
    depender de relogio.
    """

    def __init__(self, semente: int = 20260115) -> None:
        self.semente = semente
        self.tick = 0
        self.equipamentos = self._fabrica()

    def _fabrica(self) -> dict[str, Equipamento]:
        """Cria o parque de equipamentos.

        Build the device fleet.
        """
        return {
            "SW-LAB-01": Equipamento(
                "SW-LAB-01", "switch", "FOC2451X0LAB",
            ),
            "SW-LAB-02": Equipamento(
                "SW-LAB-02", "switch", "FOC2451X1LAB",
            ),
            "FW-LAB-01": Equipamento(
                "FW-LAB-01", "firewall", "JAD12345LAB",
            ),
        }

    def lista(self) -> list[str]:
        """Os hostnames do parque.

        The fleet's hostnames.
        """
        return sorted(self.equipamentos)

    def consultar(self, hostname: str) -> Equipamento:
        """Devolve um equipamento pelo hostname.

        Return one device by hostname.

        Args:
            hostname: Nome do aparelho.

        Returns:
            O equipamento.

        Raises:
            EquipamentoDesconhecido: Se o hostname nao existir.
        """
        if hostname not in self.equipamentos:
            raise EquipamentoDesconhecido(hostname)
        return self.equipamentos[hostname]

    def avancar(self, ticks: int = 1) -> None:
        """Avanca o relogio do simulador.

        Advance the simulator clock.

        Args:
            ticks: Quantos passos avancar.
        """
        self.tick += ticks

    def alterar(self, hostname: str, linha: str) -> None:
        """Aplica uma mudanca fora do processo.

        Apply an out-of-band change.

        E o drift que o alerta precisa enxergar: alguem entrou no aparelho por
        fora do controle de mudanca e mexeu na configuracao.

        Args:
            hostname: Equipamento alvo.
            linha: Linha de configuracao a acrescentar.

        Raises:
            EquipamentoDesconhecido: Se o hostname nao existir.
        """
        equipamento = self.consultar(hostname)
        if linha not in equipamento.deriva:
            equipamento.deriva.append(linha)

    def reverter(self, hostname: str) -> None:
        """Desfaz toda mudanca fora do processo.

        Revert every out-of-band change.

        Args:
            hostname: Equipamento alvo.
        """
        self.consultar(hostname).deriva.clear()

    # ------------------------------------------------------------------ ruido

    def _volateis(self, equipamento: Equipamento) -> dict[str, object]:
        """Calcula os campos que mudam a cada coleta.

        Compute the fields that change on every collection.

        Tudo aqui e estado do aparelho, nao configuracao: e exatamente o que a
        normalizacao precisa remover.
        """
        rng = random.Random(f"{self.semente}:{equipamento.hostname}:{self.tick}")

        dias = rng.randrange(1, 400)
        horas = rng.randrange(0, 24)
        minutos = rng.randrange(0, 60)

        # A tabela MAC cresce e muda: entradas aprendidas, nao configuradas.
        entradas = []
        for porta in rng.sample(range(1, 24), k=rng.randrange(2, 6)):
            mac = ":".join(f"{rng.randrange(0x100):02X}" for _ in range(6))
            entradas.append(f"  {rng.randrange(400, 8000)}  {mac}  vlan 10   Gi1/0/{porta}")

        return {
            "data": f"{(self.tick % 28) + 1:02d}/01/2026 {rng.randrange(0, 24):02d}:"
                    f"{rng.randrange(0, 60):02d}",
            "uptime": f"!Uptime is {dias} days, {horas} hours, {minutos} minutes",
            "linhas_log": rng.randrange(400, 9000),
            "tabela_mac": "\n".join(entradas) if entradas else " (vazia)",
            "conexoes": "\n".join(
                f"  {rng.randrange(100, 999)} active  {rng.randrange(0, 100)} "
                f"0.0.0.0    {rng.randrange(0, 100)} 0.0.0.0  Gi0/1"
                for _ in range(rng.randrange(1, 4))
            )
            if True
            else "",
        }

    # --------------------------------------------------------------- coleta

    def _renderiza(self, equipamento: Equipamento) -> str:
        """Monta a configuracao de um equipamento no tick atual.

        Build one device's configuration at the current tick.

        Raises:
            ValorAusente: Se o template pedir um campo que nem o tipo nem os
                volateis fornecem. Um ``KeyError`` de ``str.format`` chega ate
                o usuario como traceback de biblioteca, sem dizer qual campo
                faltou nem em qual template; esta excecao diz os dois.
        """
        volateis = self._volateis(equipamento)
        valores = dict(equipamento.base)
        valores.update(volateis)
        # O hostname e o unico campo que os dois templates usam e que nao vem
        # do dicionario base: ele pertence ao equipamento, nao ao modelo dele.
        valores["hostname"] = equipamento.hostname

        try:
            if equipamento.tipo == "switch":
                texto = BASE_SWITCH.format(**valores)
            else:
                texto = BASE_FIREWALL.format(**valores)
        except KeyError as exc:
            faltando = exc.args[0]
            raise ValorAusente(
                f"{equipamento.hostname} ({equipamento.tipo}): o template pede "
                f"o campo {faltando!r}, que nem base nem volateis fornecem"
            ) from exc

        if equipamento.deriva:
            # A deriva entra antes do `end`, como num aparelho real: e uma
            # linha de configuracao como outra qualquer.
            #
            # A quebra de linha precisa vir **antes** da linha acrescentada,
            # e nao depois. Sem o "\n" inicial, o texto terminava em
            # "...lines logged 3990" e a deriva virava continuacao daquela
            # linha: o diff acusaria a mudanca, mas a linha plantada
            # desapareceria do texto da diff, que e a evidencia que o
            # revisor precisa ler. E o pior: a regra de normalizacao do
            # buffer de log casaria a linha inteira e o drift sumiria.
            texto = texto.rsplit("\nend", 1)[0]
            texto += "\n".join(f"\n {linha}" for linha in equipamento.deriva)
            texto += "\nend\n"

        return texto if texto.endswith("\n") else texto + "\n"

    def coletar_snmp(self, hostname: str) -> str:
        """Coleta a configuracao via SNMP ficticio.

        Collect the configuration through the fictitious SNMP interface.

        O SNMP de verdade nao entrega configuracao - entrega **valores de
        MIB**. Por isso a via SNMP aqui devolve uma sintese em texto no mesmo
        formato da via HTTP, e nao um arquivo binario: o ponto do projeto e a
        comparacao, nao o transporte.

        Args:
            hostname: Equipamento alvo.

        Returns:
            A configuracao em texto.
        """
        equipamento = self.consultar(hostname)
        texto = self._renderiza(equipamento)

        cabecalho = (
            f"### colhido via SNMP em {self.tick:04d} "
            f"### serial {equipamento.serial}\n"
        )
        return cabecalho + texto

    def coletar_http(self, hostname: str) -> str:
        """Coleta a configuracao via interface HTTP ficticia.

        Collect the configuration through the fictitious HTTP interface.

        Args:
            hostname: Equipamento alvo.

        Returns:
            A configuracao em texto.
        """
        equipamento = self.consultar(hostname)
        texto = self._renderiza(equipamento)

        cabecalho = (
            f"# exportado via HTTP em {self.tick:04d}\n"
            f"# host: {equipamento.hostname} ({equipamento.tipo})\n"
        )
        return cabecalho + texto

    def coletar(self, hostname: str, via: str = "http") -> str:
        """Coleta a configuracao pela via pedida.

        Collect the configuration over the requested transport.

        Args:
            hostname: Equipamento alvo.
            via: ``http`` ou ``snmp``.

        Returns:
            A configuracao em texto.

        Raises:
            ValueError: Se a via nao for conhecida.
        """
        if via == "snmp":
            return self.coletar_snmp(hostname)
        if via == "http":
            return self.coletar_http(hostname)
        raise ValueError(f"via desconhecida: {via!r} (use 'http' ou 'snmp')")