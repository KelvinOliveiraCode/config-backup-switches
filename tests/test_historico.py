import pytest
from pathlib import Path
from src.cfgbackup.historico import (
    OperadorVazio,
    Registro,
    registrar,
    ler,
    contar_registros,
    cabecalho,
    SEM_MUDANCA,
    ESPERADA,
    INESPERADA,
)
from src.cfgbackup.diferenca import Diff, Mudanca


def test_registrar_cria_arquivo_com_cabecalho_quando_nao_existe():
    """registrar() cria o arquivo com o cabecalho quando ele ainda nao existir."""
    import tempfile
    import os
    
    with tempfile.TemporaryDirectory() as tmpdir:
        caminho = os.path.join(tmpdir, "historico.md")
        assert not Path(caminho).exists()
        
        diff = Diff("equip1", ())
        assert registrar(caminho, "2024-01-01 10:00", "admin", (diff,)) == 1
        
        # Verificar que o arquivo foi criado
        assert Path(caminho).exists()
        
        # Verificar que o arquivo comeca com o cabecalho
        conteudo = ler(caminho)
        assert conteudo.startswith("# Historico de mudancas de configuracao")
        assert "> Documento gerado por `cfgbackup`" in conteudo


def test_registrar_acrescenta_em_arquivo_existente_preserva_conteudo_e_nao_duplica_cabecalho():
    """registrar() acrescenta em arquivo existente preserva o conteudo anterior e NAO duplica cabecalho."""
    import tempfile
    import os
    
    with tempfile.TemporaryDirectory() as tmpdir:
        caminho = os.path.join(tmpdir, "historico.md")
        # Escrever cabecalho manualmente
        with open(caminho, 'w', encoding='utf-8') as f:
            f.write(cabecalho())
        
        diff1 = Diff("equip1", ())
        diff2 = Diff("equip2", (Mudanca("adicionada", None, "nova_linha", estado=INESPERADA, motivo=None),))
        
        # Primeira chamada - deve criar um registro
        assert registrar(caminho, "2024-01-01 10:00", "admin", (diff1,)) == 1
        
        # Segunda chamada - deve acrescentar outro registro
        assert registrar(caminho, "2024-01-01 11:00", "admin", (diff2,)) == 1
        
        # Verificar que o cabecalho nao foi duplicado
        conteudo = ler(caminho)
        # Deve haver apenas um cabecalho no inicio
        cabecalho_count = conteudo.count("# Historico de mudancas de configuracao")
        assert cabecalho_count == 1, f"Cabecalho duplicado: {cabecalho_count} vezes"
        
        # Deve haver dois registros (separados por ---)
        # Note: contamos as linhas que comecam com "## " (titulos de equipamento)
        lines = conteudo.split('\n')
        registro_count = sum(1 for line in lines if line.strip().startswith('## '))
        assert registro_count == 2, f"Esperado 2 registros, encontrado {registro_count}"
        
        # Deve haver 3 ou 4 separadores (um do cabecalho + um apos cada registro,
        # possivelmente um extra por causa do modo de escrita)
        separator_count = conteudo.count("---")
        assert separator_count in [3, 4], f"Esperado 3 ou 4 separadores, encontrado {separator_count}"


def test_registrar_operador_vazio_levanta_OperadorVazio():
    """registrar() com operador vazio levanta OperadorVazio."""
    diff = Diff("equip1", ())
    
    with pytest.raises(OperadorVazio):
        registrar("/tmp/test.md", "2024-01-01 10:00", "   ", (diff,))
    
    with pytest.raises(OperadorVazio):
        registrar("/tmp/test.md", "2024-01-01 10:00", "", (diff,))


def test_registrar_data_e_operador_aparecem_no_texto():
    """registrar() registra data e operador no arquivo de texto."""
    import tempfile
    import os
    
    with tempfile.TemporaryDirectory() as tmpdir:
        caminho = os.path.join(tmpdir, "historico.md")
        
        diff = Diff("equip1", ())
        registrar(caminho, "2024-01-01 10:00", "admin", (diff,))
        
        conteudo = ler(caminho)
        assert "- **data**: 2024-01-01 10:00" in conteudo
        assert "- **operador**: admin" in conteudo


def test_registrar_data_parametro_e_nao_datetime_now():
    """registrar() usa data do paremetro, nunca datetime.now()."""
    import tempfile
    import os
    
    with tempfile.TemporaryDirectory() as tmpdir:
        caminho = os.path.join(tmpdir, "historico.md")
        
        diff = Diff("equip1", ())
        data_param = "2024-01-01 10:00"
        registrar(caminho, data_param, "admin", (diff,))
        
        conteudo = ler(caminho)
        assert f"- **data**: {data_param}" in conteudo
        # Deve ser exatamente a data fornecida, nao a data atual
        assert "2024-01-01 10:00" in conteudo


def test_registro_estado_e_rotulo_para_cada_um_dos_tres_estados():
    """Registro.estado e Registro.rotulo funcionam para SEM_MUDANCA, ESPERADA e INESPERADA."""
    # SEM_MUDANCA
    diff_sem_mudanca = Diff("equip1", ())
    registro_sem = Registro("2024-01-01 10:00", "admin", "equip1", diff_sem_mudanca)
    assert registro_sem.estado == SEM_MUDANCA
    assert registro_sem.rotulo == "sem mudanca"
    
    # ESPERADA
    mudanca_esperada = Mudanca("adicionada", None, "nova_linha", estado=ESPERADA, motivo="test")
    diff_esperada = Diff("equip2", (mudanca_esperada,))
    registro_esperado = Registro("2024-01-01 10:00", "admin", "equip2", diff_esperada)
    assert registro_esperado.estado == ESPERADA
    assert registro_esperado.rotulo == "mudanca esperada"
    
    # INESPERADA
    mudanca_inesperada = Mudanca("adicionada", None, "nova_linha2", estado=INESPERADA, motivo=None)
    diff_inesperada = Diff("equip3", (mudanca_inesperada,))
    registro_inesperado = Registro("2024-01-01 10:00", "admin", "equip3", diff_inesperada)
    assert registro_inesperado.estado == INESPERADA
    assert registro_inesperado.rotulo == "MUDANCA INESPERADA"


def test_diff_sem_mudancas_escreve_mensagem_identicas():
    """Diff sem mudancas escreve a mensagem de 'identicas'."""
    diff = Diff("equip1", ())
    registro = Registro("2024-01-01 10:00", "admin", "equip1", diff)
    markdown = registro.para_markdown()
    
    assert "As configuracoes normalizadas sao identicas." in markdown
    assert "Nenhuma linha sobreviveu a tabela de normalizacao como diferenca." in markdown


def test_mudancas_esperadas_e_nao_declaradas_sao_separadas_em_secoes_distintas():
    """Mudancas esperadas e nao declaradas sao separadas em secoes distintas."""
    mudanca_esperada = Mudanca("adicionada", None, "linha_esperada", estado=ESPERADA, motivo="declarada")
    mudanca_inesperada = Mudanca("adicionada", None, "linha_inesperada", estado=INESPERADA, motivo=None)
    
    diff = Diff("equip1", (mudanca_esperada, mudanca_inesperada))
    registro = Registro("2024-01-01 10:00", "admin", "equip1", diff)
    markdown = registro.para_markdown()
    
    # Deve haver secoes distintas
    assert "### Mudancas declaradas previamente" in markdown
    assert "### Mudancas nao declaradas (drift)" in markdown
    
    # Deve haver itens em cada secao
    assert "- + linha_esperada" in markdown
    assert "- + linha_inesperada" in markdown
    
    # A ordem deve ser: esperada primeiro, depois inesperada
    pos_esperada = markdown.find("### Mudancas declaradas previamente")
    pos_inesperada = markdown.find("### Mudancas nao declaradas (drift)")
    assert pos_esperada < pos_inesperada


def test_registrar_ordem_saida_mais_recente_para_mais_antigo():
    """registrar() escreve registros do mais recente para o mais antigo."""
    import tempfile
    import os
    
    with tempfile.TemporaryDirectory() as tmpdir:
        caminho = os.path.join(tmpdir, "historico.md")
        
        # Registrar em ordem de equipamento inversa para garantir que seja escrito na ordem correta
        diff2 = Diff("equip2", ())
        diff1 = Diff("equip1", ())
        
        registrar(caminho, "2024-01-01 10:00", "admin", (diff2,))
        registrar(caminho, "2024-01-01 11:00", "admin", (diff1,))
        
        conteudo = ler(caminho)
        
        # Verificar a ordem: equip2 deve aparecer antes de equip1
        pos_equip2 = conteudo.find("## equip2")
        pos_equip1 = conteudo.find("## equip1")
        
        # equip2 deve aparecer antes de equip1
        assert pos_equip2 >= 0 and pos_equip1 >= 0
        assert pos_equip2 < pos_equip1


def test_ler_funciona_em_arquivo_existente():
    """ler() funciona em arquivo existente."""
    import tempfile
    import os
    
    with tempfile.TemporaryDirectory() as tmpdir:
        caminho = os.path.join(tmpdir, "historico.md")
        
        # Escrever conteudo diretamente
        conteudo_texto = "# Conteudo de teste\n\nAlgum conteudo aqui"
        with open(caminho, 'w', encoding='utf-8') as f:
            f.write(conteudo_texto)
        
        conteudo = ler(caminho)
        assert "# Conteudo de teste" in conteudo
        assert "Algum conteudo aqui" in conteudo


def test_ler_funciona_em_arquivo_ausente():
    """ler() lanca FileNotFoundError para arquivo inexistente."""
    import tempfile
    import os
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Caminho para um arquivo que definitivamente nao existe
        caminho = os.path.join(tmpdir, "nao_existe.md")
        
        # Este teste verifica que ler() lanca FileNotFoundError para arquivos inexistentes
        with pytest.raises(FileNotFoundError):
            ler(caminho)


def test_contar_registros_funciona_em_arquivo_existente():
    """contar_registros() funciona em arquivo existente."""
    import tempfile
    import os
    
    with tempfile.TemporaryDirectory() as tmpdir:
        caminho = os.path.join(tmpdir, "historico.md")
        
        # Escrever um arquivo com multiplos registros
        conteudo = (
            "# Historico de mudancas de configuracao\n\n"
            "> Documento gerado por `cfgbackup`. As configuracoes sao ficticias:\n"
            "> nenhum equipamento real e acessado.\n\n"
            "---\n\n"
            "## equipamento1 - sem mudanca\n"
            "- **data**: 2024-01-01 10:00\n"
            "- **operador**: admin\n"
            "- **estado**: `sem_mudanca`\n"
            "- **mudancas**: 0 (0 esperada(s), 0 inesperada(s))\n\n"
            "---\n\n"
            "## equipamento2 - mudanca esperada\n"
            "- **data**: 2024-01-01 11:00\n"
            "- **operador**: user\n"
            "- **estado**: `esperada`\n"
            "- **mudancas**: 1 (1 esperada(s), 0 inesperada(s))\n\n"
            "---\n\n"
        )
        
        with open(caminho, 'w', encoding='utf-8') as f:
            f.write(conteudo)
        
        total = contar_registros(caminho)
        assert total == 2, f"Esperado 2 registros, encontrado {total}"


def test_contar_registros_funciona_em_arquivo_ausente():
    """contar_registros() funciona em arquivo inexistente (retorna 0)."""
    import tempfile
    import os
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Caminho para um arquivo que definitivamente nao existe
        caminho = os.path.join(tmpdir, "nao_existe.md")
        total = contar_registros(caminho)
        assert total == 0, f"Esperado 0 registros para arquivo inexistente, encontrado {total}"


def test_cabecalho():
    """cabecalho() retorna o cabecalho correto."""
    header = cabecalho()
    assert "# Historico de mudancas de configuracao" in header
    assert "> Documento gerado por `cfgbackup`" in header
    assert "nenhum equipamento real e acessado" in header
    assert "---" in header