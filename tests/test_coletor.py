"""Testes para o modulo coletor."""

from __future__ import annotations

import pytest
import yaml

from cfgbackup.coletor import (
    ListaInvalida,
    EquipamentoDef,
    Coleta,
    carregar_equipamentos,
    coletar,
    carregar_normalizado,
)
from cfgbackup.simulador import Simulador
from cfgbackup.normalizador import Normalizador


def test_carregar_equipamentos_le_yaml_e_ordena_por_hostname(tmp_path):
    """carregar_equipamentos le o YAML do repositorio e ordena por hostname."""
    conteudo = yaml.safe_dump([
        {"hostname": "SW-B", "tipo": "switch", "via": "http"},
        {"hostname": "SW-A", "tipo": "switch", "via": "snmp"},
    ])
    arq = tmp_path / "equipamentos.yaml"
    arq.write_text(conteudo, encoding="utf-8")

    eqs = carregar_equipamentos(arq)
    assert [e.hostname for e in eqs] == ["SW-A", "SW-B"]


def test_arquivo_inexistente_levanta_lista_invalida():
    """Arquivo inexistente levanta ListaInvalida."""
    with pytest.raises(ListaInvalida, match="arquivo nao encontrado"):
        carregar_equipamentos("/caminho/que/nao/existe.yaml")


def test_yaml_que_nao_e_lista_levanta_lista_invalida(tmp_path):
    """YAML que nao e lista levanta ListaInvalida."""
    arq = tmp_path / "errado.yaml"
    arq.write_text("hostname: SW-01\n", encoding="utf-8")
    with pytest.raises(ListaInvalida, match="deve conter uma lista"):
        carregar_equipamentos(arq)


def test_item_sem_hostname_levanta_lista_invalida(tmp_path):
    """Item sem hostname levanta ListaInvalida."""
    arq = tmp_path / "sem_hostname.yaml"
    arq.write_text(yaml.safe_dump([{"tipo": "switch"}]), encoding="utf-8")
    with pytest.raises(ListaInvalida, match="item sem hostname"):
        carregar_equipamentos(arq)


def test_hostname_repetido_levanta_lista_invalida(tmp_path):
    """Hostname repetido levanta ListaInvalida."""
    arq = tmp_path / "dup.yaml"
    arq.write_text(yaml.safe_dump([
        {"hostname": "SW-01", "tipo": "switch"},
        {"hostname": "SW-01", "tipo": "firewall"},
    ]), encoding="utf-8")
    with pytest.raises(ListaInvalida, match="hostname repetido"):
        carregar_equipamentos(arq)


def test_tipo_invalido_levanta_lista_invalida(tmp_path):
    """Tipo invalido levanta ListaInvalida."""
    arq = tmp_path / "tipo_errado.yaml"
    arq.write_text(yaml.safe_dump([{"hostname": "SW-01", "tipo": "router"}]), encoding="utf-8")
    with pytest.raises(ListaInvalida, match="tipo invalido"):
        carregar_equipamentos(arq)


def test_via_invalida_levanta_lista_invalida(tmp_path):
    """Via invalida levanta ListaInvalida."""
    arq = tmp_path / "via_errada.yaml"
    arq.write_text(yaml.safe_dump([{"hostname": "SW-01", "tipo": "switch", "via": "ssh"}]), encoding="utf-8")
    with pytest.raises(ListaInvalida, match="via invalida"):
        carregar_equipamentos(arq)


def test_coletar_grava_bruto_e_normalizado_por_equipamento(tmp_path):
    """Coletar grava um .txt bruto e um .normalizado.txt por equipamento."""
    sim = Simulador()
    eqs = [EquipamentoDef(hostname="SW-LAB-01", tipo="switch", via="http")]
    coletas = coletar(eqs, simulador=sim, destino=tmp_path)

    assert len(coletas) == 1
    bruto = tmp_path / "SW-LAB-01.txt"
    norm = tmp_path / "SW-LAB-01.normalizado.txt"
    assert bruto.exists()
    assert norm.exists()
    assert bruto.read_text(encoding="utf-8") == coletas[0].bruto
    assert norm.read_text(encoding="utf-8") == coletas[0].normalizado


def test_normalizado_tem_menos_linhas_que_bruto_quando_ha_campo_volatil(tmp_path):
    """O normalizado tem menos linhas que o bruto quando ha campo volatil."""
    sim = Simulador()
    eqs = [EquipamentoDef(hostname="SW-LAB-01", tipo="switch", via="http")]
    coletas = coletar(eqs, simulador=sim, destino=tmp_path)
    c = coletas[0]
    assert c.linhas_normalizadas < c.linhas_brutas


def test_coleta_linhas_removidas_bate_com_a_diferenca(tmp_path):
    """Coleta.linhas_removidas bate com a diferenca entre bruto e normalizado."""
    sim = Simulador()
    eqs = [EquipamentoDef(hostname="SW-LAB-01", tipo="switch", via="http")]
    coletas = coletar(eqs, simulador=sim, destino=tmp_path)
    c = coletas[0]
    assert c.linhas_removidas == c.linhas_brutas - c.linhas_normalizadas


def test_regras_acionadas_nao_vem_vazio(tmp_path):
    """regras_acionadas nao vem vazio (o simulador injeta campos volatis)."""
    sim = Simulador()
    eqs = [EquipamentoDef(hostname="SW-LAB-01", tipo="switch", via="http")]
    coletas = coletar(eqs, simulador=sim, destino=tmp_path)
    c = coletas[0]
    assert len(c.regras_acionadas) > 0
    # Verifica se regras conhecidas estao presentes
    assert any(r in c.regras_acionadas for r in ("uptime", "tabela-mac", "cabecalho-de-coleta"))


def test_carregar_normalizado_le_os_arquivos(tmp_path):
    """carregar_normalizado le os arquivos normalizados do diretorio."""
    sim = Simulador()
    eqs = [
        EquipamentoDef(hostname="SW-LAB-01", tipo="switch", via="http"),
        EquipamentoDef(hostname="SW-LAB-02", tipo="switch", via="http"),
    ]
    coletar(eqs, simulador=sim, destino=tmp_path)

    mapa = carregar_normalizado(tmp_path)
    assert set(mapa.keys()) == {"SW-LAB-01", "SW-LAB-02"}
    assert all(isinstance(v, str) and len(v) > 0 for v in mapa.values())


def test_diretorio_sem_arquivos_normalizados_levanta_lista_invalida(tmp_path):
    """Diretorio sem arquivos normalizados levanta ListaInvalida."""
    with pytest.raises(ListaInvalida, match="nenhum arquivo .normalizado.txt"):
        carregar_normalizado(tmp_path)


def test_destino_inexistente_e_criado(tmp_path):
    """Destino inexistente e criado pelo coletar."""
    novo = tmp_path / "novo" / "subdir"
    assert not novo.exists()
    sim = Simulador()
    eqs = [EquipamentoDef(hostname="SW-LAB-01", tipo="switch", via="http")]
    coletar(eqs, simulador=sim, destino=novo)
    assert novo.exists()
    assert (novo / "SW-LAB-01.txt").exists()
    assert (novo / "SW-LAB-01.normalizado.txt").exists()