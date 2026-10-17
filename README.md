# config-backup-switches

<img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+">
<img src="https://img.shields.io/badge/tests-139%20passing-brightgreen?style=flat-square" alt="Testes">
<img src="https://img.shields.io/badge/coverage-94%25-green?style=flat-square" alt="Cobertura">
<img src="https://img.shields.io/badge/deps-PyYAML%20only-blue?style=flat-square" alt="Dependencias">
<img src="https://img.shields.io/badge/license-MIT-yellow?style=flat-square" alt="Licenca">
<img src="https://img.shields.io/badge/platform-Windows-blue?style=flat-square" alt="Windows">

Backup de configuração de equipamentos de rede com normalização e detecção de mudança gerenciada. Apenas mudanças não declaradas geram alerta.

## Problema / Por que existe

Backup de configuração é a primeira tarefa que um estagiário de infraestrutura recebe, e é a que evita o pior incidente: alguém derruba um serviço e ninguém sabe como a configuração estava antes. Mas o backup sozinho não serve se o diff é ilegível. Duas coletas de um equipamento com vida diferem sem que ninguém tenha mexido: o uptime avança, um contador sobe, a tabela MAC ganha uma entrada, a ordem das linhas muda. Sem normalização, o alerta dispara todo dia, ninguém olha, e na semana em que alguém realmente desabilita uma ACL o sistema já foi desligado. A ferramenta feita para avisar de mudança se anulou sozinha.

Este projeto existe para separar mudança de ruído. Compara apenas o que é configuração, classifica cada mudança em três estados e só alerta quando alguém mexeu fora do processo.

## O que faz

- Lê o inventário em dados/equipamentos.yaml (SW-LAB-01, SW-LAB-02 e FW-LAB-01). Um hostname que não consta do simulador é erro de inventário: a ferramenta recusa, não inventa aparelho.
- Coleta a configuração de cada equipamento por um simulador interno, com interfaces SNMP e HTTP fictícias. Nenhuma requisição sai do processo; nenhum equipamento real é acessado.
- Grava dois arquivos por equipamento: o bruto (resposta do equipamento) e o normalizado (após a tabela de 16 regras de normalização). O bruto é a única prova de que a normalização não removeu demais.
- Aplica 16 regras de normalização (uptime, contadores, tabela MAC, datas, hashes de senha, comunidade SNMP etc.), cada uma com motivo documentado. A ordem da tabela importa: a primeira regra que casa vence.
- Compara duas coletas com difflib e classifica cada mudança como sem mudança, esperada (declarada com prazo) ou inesperada (drift). Apenas a inesperada gera alerta e código de saída 1.
- Declarações expiram pela data passada; declarações vencidas são reportadas em vez de sumir silenciosamente.
- Registra o histórico em Markdown com data, operador e a diff embutida, para responder quem mudou o quê, quando e por quê.
- CLI com três subcomandos: coletar, comparar e regras.

## Stack

- Python 3.10 ou superior.
- Uma dependência de execução: PyYAML>=6.0, apenas para ler o inventário YAML.
- Biblioteca padrão para o restante: difflib (diff), re (normalização), argparse, dataclasses, pathlib.
- Desenvolvimento: pytest>=7.4, pytest-cov>=4.1.
- CI: GitHub Actions no Windows (windows-latest), Python 3.11; cobertura mínima de 70% imposta pelo pyproject.toml.
- Dados: YAML (inventário e mudanças esperadas).

## Como funciona

O fluxo de coleta tem três etapas e a ordem não é negociável.

SNMP ou HTTP (simulado) -> bruto -> normalizado

Os dois arquivos são sempre gravados. O bruto é o que o equipamento respondeu. O normalizado é o texto após a tabela de regras, com campos voláteis removidos ou substituídos por placeholders.

Duas etapas da normalização resolvem problemas diferentes. A primeira transforma cada linha volátil em um placeholder. A segunda existe porque a tabela MAC e a tabela de sessões mudam de ordem a cada coleta: normalizar o conteúdo resolve o que está escrito, mas não a ordem, e um diff linha a linha continuaria acusando mudanças onde nada mudou. Repetições consecutivas são fundidas em uma linha; a contagem fica em um marcador separado, fora do corpo da linha, porque quantidade de entradas é informação do momento, não de configuração.

A primeira regra que casa vence. Por isso a ordem da tabela é parte da semântica: a regra de uptime vem antes da de memória para que "Uptime: 3 days" não seja capturada como uso de memória.

A diferença usa difflib.SequenceMatcher. Um par "removida/adicionada" com o mesmo conteúdo normalizado é fundido em "substituída", para que uma alteração de linha apareça como uma mudança e não como duas.

Cada comparação termina em um dos três estados.

| Estado | Significado | Alerta | Código de saída |
| sem mudança | configurações normalizadas iguais | não | 0 |
| esperada | mudança declarada antes, com prazo | não | 0 |
| inesperada | alguém mexeu fora do processo (drift) | sim | 1 |

Uma mudança declarada expira: passado o prazo em `ate`, ela volta a ser drift e o relatório diz por quê, com equipamento, padrão, autor e data de encerramento.

O histórico não usa o relógio do sistema. A data entra por parâmetro (padrão fixo: 2026-01-15 14:00) para que o arquivo não mude a cada execução e não quebre o git diff.

Resumo dos módulos

| Módulo | Responsabilidade |
| simulador.py | Equipamentos fictícios, SNMP e HTTP simulados, campos voláteis determinísticos |
| normalizador.py | Tabela de 16 regras, cada uma com motivo; fusão de repetições consecutivas |
| coletor.py | Coleta, grava bruto e normalizado |
| diferenca.py | Diferença linha a linha e classificação em três estados |
| historico.py | Registro em Markdown com data e operador |
| cli.py | coletar, comparar, regras |

## Como rodar

Instale o ambiente e rode a suíte.

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
python -m pytest tests/ -v
python -m cfgbackup --help

Sem instalar nada, aponte o PYTHONPATH para src.

$env:PYTHONPATH="$PWD\src"
python -m cfgbackup coletar --equipamentos dados/equipamentos.yaml --saida saida/
python -m cfgbackup comparar --anterior saida/a --atual saida/b
python -m cfgbackup regras --texto

Saída real de `coletar`, com a venv ativa.

coleta de 3 equipamento(s) em saida/
  FW-LAB-01      via http    31 linhas ->   26 normalizadas (5 removidas)
  SW-LAB-01      via snmp    47 linhas ->   41 normalizadas (6 removidas)
  SW-LAB-02      via http    47 linhas ->   42 normalizadas (5 removidas)

regras de normalização acionadas: 8
  - buffer-de-log
  - cabecalho-de-coleta
  - chave-criptografica
  - data-nvram
  - data-ultima-mudanca
  - entrada-da-tabela-mac
  - numero-de-conexao
  - uptime

brutos em *.txt, normalizados em *.normalizado.txt
nenhum equipamento real foi acessado: a coleta sai do simulador

Verificações que a suíte de testes não cobre sozinha.

python tools/verificar_aceite.py       # quatro metades do critério de aceite
python tools/verificar_encoding.py     # nenhum caractere corrompido
python tools/verificar_doc.py          # o doc descreve a tabela de regras real
python tools/gerar_exemplo.py         # regera o exemplo de forma determinística

Os quatro rodam no CI. `verificar_doc.py` impede que a tabela de regras e a documentação divergam em silêncio: ambas descrevem os mesmos 16 padrões, e a checagem compara nome, ação, ordem e o texto de cada regex.

## Estrutura do projeto

config-backup-switches/
├── src/cfgbackup/          # pacote (cli, coletor, diferença, histórico, normalizador, simulador)
├── dados/                  # equipamentos.yaml (inventário), mudancas-esperadas.yaml
├── docs/                   # o-que-nao-comparar.md, como-normalizar-uma-config.md
├── exemplos/               # historico-exemplo.md (gerado determinísticamente)
├── tests/                  # 139 testes
├── tools/                  # gerador e verificações de aceite, encoding e doc
├── pyproject.toml
├── requirements.txt
├── LICENSE
└── README.md

## Trade-offs e decisões

1. Ordem da tabela de regras é semântica. A primeira regra que casa vence; inverter uptime e memória muda o diff de todo equipamento. A ordem é fixa no código e coberta por teste.
2. Bruto e normalizado são sempre gravados. O bruto é a única prova de que a tabela de normalização não removeu demais. Salvar só o normalizado torna erros de regra invisíveis até o dia em que o valor original for necessário.
3. A fusão funde apenas repetições consecutivas. Duas linhas de configuração idênticas lado a lado (duas interfaces iguais) são duplicata real e permanecem como duas linhas; fundi-las esconderia um erro.
4. A contagem da tabela MAC fica fora do corpo da linha, em um marcador separado. Quantidade é estado do momento, não configuração; se comparada, vira alerta a cada coleta.
5. A data do histórico vem por parâmetro, nunca por `datetime.now()`. Histórico com hora da execução muda a cada run e quebra o git diff; a mudança de data é explícita.
6. O inventário é a fonte da verdade. Um hostname a mais é erro de inventário: a ferramenta recusa em vez de inventar um aparelho.
7. O SNMP real não entrega configuração, apenas valores de MIB. A via SNMP do simulador devolve uma síntese em texto no mesmo formato da via HTTP; o ponto do projeto é a comparação, não o transporte.
8. A expiração usa a data que você passa. Não há relógio próprio: uma declaração com prazo no passado expira numa coleta de 2019, comportamento correto para backup histórico e não para alerta ao vivo.

## Limitações conhecidas

- A configuração é sintética (dialeto Cisco IOS). A tabela de regras tem regras específicas de IOS; equipamento de outra família precisa de regras próprias.
- O SNMP real não entrega configuração, entrega valores de MIB; a coleta não acessa rede real.
- A contagem de entradas da tabela MAC é descartada de propósito. Quem precisa de quantos clientes estão conectados lê a tabela de vizinhos, que não está no backup.
- A fusão de repetições não sabe o que é tabela: funde qualquer repetição consecutiva, mesmo fora de tabelas.
- A expiração usa a data que você passa; não há relógio próprio.
- Para usar em equipamentos reais, o simulador precisaria ser substituído por coleta real (SNMP, HTTP ou SSH).

## Licença

MIT. Veja [`LICENSE`](LICENSE). Copyright (c) 2026 Kelvin Oliveira.

## Autor

Kelvin Oliveira.
