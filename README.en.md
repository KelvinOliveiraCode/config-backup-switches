# cfgbackup (English)

Collects **fictitious** network device configuration, normalizes it before
comparing, and classifies the change into three states: no change, declared
change, undeclared change. Only the third raises an alert.

Versão em português: [`README.md`](README.md)

> **Nothing here is real.** The devices `SW-LAB-01`, `SW-LAB-02` and
> `FW-LAB-01` do not exist. The configurations use Cisco IOS syntax, written for
> this project. SNMP and the HTTP interface are simulated in `simulador.py`;
> no request leaves the process.

## The problem it solves

Configuration backup is the first task an infrastructure intern gets, and it is
the one that prevents the worst incident: someone takes a service down and
nobody knows what the configuration looked like before.

But the backup is useless if the diff is unreadable. Two collections of a live
device differ **without anyone having touched anything**: uptime advanced, a
counter went up, the MAC table gained an entry, session order changed.

Here, three devices and two collections 23 ticks apart produce **zero**
differences. Not because the diff is clever: because 16 rules remove from the
comparison whatever is device state, and each rule carries its reason in code
and in
[`docs/o-que-nao-comparar.md`](docs/o-que-nao-comparar.md) (Portuguese).

## Install

```powershell
git clone <repository-url>
cd config-backup-switches
pip install -e ".[dev]"
```

One dependency, PyYAML, to read the inventory. Everything else is standard
library: the diff uses `difflib` and normalization uses `re`.

## Usage

```powershell
python -m cfgbackup coletar --equipamentos dados/equipamentos.yaml --saida saida/
```

Actual output:

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

Compare two collections:

```powershell
python -m cfgbackup comparar --anterior saida/ --atual saida/ --historico exemplos/historico-exemplo.md
```

See the normalization table, the part of the code that matters most:

```powershell
python -m cfgbackup regras --texto
```

## The three states

This is the whole point of the project, and the distinction between the middle
state and the third is what separates a useful tool from one nobody reads.

| State | Meaning | Alert | Exit code |
|---|---|---|---|
| no change | the normalized configurations are equal | no | 0 |
| declared | the change was declared in advance, with a deadline | no | 0 |
| undeclared | someone edited out of process — **drift** | **yes** | 1 |

Without the middle state, every alert becomes noise. The first time someone
does scheduled maintenance the system warns; the second time the team silences
it — not because the problem went away, but because the alert stopped meaning
anything.

A declared change **expires**:

```yaml
# dados/mudancas-esperadas.yaml
SW-LAB-02:
  - padrao: '^\s+exec-timeout'
    motivo: reducao do timeout de sessao conforme politica de seguranca de 2026-01
    autor: kelvin
    ate: '2026-03-01'
```

Past the 20th, the change is drift again — and the report says why:

```
declaracoes com a janela encerrada:
    SW-LAB-02  padrao=^\s+exec-timeout  por kelvin
      motivo: reducao do timeout de sessao conforme politica de seguranca de 2026-01
      janela encerrada em 2026-03-01
```

Without that, the `ate` field is a comment — and writing a wrong deadline is as
useless as writing none. Without the report, the alert also fails to say what to
do: a silent drift does not distinguish "someone edited" from "the maintenance
window expired".

## How it works

| Module | Responsibility |
|---|---|
| `simulador.py` | Fictitious devices, simulated SNMP and HTTP, volatile fields |
| `normalizador.py` | Table of 16 rules, each with its reason |
| `coletor.py` | Collects, writes the raw **and** the normalized file |
| `diferenca.py` | Line-level diff and three-state classification |
| `historico.py` | Markdown record, with date and operator |
| `cli.py` | `coletar`, `comparar`, `regras` |

Module, function and field names stay in Portuguese to match the portfolio and
the YAML data. The domain vocabulary maps as: `coletar`/collect,
`comparar`/compare, `regras`/rules, `historico`/history, `normalizado`/
normalized, `deriva`/drift, `esperadas`/declared.

### Why both files are written

Raw and normalized, always. The raw file is what the device returned, and it is
the only way to find out that the normalization table is wrong: if a rule
removed too much, only the raw file shows what disappeared. Keeping only the
normalized version makes the error invisible until the day you need the
original value.

### Why the MAC table needs collapsing, not just a placeholder

The MAC table has two properties that break a diff: it changes **order** on
every collection and changes **size** as people come and go.

Normalizing each row to the same placeholder solves the first and not the
second — and the shuffled order still produces six "changes" where nothing
changed. Hence the collapsing of consecutive repeats: the whole table becomes
one line.

The entry count lives **outside** the line body, in a separate marker. That is
deliberate: how many clients are connected is information of the moment, not of
the configuration. Comparing the count would make it alert on every collection.

### Rule order matters

The first rule that matches wins. The uptime rule comes before the memory rule
so that `Uptime: 3 days` is not captured as if it were memory usage.

And collapsing only merges **consecutive** repeats. Two configuration lines
that happen to be adjacent and identical — two identical interfaces — stay two
lines, because merging them would hide a real duplicate.

## Data formats

**`dados/equipamentos.yaml`** — the list of what exists:

```yaml
- hostname: SW-LAB-01
  tipo: switch
  via: snmp
  comunidade: LABCOMUNIDADE
```

The list is the source of truth. An extra hostname here is an inventory error
and the tool **refuses** rather than inventing a device: a backup that "created"
a device the client does not have is worse than a backup that failed.

## Tests

```powershell
python -m pytest tests/ -v
```

139 tests, 94% coverage. They cover the 16 rules, rule ordering, repeat
collapsing, the three states, the declaration expiry cycle, the whole CLI, and
the fact that two collections at different ticks produce identical normalized
output.

Checks the suite alone does not cover:

```powershell
python tools/verificar_aceite.py       # all four halves of the acceptance criterion
python tools/verificar_encoding.py     # no corrupted characters
python tools/verificar_doc.py          # the doc matches the real rule table
python tools/gerar_exemplo.py         # regenerates the example deterministically
```

All four run in CI. `verificar_doc.py` is what keeps the rule table and the
documentation from drifting apart silently: both describe the same 16 patterns,
and the check compares name, action, order and each regex's literal text.

`verificar_aceite.py` is the important one, because the suite proves the
functions work and not that the whole tool behaves:

```
1) two collections with nothing touched
   FW-LAB-01: sem mudanca
   SW-LAB-01: sem mudanca
   SW-LAB-02: sem mudanca
   (reinforcement: a 23-tick gap must also come out clean)
   23 ticks apart: no change on all three devices

2) one line edited out of process
   SW-LAB-01: unexpected, 1 change(s)

3) a declared change does not alert
   SW-LAB-02: expected, no alert, reason: route opening for the backup server, 15/01 window

4) the history records author and date
   2 records, 44 lines
```

## Structure

```
config-backup-switches/
├── src/cfgbackup/          # the package
├── dados/                  # inventory, declared changes
├── docs/                   # what not to compare, how to normalize
├── exemplos/               # generated history
├── tests/                  # 139 tests
└── tools/                  # generator and verification scripts
```

## Limitations

- **The configuration is synthetic.** Cisco IOS is the dialect, and the rule
  table has rules specific to it. A device from another family needs its own
  rules, and the table is where that discussion belongs.
- **Real SNMP does not deliver configuration**, it delivers MIB values. The
  SNMP path here returns a text synthesis in the same format as the HTTP path,
  and the point of the project is the comparison, not the transport.
- **The MAC table entry count is discarded** on purpose. Anyone who needs to
  know how many clients are connected reads the neighbour table, which is not in
  the backup.
- **Repeat collapsing does not know what a table is.** It merges any
  consecutive repetition. A rule that places two identical lines next to each
  other in a real configuration will have both merged.
- **Expiry uses the date you pass.** There is no clock of its own: a
  declaration with a past deadline expires during a 2019 collection, which is
  the right behaviour for a historical backup and not for a live alert.

## License

MIT.