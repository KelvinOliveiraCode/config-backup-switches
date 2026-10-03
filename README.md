# config-backup-switches

Coleta a configuração de equipamentos de rede fictícios, normaliza antes de comparar e classifica a mudança em três estados; só a terceira gera alerta.

> **Nada aqui é real.** Os equipamentos `SW-LAB-01`, `SW-LAB-02` e `FW-LAB-01` não existem. As configurações são de sintaxe Cisco IOS, escritas para este projeto. O SNMP e a interface HTTP são simulados em `simulador.py`; nenhuma requisição sai do processo.

### O que é

Ferramenta de detecção de drift de configuração: coleta a configuração de equipamentos fictícios, aplica uma tabela de normalização antes de comparar e classifica cada mudança como **sem mudança**, **esperada** (declarada) ou **inesperada** (drift).

### Por que foi feito

Backup de configuração é a primeira tarefa que um estagiário de infraestrutura recebe, e é a que evita o pior incidente: alguém derruba um serviço e ninguém sabe o que a configuração tinha antes. Mas o backup em si não serve de nada se o diff é ilegível: com duas coletas de um equipamento com vida, o uptime avança, um contador sobe, a tabela MAC ganha uma entrada e o diff fica com uma centena de linhas que não são mudança. Sem normalizar, o alerta dispara todo dia, ninguém olha, e na semana em que alguém realmente desabilitou uma ACL o sistema já foi desligado — a ferramenta feita para avisar de mudança se anulou sozinha.

### Como rodar

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
python -m pytest tests/ -v
python -m cfgbackup --help
```

Saída real, com a venv ativa:

```
usage: cfgbackup [-h] {coletar,comparar,regras} ...

Coleta configuracao de equipamentos ficticios, normaliza e detecta mudanca
gerenciada. Collects fictitious device configuration, normalizes it and
detects managed change.

positional arguments:
  {coletar,comparar,regras}
    coletar             Coleta a configuracao dos equipamentos.
    comparar            Compara duas coletas.
    regras              Mostra a tabela de normalizacao.

options:
  -h, --help            show this help message and exit
```

A dependência é só `PyYAML`, para ler o inventário; o diff usa `difflib` e a normalização usa `re`.

Para rodar um comando no host sem instalar nada, aponte o PYTHONPATH para `src`:

```powershell
$env:PYTHONPATH="C:\Users\Kelvin\Desktop\portfolio-24\config-backup-switches\src"
python -m cfgbackup coletar --equipamentos dados/equipamentos.yaml --saida saida/
```

### O que aprendi

1. **A ordem da tabela de regras é parte da semântica.** A primeira regra que casa vence. Se `memoria` viesse antes de `uptime`, a linha `Uptime: 3 days` seria capturada como uso de memória. A ordem é fixa no código e coberta por teste. Consequência: inverter as duas muda o diff de todo equipamento.

2. **Fusão só de repetidas consecutivas.** Depois de normalizar cada linha da tabela MAC para o mesmo placeholder, a fusão de repetidas transforma a tabela inteira em uma linha. Mas ela só funde repetições consecutivas: duas interfaces idênticas lado a lado são duplicata real de configuração, e fundi-las esconderia um erro. Consequência: o diff continua mostrando duplicatas verdadeiras.

3. **O bruto precisa ser gravado junto com o normalizado.** O normalizado é a saída de comparação; o bruto é a única prova de que a tabela de normalização não removeu demais. Guardar só o normalizado torna o erro da regra invisível até você precisar do valor original. Consequência: o bruto é o que permite auditar a tabela de regras.

4. **A contagem da tabela MAC fica fora do corpo da linha.** O tamanho da tabela é estado do momento, não configuração. Se a contagem fosse comparada, um andar com gente entrando e saindo viraria alerta a cada coleta. Por isso o marcador de contagem vem separado. Consequência: quem precisa de contagem lê a tabela de vizinhos, que não está no backup.

### Limitações

- **A configuração é sintética.** Cisco IOS é o dialeto; a tabela de regras tem regras específicas dele. Um equipamento de outra família precisa das próprias regras, e a tabela é o lugar de discuti-las.
- **O SNMP real não entrega configuração**, entrega valores de MIB. A via SNMP aqui devolve uma síntese em texto no mesmo formato da via HTTP, e o ponto do projeto é a comparação, não o transporte.
- **A contagem de entradas da tabela MAC é descartada** de propósito. Quem precisa de quantos clientes estão conectados lê a tabela de vizinhos, que não está no backup.
- **A fusão de repetidas não sabe o que é tabela.** Ela funde qualquer repetição consecutiva. Uma regra que coloque duas linhas iguais vizinhas numa configuração real vai ter as duas fundidas.
- **A expiração usa a data que você passa.** Não há relógio próprio: uma declaração com prazo no passado é expirada numa coleta de 2019, o que é o comportamento correto para um backup histórico e não para um alerta ao vivo.

### Licença

MIT. Veja [`LICENSE`](LICENSE).

## EN

### What it is

Configuration-drift detector for fictitious network devices: it collects `running-config`, normalizes it before comparing, and classifies each change as no change, declared, or unexpected; only the last raises an alert.

### Why it was built

Configuration backup is the first task an infrastructure intern gets, and it is the one that prevents the worst incident: someone takes a service down and nobody knows what the configuration was before. But a backup is useless if the diff is unreadable. With two collections of a live device, uptime advances, counters tick up, the MAC table gains an entry, and the diff fills with lines that are not change. Without normalization, the alert fires every day, nobody looks, and when someone disables a real ACL the system has already been turned off — the drift detector nullified itself.

### How to run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
python -m pytest tests/ -v
python -m cfgbackup --help
```

Real output, with the venv active:

```
usage: cfgbackup [-h] {coletar,comparar,regras} ...

Coleta configuracao de equipamentos ficticios, normaliza e detecta mudanca
gerenciada. Collects fictitious device configuration, normalizes it and
detects managed change.

positional arguments:
  {coletar,comparar,regras}
    coletar             Coleta a configuracao dos equipamentos.
    comparar            Compara duas coletas.
    regras              Mostra a tabela de normalizacao.

options:
  -h, --help            show this help message and exit
```

The only dependency is `PyYAML`, to read the inventory; the diff uses `difflib` and the normalization uses `re`.

To run a command on the host without installing anything, set PYTHONPATH to `src`:

```powershell
$env:PYTHONPATH="C:\Users\Kelvin\Desktop\portfolio-24\config-backup-switches\src"
python -m cfgbackup coletar --equipamentos dados/equipamentos.yaml --saida saida/
```

### What I learned

1. **Rule order is part of the semantics.** The first rule that matches wins. If `memoria` came before `uptime`, the line `Uptime: 3 days` would be captured as memory usage. The order is fixed in the code and covered by tests. Consequence: swapping the two changes the diff on every device.

2. **Fusion only of consecutive duplicates.** After normalizing every MAC-table line to the same placeholder, consecutive-fusion turns the whole table into one line. But it only fuses consecutive repetitions: two identical interfaces side by side are a real configuration duplicate, and fusing them would hide an error. Consequence: the diff keeps showing real duplicates.

3. **The raw output must be saved alongside the normalized one.** The normalized output is the comparison result; the raw output is the only proof that the normalization table did not remove too much. Saving only the normalized one makes rule errors invisible until you need the original value. Consequence: the raw output is what lets you audit the rules table.

4. **The MAC-table entry count lives outside the line body.** The table size is momentary state, not configuration. If the count were compared, a floor with people coming and going would raise an alert every collection. That is why the count marker is separate. Consequence: anyone needing the count reads the neighbor table, which is not in the backup.

### Limitations

- **The configuration is synthetic.** Cisco IOS is the dialect; the rules table holds IOS-specific rules. A device from another family needs its own rules, and the table is the place to discuss them.
- **Real SNMP does not deliver configuration**; it delivers MIB values. The SNMP path here returns a text synthesis in the same format as the HTTP path, and the point of the project is comparison, not transport.
- **The MAC-table entry count is discarded** on purpose. Anyone who needs to know how many clients are connected reads the neighbor table, which is not in the backup.
- **Consecutive-fusion does not know what a table is.** It fuses any consecutive repetition. A rule that places two identical lines next to each other in a real configuration will have those two fused.
- **Expiration uses the date you pass.** There is no internal clock: a declaration with a past deadline expires on a 2019 collection, which is correct behavior for a historical backup and not for a live alert.

### License

MIT. See [`LICENSE`](LICENSE).

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

Bruto e normalizado, sempre. O bruto é o que o equipamento respondeu, e ele é o único jeito de descobrir que a tabela de normalização está errada: se a regra removeu demais, só o bruto mostra o que sumiu. Guardar só o normalizado faz o erro ser invisível até o dia em que você precisar do valor original.

### Por que a tabela MAC precisa de fusão, e não só de placeholder

A tabela MAC tem duas propriedades que quebram a diff: muda de **ordem** a cada coleta e muda de **tamanho** conforme gente entra e sai.

Normalizar cada linha para o mesmo placeholder resolve a primeira e não a segunda — e a ordem trocada ainda gera seis "mudanças" onde nada mudou. Por isso existe a fusão de repetidas consecutivas: a tabela inteira vira uma linha.

A contagem de entradas fica **fora** do corpo da linha, num marcador à parte. É deliberado: quantos clientes estão conectados é informação de momento, não de configuração. Se a contagem fosse comparada, ela viraria alerta a cada coleta.

### A ordem da tabela importa

A primeira regra que casa vence. A regra de uptime vem antes da de memória para que `Uptime: 3 days` não seja capturada como se fosse uso de memória.

E a fusão só funde repetições **consecutivas**. Duas linhas de configuração iguais que por acaso ficam lado a lado — duas interfaces idênticas — continuam sendo duas linhas, porque fundi-las esconderia uma duplicata real.

## Os três estados

É o ponto inteiro do projeto, e a distinção entre o estado do meio e o terceiro é o que separa uma ferramenta útil de uma que ninguém ouve.

| Estado | Significado | Alerta | Código de saída |
|---|---|---|---|
| sem mudança | as configurações normalizadas são iguais | não | 0 |
| esperada | a mudança foi declarada antes, com prazo | não | 0 |
| inesperada | alguém mexeu fora do processo — **drift** | **sim** | 1 |

Sem o estado do meio, todo alerta vira alarme. Na primeira vez que alguém executa a manutenção de verdade, o sistema avisa; na segunda, o time silencia o alerta — e não porque o problema sumiu, mas porque ele parou de significar alguma coisa.

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

Sem isso, o campo `até` é um comentário — e escrever um prazo errado é tão inútil quanto não escrever nenhum. Sem o relatório, o alerta também não diz o que fazer: um drift mudo não distingue "alguém mexeu" de "a janela de manutenção venceu".

## Formato dos dados

**`dados/equipamentos.yaml`** — lista do que existe:

```yaml
- hostname: SW-LAB-01
  tipo: switch
  via: snmp
  comunidade: LABCOMUNIDADE
```

A lista é a fonte da verdade. Um hostname a mais aqui é erro de inventário e a ferramenta **recusa** em vez de inventar um aparelho: um backup que "criou" um equipamento que o cliente não tem seria pior do que um backup que falhou.

## Testes

```powershell
python -m pytest tests/ -v
```

139 testes, 94% de cobertura. Cobrem as 16 regras, a ordem da tabela, a fusão de repetidas, os três estados, o ciclo de expiração da declaração, a CLI inteira e o fato de que duas coletas com ticks diferentes produzem normalizado idêntico.

Verificações que a suíte não cobre sozinha:

```powershell
python tools/verificar_aceite.py       # as quatro metades do critério de aceite
python tools/verificar_encoding.py     # nenhum caractere corrompido
python tools/verificar_doc.py          # o doc descreve a tabela de regras real
python tools/gerar_exemplo.py         # regera o exemplo de forma determinística
```

Os quatro rodam no CI. O `verificar_doc.py` é o que impede que a tabela de regras e a documentação divergam em silêncio: as duas descrevem os mesmos 16 padrões, e a checagem compara nome, ação, ordem e o texto de cada regex.

O `verificar_aceite.py` é o mais importante, porque a suíte prova que as funções funcionam e não que a ferramenta inteira se comporta:

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
