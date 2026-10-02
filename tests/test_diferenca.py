"""Testes para o modulo diferenca."""

from __future__ import annotations

import pytest

from cfgbackup.diferenca import (
    SEM_MUDANCA,
    ESPERADA,
    INESPERADA,
    Mudanca,
    MudancaEsperada,
    Diff,
    comparar,
)


def test_tres_estados_e_regra_de_alerta():
    """Os tres estados (sem_mudanca, esperada, inesperada) e so a inesperada alerta."""
    # sem_mudanca
    d = comparar("SW-01", "a\nb\nc", "a\nb\nc")
    assert d.estado == SEM_MUDANCA
    assert d.alerta is False

    # esperada
    exp = MudancaEsperada(r"nova.*linha", "mudanca planejada")
    d = comparar("SW-01", "a\nb", "a\nb\nnova linha", esperadas=[exp])
    assert d.estado == ESPERADA
    assert d.alerta is False

    # inesperada
    d = comparar("SW-01", "a\nb", "a\nb\nmudanca nao declarada")
    assert d.estado == INESPERADA
    assert d.alerta is True


def test_mudanca_declarada_nao_vira_alerta_e_carrega_motivo():
    """Uma mudanca declarada nao vira alerta e carrega o motivo."""
    exp = MudancaEsperada(r"interface.*Gigabit", "troca de porta agendada")
    d = comparar("SW-01", "interface GigabitEthernet1/0/1", "interface GigabitEthernet1/0/2", esperadas=[exp])
    assert d.estado == ESPERADA
    assert d.mudancas[0].estado == ESPERADA
    assert d.mudancas[0].motivo == "troca de porta agendada"
    assert d.mudancas[0].alerta is False


def test_expected_casa_por_padrao_regular():
    """Expected casa por padrao regular (regex)."""
    exp = MudancaEsperada(r"vlan\s+\d+", "ajuste de vlan")
    # casa na linha 'depois'
    d = comparar("SW-01", "vlan 10", "vlan 20", esperadas=[exp])
    assert d.mudancas[0].estado == ESPERADA
    # casa na linha 'antes'
    d = comparar("SW-01", "vlan 10", "vlan 10", esperadas=[exp])
    assert d.estado == SEM_MUDANCA  # sem mudanca real
    # nao casa se padrao nao bate
    exp2 = MudancaEsperada(r"vlan\s+99", "vlan gerencia")
    d = comparar("SW-01", "vlan 10", "vlan 20", esperadas=[exp2])
    assert d.mudancas[0].estado == INESPERADA


def test_substituicao_linha_alterada_vira_tipo_substituida():
    """Substituicao quando a linha e alterada vira tipo substituida e nao remocao mais insercao."""
    d = comparar("SW-01", "hostname SW-OLD", "hostname SW-NEW")
    assert len(d.mudancas) == 1
    assert d.mudancas[0].tipo == "substituida"
    assert d.mudancas[0].antes == "hostname SW-OLD"
    assert d.mudancas[0].depois == "hostname SW-NEW"


def test_remocao_pura_e_insercao_pura():
    """Remocao pura e insercao pura."""
    # remocao pura
    d = comparar("SW-01", "a\nb\nc", "a\nc")
    removidas = [m for m in d.mudancas if m.tipo == "removida"]
    assert len(removidas) == 1
    assert removidas[0].antes == "b"
    assert removidas[0].depois is None

    # insercao pura
    d = comparar("SW-01", "a\nc", "a\nb\nc")
    adicionadas = [m for m in d.mudancas if m.tipo == "adicionada"]
    assert len(adicionadas) == 1
    assert adicionadas[0].antes is None
    assert adicionadas[0].depois == "b"


def test_ordem_deterministica_das_mudancas():
    """Ordem deterministica das mudancas (ordenacao natural do SequenceMatcher)."""
    anterior = "a\nb\nc\nd\ne"
    atual = "a\nx\nc\ny\ne"
    d = comparar("SW-01", anterior, atual)
    # Deve vir na ordem em que aparecem no arquivo
    assert [m.antes for m in d.mudancas if m.antes] == ["b", "d"]
    assert [m.depois for m in d.mudancas if m.depois] == ["x", "y"]


def test_quebras_empate_em_diff_estado():
    """Quebras de empate em Diff.estado: inesperada > esperada > sem_mudanca."""
    exp = MudancaEsperada(r"^esperada$", "motivo")
    # mistura: uma esperada e uma inesperada -> estado geral inesperada
    d = comparar("SW-01", "a\nesperada\nc", "a\nesperada modificada\nc\ninesperada", esperadas=[exp])
    assert d.estado == INESPERADA
    # so esperadas -> estado geral esperada
    d = comparar("SW-01", "a\nesperada\nc", "a\nesperada modificada\nc", esperadas=[exp])
    assert d.estado == ESPERADA
    # sem mudancas -> sem_mudanca
    d = comparar("SW-01", "a\nb\nc", "a\nb\nc")
    assert d.estado == SEM_MUDANCA


def test_texto_formato_unified():
    """texto() no formato unified diff."""
    d = comparar("SW-01", "a\nb\nc", "a\nx\nc")
    txt = d.texto()
    assert "--- SW-01 (anterior)" in txt
    assert "+++ SW-01 (atual)" in txt
    assert "-b" in txt
    assert "+x" in txt


def test_texto_ausencia_de_mudancas():
    """texto() com ausencia de mudancas."""
    d = comparar("SW-01", "a\nb\nc", "a\nb\nc")
    assert d.texto() == "sem mudancas"


def test_serializa_para_dict():
    """Serializa para_dict."""
    exp = MudancaEsperada(r"vlan \d+", "mudanca de vlan")
    d = comparar("SW-01", "vlan 10", "vlan 20", esperadas=[exp])
    dct = d.para_dict()
    assert dct["equipamento"] == "SW-01"
    assert dct["estado"] == ESPERADA
    assert dct["alerta"] is False
    assert dct["total_mudancas"] == 1
    assert dct["inesperadas"] == 0
    assert dct["esperadas"] == 1
    m = dct["mudancas"][0]
    assert m["tipo"] == "substituida"
    assert m["estado"] == ESPERADA
    assert m["motivo"] == "mudanca de vlan"


def test_mudanca_esperada_casa_com_qualquer_uma_das_linhas():
    """MudancaEsperada.casa com qualquer uma das linhas (antes ou depois)."""
    exp = MudancaEsperada(r"ip address", "mudanca de ip")
    # casa no 'antes'
    d = comparar("SW-01", "ip address 10.0.0.1", "ip address 10.0.0.2", esperadas=[exp])
    assert d.mudancas[0].estado == ESPERADA
    # casa no 'depois' (padrao so bate no depois)
    exp2 = MudancaEsperada(r"10\.0\.0\.2", "novo ip")
    d = comparar("SW-01", "ip address 10.0.0.1", "ip address 10.0.0.2", esperadas=[exp2])
    assert d.mudancas[0].estado == ESPERADA


def test_lista_de_esperadas_vazia():
    """Lista de esperadas vazia nao quebra e tudo vira inesperada."""
    d = comparar("SW-01", "a\nb", "a\nc", esperadas=[])
    assert d.estado == INESPERADA
    assert d.mudancas[0].estado == INESPERADA
    assert d.mudancas[0].motivo is None