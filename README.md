# cfgbackup

Coleta a configuração de equipamentos de rede **fictícios**, normaliza antes de
comparar, e classifica a mudança em três estados: sem mudança, mudança esperada
e mudança inesperada. Só a terceira gera alerta.

Cross-references **fictitious** network device configuration, normalizes it
before comparing, and classifies the change into three states: no change,
declared change, undeclared change. Only the third raises an alert.

> **Nada aqui é real.** Os equipamentos `SW-LAB-01`, `SW-LAB-02` e `FW-LAB-01`
> não existem. As configurações são de sintaxe Cisco IOS, escritas para este
> projeto. O SNMP e a interface HTTP são simulados em `simulador.py`; nenhuma
> requisição sai do processo.

## O problema que ele resolve

Backup de configuração é a primeira tarefa que um estagiário de infraestrutura
recebe, e é a que evita o pior incidente: alguém derruba um serviço e ninguém
sabe o que a configuração tinha antes.

Mas o backup em si não serve de nada se o diff é ilegível. Duas coletas de um
equipamento com vida têm diferença **sem que ninguém tenha mexido em nada**: o
uptime avançou, um contador subiu, a tabela MAC ganhou uma entrada, a ordem das
sessões mudou.

Aqui, três equipamentos e duas coletas separadas por 23 ticks de tempo
resultam em **zero** diferenças. Não porque o diff é esperto: porque 16 regras
retiram da comparação o que é estado do aparelho, e cada uma delas carrega o
motivo em código e em
[`docs/o-que-nao-comparar.md`](docs/o-que-nao-comparar.md).

## Instalação

```powershell
git clone <url-do-repositório>
cd config-backup-switches
pip install -e ".[dev]"
```

Uma dependência, PyYAML, para ler o inventário. O resto é biblioteca padrão:
o diff usa `difflib` e a normalização usa `re`.

## Uso

```powershell
python -m cfgbackup coletar --equipamentos dados/equipamentos.yaml --saida saida/
```

Saída real:

```
coleta de 3 equipamento(s) em saida
  FW-LAB-01      via http    31 linhas ->   26 normalizadas (5 removidas)
  SW-LAB-01      via snmp    47 linhas ->   41 normalizadas (6 removidas)
  SW-LAB-02      via http    47 linhas ->   42 normalizadas (5 removidas)

regras de normalizacao acionadas: 8
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
```

Comparar duas coletas:

```powershell
python -m cfgbackup comparar --anterior saida/ --atual saida/ --historico exemplos/historico-exemplo.md
```

Ver a tabela de normalização, que é a parte do código que mais importa:

```powershell
python -m cfgbackup regras --texto
```

## Os três estados

É o ponto inteiro do projeto, e a distinção entre o estado do meio e o terceiro
é o que separa uma ferramenta útil de uma que ninguém ouve.

| Estado | Significado | Alerta | Código de saída |
|---|---|---|---|
| sem mudança | as configurações normalizadas são iguais | não | 0 |
| esperada | a mudança foi declarada antes, com prazo | não | 0 |
| inesperada | alguém mexeu fora do processo — **drift** | **sim** | 1 |

Sem o estado do meio, todo alerta vira alarme. Na primeira vez que alguém
executa a manutenção de verdade, o sistema avisa; na segunda, o time silencia o
alerta — e não porque o problema sumiu, mas porque ele parou de significar
alguma coisa.

Uma mudança declarada **expira**:

```yaml
# dados/mudancas-esperadas.yaml
SW-LAB-02:
  - padrao: '^\s+exec-timeout'
    motivo: reducao do timeout de sessao conforme politica de seguranca de 2026-01
    autor: kelvin
    ate: '2026-03-01'
```

Passado o dia 20, a mudança volta a ser drift — e o relatório diz por quê:

```
declaracoes com a janela encerrada:
    SW-LAB-02  padrao=^\s+exec-timeout  por kelvin
      motivo: reducao do timeout de sessao conforme politica de seguranca de 2026-01
      janela encerrada em 2026-03-01
```

Sem isso, o campo `até` é um comentário — e escrever um prazo errado é tão
inútil quanto não escrever nenhum. Sem o relatório, o alerta também não diz o
que fazer: um drift mudo não distingue "alguém mexeu" de "a janela de
manutenção venceu".

## Como funciona

| Módulo | Responsabilidade |
|---|---|
| `simulador.py` | Equipamentos fictícios, SNMP e HTTP simuladas, campo volátil |
| `normalizador.py` | Tabela de 16 regras, cada uma com seu motivo |
| `coletor.py` | Coleta, grava bruto **e** normalizado |
| `diferenca.py` | Diff linha a linha e classificação em três estados |
| `historico.py` | Registro em Markdown, com data e operador |
| `cli.py` | `coletar`, `comparar`, `regras` |

### Por que gravar os dois arquivos

Bruto e normalizado, sempre. O bruto é o que o equipamento respondeu, e ele é o
único jeito de descobrir que a tabela de normalização está errada: se a regra
removeu demais, só o bruto mostra o que sumiu. Guardar só o normalizado faz o
erro ser invisível até o dia em que você precisar do valor original.

### Por que a tabela MAC precisa de fusão, e não só de placeholder

A tabela MAC tem duas propriedades que quebram a diff: muda de **ordem** a cada
coleta e muda de **tamanho** conforme gente entra e sai.

Normalizar cada linha para o mesmo placeholder resolve a primeira e não a
segunda — e a ordem trocada ainda gera seis "mudanças" onde nada mudou. Por isso
existe a fusão de repetidas consecutivas: a tabela inteira vira uma linha.

A contagem de entradas fica **fora** do corpo da linha, num marcador à parte. É
deliberado: quantos clientes estão conectados é informação de momento, não de
configuração. Se a contagem fosse comparada, ela viraria alerta a cada coleta.

### A ordem da tabela importa

A primeira regra que casa vence. A regra de uptime vem antes da de memória
para que `Uptime: 3 days` não seja capturada como se fosse uso de memória.

E a fusão só funde repetições **consecutivas**. Duas linhas de configuração
iguais que por acaso ficam lado a lado — duas interfaces idênticas —
continuam sendo duas linhas, porque fundi-las esconderia uma duplicata real.

## Formato dos dados

**`dados/equipamentos.yaml`** — lista do que existe:

```yaml
- hostname: SW-LAB-01
  tipo: switch
  via: snmp
  comunidade: LABCOMUNIDADE
```

A lista é a fonte da verdade. Um hostname a mais aqui é erro de inventário e a
ferramenta **recusa** em vez de inventar um aparelho: um backup que "criou" um
equipamento que o cliente não tem seria pior do que um backup que falhou.

## Testes

```powershell
python -m pytest tests/ -v
```

139 testes, 94% de cobertura. Cobrem as 16 regras, a ordem da tabela, a fusão
de repetidas, os três estados, o ciclo de expiração da declaração, a CLI
inteira e o fato de que duas coletas com ticks diferentes produzem normalizado
idêntico.

Verificações que a suíte não cobre sozinha:

```powershell
python tools/verificar_aceite.py       # as quatro metades do critério de aceite
python tools/verificar_encoding.py     # nenhum caractere corrompido
python tools/verificar_doc.py          # o doc descreve a tabela de regras real
python tools/gerar_exemplo.py         # regera o exemplo de forma determinística
```

Os quatro rodam no CI. O `verificar_doc.py` é o que impede que a tabela de
regras e a documentação divergam em silêncio: as duas descrevem os mesmos 16
padrões, e a checagem compara nome, ação, ordem e o texto de cada regex.

O `verificar_aceite.py` é o mais importante, porque a suíte prova que as
funções funcionam e não que a ferramenta inteira se comporta:

```
1) duas coletas sem mexer em nada
   FW-LAB-01: sem mudanca
   SW-LAB-01: sem mudanca
   SW-LAB-02: sem mudanca
   (reforco: um salto de 23 ticks tambem tem de sair limpo)
   23 ticks de intervalo: sem mudanca nos tres equipamentos

2) uma linha alterada fora do processo
   SW-LAB-01: inesperada, 1 mudanca(s)

3) uma mudanca declarada nao vira alerta
   SW-LAB-02: esperada, sem alerta, motivo: abertura de rota para o servidor de backup, janela de 15/01

4) o historico registra autor e data
   2 registros, 44 linhas
```

## Estrutura

```
config-backup-switches/
├── src/cfgbackup/          # o pacote
├── dados/                  # inventário, mudanças esperadas
├── docs/                   # o que não comparar, como normalizar
├── exemplos/               # histórico gerado
├── tests/                  # 139 testes
└── tools/                  # gerador e verificações
```

## Limitações

- **A configuração é sintética.** Cisco IOS é o dialeto; a tabela de regras tem
  regras específicas dele. Um equipamento de outra família precisa das próprias
  regras, e a tabela é o lugar de discuti-las.
- **O SNMP real não entrega configuração**, entrega valores de MIB. A via SNMP
  aqui devolve uma síntese em texto no mesmo formato da via HTTP, e o ponto do
  projeto é a comparação, não o transporte.
- **A contagem de entradas da tabela MAC é descartada** de propósito. Quem
  precisa de quantos clientes estão conectados lê a tabela de vizinhos, que não
  está no backup.
- **A fusão de repetidas não sabe o que é tabela.** Ela funde qualquer repetição
  consecutiva. Uma regra que coloque duas linhas iguais vizinhas numa
  configuração real vai ter as duas fundidas.
- **A expiração usa a data que você passa.** Não há relógio próprio: uma
  declaração com prazo no passado é expirada numa coleta de 2019, o que é o
  comportamento correto para um backup histórico e não para um alerta ao vivo.

## Licença

MIT.