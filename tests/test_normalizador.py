from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from cfgbackup.normalizador import (
    REGRAS_PADRAO,
    Regra,
    RegraDuplicada,
    Normalizador,
    _agrupa_repetidas,
    REMOVER,
    SUBSTITUIR,
    PRESERVAR,
)


class TestAgrupaRepetidas:
    """Testa _agrupa_repetidas: fusao de repeticoes consecutivas."""

    def test_lista_vazia(self):
        """Lista vazia retorna lista vazia."""
        assert _agrupa_repetidas([]) == []

    def test_sem_repeticao(self):
        """Linhas unicas permanecem inalteradas."""
        assert _agrupa_repetidas(["a\n", "b\n", "c\n"]) == ["a\n", "b\n", "c\n"]

    def test_repeticao_consecutiva_vira_uma(self):
        """Bloco de linhas iguais consecutivas vira uma unica linha."""
        assert _agrupa_repetidas(["x\n"] * 3) == ["x\n"]

    def test_linhas_iguais_nao_consecutivas_nao_sao_fundidas(self):
        """Linhas iguais separadas por outras continuam separadas."""
        linhas = ["a\n", "b\n", "a\n"]
        assert _agrupa_repetidas(linhas) == ["a\n", "b\n", "a\n"]

    def test_mistura_blocos_e_singletons(self):
        """Mistura de repeticoes e linhas unicas e tratada corretamente."""
        linhas = ["a\n", "b\n", "b\n", "c\n", "c\n", "c\n"]
        assert _agrupa_repetidas(linhas) == ["a\n", "b\n", "c\n"]

    def test_preserva_newline_da_primeira_ocorrencia(self):
        """O terminador da primeira linha do bloco e mantido."""
        assert _agrupa_repetidas(["ok\n", "ok\n"]) == ["ok\n"]

    def test_sem_newline_e_mantido_sem_newline(self):
        """Linhas sem terminador continuam sem terminador apos fusao."""
        assert _agrupa_repetidas(["ok", "ok"]) == ["ok"]

    def test_linha_vazia_consecutiva(self):
        """Linhas vazias consecutivas sao fundidas."""
        assert _agrupa_repetidas(["", "", ""]) == [""]

    def test_mistura_com_linha_vazia(self):
        """Linha vazia entre nao-vazias e preservada."""
        assert _agrupa_repetidas(["a\n", "\n", "b\n"]) == ["a\n", "\n", "b\n"]


class TestRegraDuplicada:
    """Testa deteccao de nomes de regra duplicados."""

    def test_nome_repetido_levanta_excecao(self):
        """Regras com mesmo nome levantam RegraDuplicada."""
        with pytest.raises(RegraDuplicada) as exc:
            Normalizador([
                Regra("dup", r"a", REMOVER, "m1"),
                Regra("dup", r"b", REMOVER, "m2"),
            ])
        assert exc.value.nome == "dup"

    def test_regra_duplicada_e_value_error(self):
        """RegraDuplicada e subclasse de ValueError."""
        with pytest.raises(ValueError):
            Normalizador([Regra("r", r"a", REMOVER, "m"), Regra("r", r"b", REMOVER, "m")])

    def test_mensagem_contem_nome(self):
        """Mensagem da excecao inclui o nome duplicado."""
        with pytest.raises(RegraDuplicada, match="regra duplicada: x"):
            Normalizador([Regra("x", r"a", REMOVER, "m"), Regra("x", r"b", REMOVER, "m")])


class TestNormalizadorInit:
    """Testa inicializacao do Normalizador."""

    def test_default_usar_regras_padrao(self):
        """Sem argumentos, Normalizador usa REGRAS_PADRAO."""
        n = Normalizador()
        assert n.regras == REGRAS_PADRAO

    def test_regras_customizadas(self):
        """Regras customizadas sao armazenadas."""
        custom = (Regra("unica", r"foo", REMOVER, "motivo"),)
        assert Normalizador(custom).regras == custom


class TestNormalizar:
    """Testa Normalizador.normalizar e normalizar_linhas."""

    def test_texto_vazio(self):
        """Texto vazio devolve texto vazio."""
        assert Normalizador().normalizar("") == ""

    def test_linha_sem_match_fica_intacta(self):
        """Linhas que nao casam com nenhuma regra sao preservadas."""
        n = Normalizador()
        texto = "hostname SW1\ninterface GigabitEthernet0/1\n"
        assert n.normalizar(texto) == texto

    def test_regra_remover_elimina_linha(self):
        """Regra remover retira a linha completamente."""
        n = Normalizador()
        assert n.normalizar("!Last configuration change at 12:34 BRST\n") == ""

    def test_regra_substituir_altera_linha(self):
        """Regra substituir troca o conteudo pelo placeholder."""
        n = Normalizador()
        assert n.normalizar("Uptime: 3 days\n") == "<UPTIME NORMALIZADO>\n"

    def test_ordem_define_qual_regra_casa(self):
        """A primeira regra que casa vence; inverter a ordem inverte o resultado."""
        texto = "foo bar\n"
        regras_especifica_primeiro = (
            Regra("especifica", r"^foo bar$", SUBSTITUIR, "m1", substituicao="<ESPECIFICA>"),
            Regra("geral", r"^foo.*$", SUBSTITUIR, "m2", substituicao="<GERAL>"),
        )
        assert Normalizador(regras_especifica_primeiro).normalizar(texto) == "<ESPECIFICA>\n"

        regras_geral_primeiro = (
            Regra("geral", r"^foo.*$", SUBSTITUIR, "m2", substituicao="<GERAL>"),
            Regra("especifica", r"^foo bar$", SUBSTITUIR, "m1", substituicao="<ESPECIFICA>"),
        )
        assert Normalizador(regras_geral_primeiro).normalizar(texto) == "<GERAL>\n"

    def test_preserva_quebra_de_linha(self):
        """Linha com newline continua com newline apos substituicao."""
        n = Normalizador()
        assert n.normalizar("Uptime: 1 day\n") == "<UPTIME NORMALIZADO>\n"

    def test_ultima_linha_sem_newline(self):
        """Ultima linha sem newline e normalizada sem adicionar newline."""
        n = Normalizador()
        assert n.normalizar("Uptime: 1 day") == "<UPTIME NORMALIZADO>"

    def test_linha_normalizada_igual_e_consecutive_e_fundida(self):
        """Linhas normalizadas para o mesmo placeholder sao fundidas."""
        texto = "  <TABELA MAC>\n  <TABELA MAC>\n"
        n = Normalizador()
        assert n.normalizar(texto) == "  <TABELA MAC>\n"

    def test_linhas_iguais_nao_consecutivas_nao_sao_fundidas(self):
        """Linhas de configuracao iguais separadas por outras nao sao fundidas."""
        n = Normalizador()
        texto = "interface GigabitEthernet0/1\ndescription A\ninterface GigabitEthernet0/1\n"
        assert n.normalizar(texto) == texto

    def test_mistura_remover_e_substituir(self):
        """Regras de remover e substituir atuam juntas corretamente."""
        n = Normalizador()
        texto = "hostname SW1\n!Software Version 17.3\n Uptime: 1 day\ninterface Gi0/1\n"
        resultado = n.normalizar(texto)
        assert "hostname SW1\n" in resultado
        assert "interface Gi0/1\n" in resultado
        assert "!Software Version" not in resultado
        assert "<UPTIME NORMALIZADO>" in resultado

    def test_padrao_que_nao_casa_deixa_linha(self):
        """Padrao que nao casa com a linha deixa a linha intacta."""
        n = Normalizador()
        texto = "linha generica que nao casa\n"
        assert n.normalizar(texto) == texto

    def test_normalizar_linhas_aceita_iteravel(self):
        """normalizar_linhas aceita qualquer iteravel, nao so listas."""
        n = Normalizador()
        gerador = (linha for linha in ["Uptime: 1 day\n", "hostname SW1\n"])
        resultado = n.normalizar_linhas(gerador)
        assert resultado == ["<UPTIME NORMALIZADO>\n", "hostname SW1\n"]

    def test_apenas_newlines(self):
        """Sequencia de newlines identicas e fundida em uma."""
        n = Normalizador()
        assert n.normalizar("\n\n") == "\n"

    def test_remover_nao_deixa_linha_vazia_fantasma(self):
        """Linha removida some completamente, sem newline fantasma."""
        n = Normalizador()
        assert n.normalizar("!Software Version 17.3\n") == ""


class TestRegrasQueAgiram:
    """Testa Normalizador.regras_que_agiram."""

    def test_texto_vazio(self):
        """Texto vazio retorna lista vazia."""
        assert Normalizador().regras_que_agiram("") == []

    def test_sem_match(self):
        """Texto sem regras que casam retorna lista vazia."""
        n = Normalizador()
        assert n.regras_que_agiram("hostname SW1\ninterface Gi0/1\n") == []

    def test_sem_repeticao_mesmo_com_varias_linhas(self):
        """Cada regra aparece uma unica vez, mesmo casando varias linhas."""
        texto = "!Software Version 17.3\n!NVRAM config last updated at 12:00\n"
        n = Normalizador()
        resultado = n.regras_que_agiram(texto)
        assert resultado == ["versao-do-sistema", "data-nvram"]
        assert len(resultado) == len(set(resultado))

    def test_ordem_da_tabela_nao_da_ocorrencia(self):
        """Regras sao listadas na ordem da tabela, nao da ocorrencia no texto."""
        texto = "!NVRAM config last updated at 12:00\n!Software Version 17.3\n"
        n = Normalizador()
        resultado = n.regras_que_agiram(texto)
        assert resultado.index("data-nvram") < resultado.index("versao-do-sistema")

    def test_search_nao_match(self):
        """Usa search, entao padrao sem ^ casa em qualquer posicao."""
        regras = (Regra("busca", r"Uptime", SUBSTITUIR, "m", substituicao="<X>"),)
        n = Normalizador(regras)
        assert n.regras_que_agiram("tempo: Uptime aqui\n") == ["busca"]


class TestMotivoDa:
    """Testa Normalizador.motivo_da."""

    def test_retorna_motivo(self):
        """Retorna motivo da regra pelo nome."""
        n = Normalizador()
        motivo = n.motivo_da("uptime")
        assert isinstance(motivo, str)
        assert len(motivo) > 0

    def test_nome_inexistente_levanta_key_error(self):
        """Nome inexistente levanta KeyError."""
        n = Normalizador()
        with pytest.raises(KeyError):
            n.motivo_da("nao-existe-decimal")

    def test_key_error_contem_nome(self):
        """KeyError inclui o nome da regra inexistente."""
        n = Normalizador()
        with pytest.raises(KeyError, match="nao-existe-decimal"):
            n.motivo_da("nao-existe-decimal")


class TestTabela:
    """Testa Normalizador.tabela."""

    def test_quantidade_de_regras(self):
        """Exporta uma entrada por regra."""
        assert len(Normalizador().tabela()) == len(REGRAS_PADRAO)

    def test_chaves_obrigatorias(self):
        """Cada entrada tem nome, acao, padrao e motivo."""
        for entrada in Normalizador().tabela():
            assert set(entrada.keys()) == {"nome", "acao", "padrao", "motivo"}

    def test_valores_iguais_aos_originais(self):
        """Valores exportados correspondem as regras originais."""
        for entrada, regra in zip(Normalizador().tabela(), REGRAS_PADRAO):
            assert entrada["nome"] == regra.nome
            assert entrada["acao"] == regra.acao
            assert entrada["padrao"] == regra.padrao
            assert entrada["motivo"] == regra.motivo

    def test_ordem_preservada(self):
        """Ordem das regras na exportacao e a mesma da tabela original."""
        nomes = [e["nome"] for e in Normalizador().tabela()]
        assert nomes == [r.nome for r in REGRAS_PADRAO]


class TestRegrasPadrao:
    """Testa cada regra individual da tabela padrao."""

    def test_data_ultima_mudanca_removida(self):
        """Remove !Last configuration change at ..."""
        n = Normalizador()
        assert n.normalizar("!Last configuration change at 12:34 BRST\n") == ""

    def test_data_nvram_removida(self):
        """Remove !NVRAM config last updated at ..."""
        n = Normalizador()
        assert n.normalizar("!NVRAM config last updated at 12:00 BRST\n") == ""

    def test_comentario_flash_removido(self):
        """Remove comentario de marcacao flash."""
        n = Normalizador()
        assert n.normalizar("!configuration from flash: bootflash:.safe\n") == ""

    def test_comentario_flash_from_removido(self):
        """Remove comentario com 'configuration from flash'."""
        n = Normalizador()
        assert n.normalizar("!configuration from flash: bootflash:.safe\n") == ""

    def test_versao_sistema_removida(self):
        """Remove !Software Version ..."""
        n = Normalizador()
        assert n.normalizar("!Software Version 17.3.5\n") == ""

    def test_uptime_substituida(self):
        """Substitui Uptime: ..."""
        n = Normalizador()
        assert n.normalizar("Uptime: 1 day\n") == "<UPTIME NORMALIZADO>\n"

    def test_uptime_com_exclamacao_substituida(self):
        """Substitui !Uptime is ..."""
        n = Normalizador()
        assert n.normalizar("!Uptime is 12345 seconds\n") == "<UPTIME NORMALIZADO>\n"

    def test_uptime_snmp_agent_substituida(self):
        """Substitui !SNMP agent Uptime is ..."""
        n = Normalizador()
        assert n.normalizar("!SNMP agent Uptime is 12345\n") == "<UPTIME NORMALIZADO>\n"

    def test_tempo_relogio_substituido(self):
        """Substitui Time source is ..."""
        n = Normalizador()
        assert n.normalizar("Time source is NTP\n") == "Time source is <ORIGEM NORMALIZADA>\n"

    def test_numero_serie_substituido(self):
        """Substitui serial ... mantendo prefixo."""
        n = Normalizador()
        texto = " serial ABC 99A12345678\n"
        resultado = n.normalizar(texto)
        assert "serial ABC " in resultado
        assert "<APARELHO>" in resultado
        assert "<SERIE NORMALIZADA>" in resultado

    def test_hash_senha_substituido(self):
        """Substitui password/secret hash."""
        n = Normalizador()
        texto = " username admin password 0 mysecret\n"
        resultado = n.normalizar(texto)
        assert "username admin password 0 " in resultado
        assert "<HASH OCULTO>" in resultado

    def test_hash_secret_substituido(self):
        """Substitui secret hash."""
        n = Normalizador()
        texto = " username admin secret 5 myhash\n"
        resultado = n.normalizar(texto)
        assert "username admin secret 5 " in resultado
        assert "<HASH OCULTO>" in resultado

    def test_chave_criptografica_substituida(self):
        """Substitui snmp-server community."""
        n = Normalizador()
        texto = " snmp-server community public RO\n"
        resultado = n.normalizar(texto)
        assert "snmp-server community public " in resultado
        assert "<SEGREDO OCULTO>" in resultado

    def test_cabecalho_snmp_removido(self):
        """Remove cabecalho de coleta SNMP."""
        n = Normalizador()
        assert n.normalizar("### colhido via SNMP em 123456\n") == ""

    def test_cabecalho_http_removido(self):
        """Remove cabecalho de coleta HTTP."""
        n = Normalizador()
        assert n.normalizar("# exportado via HTTP em 123456\n") == ""

    def test_tabela_mac_substituida(self):
        """Substitui entrada de tabela MAC."""
        n = Normalizador()
        texto = " 1 0001.0002.0003 Gi0/1\n"
        resultado = n.normalizar(texto)
        assert "<TABELA MAC>" in resultado

    def test_sessao_substituida(self):
        """Substitui linha de sessao ativa."""
        n = Normalizador()
        texto = " 1 active 0x1234\n"
        resultado = n.normalizar(texto)
        assert "<SESSAO>" in resultado

    def test_contador_pacotes_substituido(self):
        """Substitui contador de pacotes."""
        n = Normalizador()
        texto = " 123 packets input, 456 packets output\n"
        resultado = n.normalizar(texto)
        assert "<CONTADOR NORMALIZADO>" in resultado

    def test_memoria_substituida(self):
        """Substitui linha de memoria."""
        n = Normalizador()
        texto = "Free Memory: 12345 kB\n"
        resultado = n.normalizar(texto)
        assert "Free Memory:" in resultado
        assert "<MEMORIA NORMALIZADA>" in resultado

    def test_buffer_log_substituido(self):
        """Substitui contagem de buffer de log."""
        n = Normalizador()
        texto = " logging buffer: 1000 lines logged 500\n"
        resultado = n.normalizar(texto)
        assert "<CONTADOR NORMALIZADO>" in resultado


class TestCasosFalha:
    """Testa casos de falha, entrada invalida e casos extremos."""

    def test_regex_invalido_levanta_erro(self):
        """Regex invalido levanta re.error ao compilar durante normalizacao."""
        regra = Regra("ruim", r"[invalid(", REMOVER, "teste")
        n = Normalizador([regra])
        with pytest.raises(re.error):
            n.normalizar_linhas(["qualquer texto\n"])

    def test_texto_vazio_nao_levanta(self):
        """normalizar aceita string vazia sem excecao."""
        assert Normalizador().normalizar("") == ""

    def test_padrao_sem_correspondencia(self):
        """Linha que nao casa com nenhuma regra permanece inalterada."""
        n = Normalizador()
        original = "linha qualquer sem regra\n"
        assert n.normalizar(original) == original
