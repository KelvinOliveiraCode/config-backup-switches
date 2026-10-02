"""Testes da linha de comando do cfgbackup.

CLI tests.

A CLI e a superficie que o portfolio mostra primeiro, entao os testes aqui
nao verificam so o codigo de retorno: eles verificam que a **saida em texto**
e a que o README promete, incluindo o caso em que duas coletas sem alteracao
qualquer precisam sair limpas.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cfgbackup.cli import construir_parser, main
from cfgbackup.historico import contar_registros

RAIZ = Path(__file__).resolve().parent.parent
YAML_EQUIPAMENTOS = RAIZ / "dados" / "equipamentos.yaml"


def _coletar(destino: Path, ticks: int) -> Path:
    """Rode a coleta de verdade e devolve o diretorio.

    Run a real collection and return the directory.
    """
    codigo = main([
        "coletar",
        "--equipamentos", str(YAML_EQUIPAMENTOS),
        "--saida", str(destino),
        "--ticks", str(ticks),
    ])
    assert codigo == 0
    return destino


def _coletar_com_drift(destino: Path, linha: str) -> tuple[Path, Path]:
    """Duas coletas com uma linha plantada na segunda.

    Duas coletas do simulador nunca divergem: sem alteracao, a demonstracao de
    que uma mudanca declarada nao alerta e vazia. A diferenca precisa existir
    para o teste ter o que provar.
    """
    anterior = _coletar(destino / "a", 7)
    atual = _coletar(destino / "b", 9)

    alvo = atual / "SW-LAB-01.normalizado.txt"
    alvo.write_text(
        alvo.read_text(encoding="utf-8") + linha + "\n", encoding="utf-8"
    )
    return anterior, atual


class TestColetar:
    """A coleta pela linha de comando."""

    def test_gera_arquivos(self, tmp_path: Path, capsys) -> None:
        destino = _coletar(tmp_path / "saida", 7)
        # O glob *.txt tambem pega os normalizados, porque o sufixo termina em
        # .txt. Sao dois arquivos por equipamento, nao tres.
        normalizados = list(destino.glob("*.normalizado.txt"))
        brutos = [p for p in destino.glob("*.txt") if not p.name.endswith(".normalizado.txt")]
        assert len(brutos) == 3
        assert len(normalizados) == 3

    def test_relatorio_no_terminal(self, tmp_path: Path, capsys) -> None:
        _coletar(tmp_path / "saida", 7)
        saida = capsys.readouterr().out
        assert "coleta de 3 equipamento(s)" in saida
        assert "regras de normalizacao acionadas" in saida
        assert "nenhum equipamento real foi acessado" in saida

    def test_numeros_de_linha_batem(self, tmp_path: Path, capsys) -> None:
        _coletar(tmp_path / "saida", 7)
        saida = capsys.readouterr().out
        # Cada equipamento mostra "brutas -> normalizadas (removidas)".
        assert saida.count("normalizadas") == 3
        assert "removidas" in saida

    def test_cria_diretorio(self, tmp_path: Path) -> None:
        destino = tmp_path / "a" / "b" / "c"
        _coletar(destino, 7)
        assert destino.exists()

    def test_yaml_de_equipamentos_padrao(self, tmp_path: Path) -> None:
        # Sem --equipamentos, a CLI usa dados/equipamentos.yaml do cwd.
        assert main(["coletar", "--saida", str(tmp_path / "s"), "--ticks", "7"]) == 0

    def test_yaml_inexistente(self, tmp_path: Path, capsys) -> None:
        codigo = main([
            "coletar", "--equipamentos", str(tmp_path / "nao-existe.yaml"),
            "--saida", str(tmp_path / "s"),
        ])
        assert codigo == 2
        assert "Erro" in capsys.readouterr().err

    def test_inventario_vazio(self, tmp_path: Path, capsys) -> None:
        vazio = tmp_path / "vazio.yaml"
        vazio.write_text("[]\n", encoding="utf-8")
        codigo = main([
            "coletar", "--equipamentos", str(vazio),
            "--saida", str(tmp_path / "s"),
        ])
        assert codigo == 2
        assert "nenhum equipamento declarado" in capsys.readouterr().err

    def test_hostname_que_nao_existe(self, tmp_path: Path, capsys) -> None:
        # A lista e a fonte da verdade. Um hostname a mais e erro de inventario.
        lista = tmp_path / "l.yaml"
        lista.write_text(
            "- hostname: SW-QUE-NAO-EXISTE\n  tipo: switch\n  via: http\n",
            encoding="utf-8",
        )
        codigo = main([
            "coletar", "--equipamentos", str(lista),
            "--saida", str(tmp_path / "s"),
        ])
        assert codigo == 2
        assert "Erro" in capsys.readouterr().err

    def test_saida_deterministica(self, tmp_path: Path) -> None:
        # Mesma semente e mesmo tick tem de dar os mesmos bytes: e o que
        # permite um exemplo versionado e um git diff utilizavel.
        a = tmp_path / "a"
        b = tmp_path / "b"
        main(["coletar", "--saida", str(a), "--ticks", "7"])
        main(["coletar", "--saida", str(b), "--ticks", "7"])
        for arquivo in sorted(a.glob("*.normalizado.txt")):
            assert arquivo.read_bytes() == (b / arquivo.name).read_bytes()

    def test_ticks_diferente_muda_o_bruto(self, tmp_path: Path) -> None:
        a = tmp_path / "a"
        b = tmp_path / "b"
        main(["coletar", "--saida", str(a), "--ticks", "7"])
        main(["coletar", "--saida", str(b), "--ticks", "8"])
        brutos = sorted(a.glob("*.txt"))
        brutos = [p for p in brutos if not p.name.endswith(".normalizado.txt")]
        difere = any(
            p.read_bytes() != (b / p.name).read_bytes() for p in brutos
        )
        assert difere, "dois ticks diferentes deram o mesmo bruto"


class TestComparar:
    """A comparacao pela linha de comando."""

    def test_sem_mudanca_sai_limpa(self, tmp_path: Path, capsys) -> None:
        a = _coletar(tmp_path / "a", 7)
        b = _coletar(tmp_path / "b", 8)
        codigo = main(["comparar", "--anterior", str(a), "--atual", str(b)])
        assert codigo == 0
        saida = capsys.readouterr().out
        assert "sem mudanca inesperada" in saida
        assert "MUDANCA INESPERADA" not in saida

    def test_registra_no_historico(self, tmp_path: Path) -> None:
        a = _coletar(tmp_path / "a", 7)
        b = _coletar(tmp_path / "b", 8)
        hist = tmp_path / "h.md"
        main([
            "comparar", "--anterior", str(a), "--atual", str(b),
            "--historico", str(hist),
            "--data", "2026-02-02 10:00",
            "--operador", "kelvin",
        ])
        texto = hist.read_text(encoding="utf-8")
        assert "2026-02-02 10:00" in texto
        assert "kelvin" in texto
        assert contar_registros(hist) == 3

    def test_operador_vazio_falha(self, tmp_path: Path, capsys) -> None:
        a = _coletar(tmp_path / "a", 7)
        b = _coletar(tmp_path / "b", 8)
        codigo = main([
            "comparar", "--anterior", str(a), "--atual", str(b),
            "--historico", str(tmp_path / "h.md"),
            "--operador", "   ",
        ])
        assert codigo == 2

    def test_diretorio_inexistente(self, tmp_path: Path, capsys) -> None:
        a = _coletar(tmp_path / "a", 7)
        codigo = main([
            "comparar", "--anterior", str(a), "--atual", str(tmp_path / "nao-existe")
        ])
        assert codigo == 2
        assert "Erro" in capsys.readouterr().err

    def test_diretorio_sem_normalizados(self, tmp_path: Path, capsys) -> None:
        vazio = tmp_path / "vazio"
        vazio.mkdir()
        codigo = main([
            "comparar", "--anterior", str(vazio), "--atual", str(vazio)
        ])
        assert codigo == 2
        assert "a coleta nao foi feita" in capsys.readouterr().err

    def test_mudanca_declarada_nao_alerta(self, tmp_path: Path, capsys) -> None:
        # Este e o teste do estado do meio: sem ele, qualquer ferramenta de
        # alerta fica inutil depois da primeira falsa sentida.
        a, b = _coletar_com_drift(tmp_path, "spanning-tree mode rapid-pvst")

        esperadas = tmp_path / "esperadas.yaml"
        esperadas.write_text(
            "SW-LAB-01:\n"
            "  - padrao: 'spanning-tree'\n"
            "    motivo: janela de mudanca de 15/01\n"
            "    autor: kelvin\n",
            encoding="utf-8",
        )
        codigo = main([
            "comparar", "--anterior", str(a), "--atual", str(b),
            "--esperadas", str(esperadas),
        ])
        saida = capsys.readouterr().out
        assert "mudanca esperada" in saida
        assert "ALERTA" not in saida
        assert codigo == 0

    def test_esperadas_malformadas(self, tmp_path: Path, capsys) -> None:
        a = _coletar(tmp_path / "a", 7)
        ruim = tmp_path / "ruim.yaml"
        ruim.write_text("- nao-e-mapa\n", encoding="utf-8")
        codigo = main([
            "comparar", "--anterior", str(a), "--atual", str(a),
            "--esperadas", str(ruim),
        ])
        assert codigo == 2
        assert "Erro" in capsys.readouterr().err


class TestPrazoDeclarado:
    """O `ate` de uma mudanca esperada e uma promessa, nao um comentario."""

    def _yaml(self, destino: Path, ate: str) -> Path:
        caminho = destino / "esperadas.yaml"
        caminho.write_text(
            "SW-LAB-01:\n"
            "  - padrao: 'spanning-tree'\n"
            "    motivo: janela de mudanca de 15/01\n"
            "    autor: kelvin\n"
            f"    ate: '{ate}'\n",
            encoding="utf-8",
        )
        return caminho

    def _compara(self, tmp_path: Path, ate: str, data: str | None, capsys):
        a, b = _coletar_com_drift(tmp_path, "spanning-tree mode rapid-pvst")
        argv = [
            "comparar", "--anterior", str(a), "--atual", str(b),
            "--esperadas", str(self._yaml(tmp_path, ate)),
        ]
        if data is not None:
            argv += ["--data", data]
        codigo = main(argv)
        cap = capsys.readouterr()
        return codigo, cap.out + cap.err

    def test_dentro_da_janela_nao_alerta(self, tmp_path: Path, capsys) -> None:
        codigo, saida = self._compara(tmp_path, "2026-03-01", "2026-02-20 10:00", capsys)
        assert "ALERTA" not in saida
        assert codigo == 0

    def test_no_dia_do_prazo_ainda_valida(self, tmp_path: Path, capsys) -> None:
        # "ate 2026-03-01" quer dizer valendo DURANTE o dia 01, nao ate as
        # 23:59 do dia seguinte. Uma janela que estoura na virada vira alerta
        # numa coleta legitima, que e o pior jeito de errar.
        codigo, saida = self._compara(tmp_path, "2026-03-01", "2026-03-01 23:00", capsys)
        assert "ALERTA" not in saida
        assert codigo == 0

    def test_passado_o_prazo_volta_a_ser_drift(self, tmp_path: Path, capsys) -> None:
        # Sem isto, `ate` e decoracao: uma declaracao de 2020 continuaria
        # silenciando drift para sempre.
        codigo, saida = self._compara(tmp_path, "2026-03-01", "2026-04-01 09:00", capsys)
        assert "ALERTA" in saida
        assert codigo == 1

    def test_expirada_mantem_o_motivo_visivel(self, tmp_path: Path, capsys) -> None:
        # O alerta precisa dizer POR QUE a declaracao deixou de valer. Sem o
        # motivo no texto, o operador so ve uma janela vencida e nao sabe se
        # renova a declaracao ou investiga.
        _, saida = self._compara(tmp_path, "2026-03-01", "2026-04-01 09:00", capsys)
        assert "janela encerrada em 2026-03-01" in saida

    def test_sem_data_nao_expira(self, tmp_path: Path, capsys) -> None:
        # Nao ha relogio proprio: sem --data a ferramenta nao pode supor que
        # "agora" e a data da coleta.
        codigo, saida = self._compara(tmp_path, "2026-03-01", None, capsys)
        assert "ALERTA" not in saida
        assert codigo == 0

    def test_data_com_horario_e_aceita(self, tmp_path: Path, capsys) -> None:
        codigo, saida = self._compara(tmp_path, "2026-03-01", "2026-02-20 14:30", capsys)
        assert "ALERTA" not in saida
        assert codigo == 0

    def test_prazo_ilegivel_e_erro_de_inventario(self, tmp_path: Path, capsys) -> None:
        # Adivinhar a partir de "01/03/2026" significaria aceitar uma
        # declaracao sem prazo em silencio, que e o pior desfecho possivel:
        # drift silenciado por um prazo que ninguem leu.
        codigo, saida = self._compara(tmp_path, "01/03/2026", "2026-02-20 10:00", capsys)
        assert codigo == 2
        assert "prazo invalido" in saida

    def test_prazo_vazio_nao_expira(self, tmp_path: Path, capsys) -> None:
        caminho = tmp_path / "esperadas.yaml"
        caminho.write_text(
            "SW-LAB-01:\n"
            "  - padrao: 'spanning-tree'\n"
            "    motivo: janela sem prazo definido\n"
            "    autor: kelvin\n"
            "    ate: ''\n",
            encoding="utf-8",
        )
        a, b = _coletar_com_drift(tmp_path, "spanning-tree mode rapid-pvst")
        codigo = main([
            "comparar", "--anterior", str(a), "--atual", str(b),
            "--esperadas", str(caminho),
            "--data", "2030-01-01 10:00",
        ])
        assert "ALERTA" not in capsys.readouterr().out
        assert codigo == 0

    def test_o_yaml_do_repositorio_expirada_para_fora(self, tmp_path: Path, capsys) -> None:
        # Guarda o arquivo de verdade contra regressao de escape: com `\\s` no
        # lugar de `\\s`, o padrao nunca casa e a declaracao vira alerta sem
        # que ninguem perceba que ela existe.
        from cfgbackup.cli import _carrega_esperadas

        declaracoes = _carrega_esperadas(
            RAIZ / "dados" / "mudancas-esperadas.yaml", "2026-01-20 09:30"
        )
        assert "SW-LAB-02" in declaracoes
        padrao = declaracoes["SW-LAB-02"][0]
        assert padrao.casa(" exec-timeout 5 0"), "o padrao do YAML nao casa com a linha"

    def test_o_yaml_do_repositorio_expirou_de_fato(self, tmp_path: Path, capsys) -> None:
        from cfgbackup.cli import _carrega_esperadas

        declaracoes = _carrega_esperadas(
            RAIZ / "dados" / "mudancas-esperadas.yaml", "2026-04-01 09:30"
        )
        assert declaracoes["SW-LAB-02"][0].casa(" exec-timeout 5 0") is False


class TestRegras:
    """A listagem da tabela de normalizacao."""

    def test_resumo(self, capsys) -> None:
        assert main(["regras"]) == 0
        saida = capsys.readouterr().out
        assert "regra(s) de normalizacao" in saida
        assert "docs/o-que-nao-comparar.md" in saida

    def test_com_texto_mostra_padrao_e_motivo(self, capsys) -> None:
        assert main(["regras", "--texto"]) == 0
        saida = capsys.readouterr().out
        assert "padrao:" in saida
        assert "motivo:" in saida

    def test_toda_regra_aparece(self, capsys) -> None:
        from cfgbackup.normalizador import REGRAS_PADRAO

        main(["regras", "--texto"])
        saida = capsys.readouterr().out
        for regra in REGRAS_PADRAO:
            assert regra.nome in saida, regra.nome


class TestParser:
    """A forma da interface."""

    def test_ajuda(self) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == 0

    def test_ajuda_de_cada_subcomando(self) -> None:
        for sub in ("coletar", "comparar", "regras"):
            with pytest.raises(SystemExit) as exc:
                main([sub, "--help"])
            assert exc.value.code == 0, sub

    def test_sem_subcomando(self) -> None:
        with pytest.raises(SystemExit) as exc:
            main([])
        assert exc.value.code != 0

    def test_subcomando_desconhecido(self) -> None:
        with pytest.raises(SystemExit):
            main(["inventado"])

    def test_comparar_exige_os_dois_diretorios(self) -> None:
        with pytest.raises(SystemExit):
            main(["comparar", "--anterior", "x"])

    def test_os_tres_subcomandos_existem(self) -> None:
        parser = construir_parser()
        assert parser.parse_args(["regras"]).comando == "regras"
        assert parser.parse_args(
            ["comparar", "--anterior", "a", "--atual", "b"]
        ).comando == "comparar"
        assert parser.parse_args(["coletar"]).comando == "coletar"