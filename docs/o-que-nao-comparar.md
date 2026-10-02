# O que não comparar

Este é o arquivo mais útil do repositório na prática.

Um equipamento com vida devolve uma configuração diferente a cada coleta. Não
porque alguém mexeu: porque o uptime avançou, um contador subiu, a tabela MAC
ganhou uma entrada. Sem normalizar, a diferença entre duas coletas de dez
minutos intervalo tem 14 linhas, e nenhuma delas é mudança.

O efeito é worse que irritante. O alerta dispara todo dia, ninguém olha, e na
semana em que alguém **realmente** desabilitou uma ACL o sistema já está
marcado como crywolf. Aí ninguém lê mais.

Por isso cada regra abaixo carrega **por que** ela existe, e não só o que ela
remove. Sem o porquê, a próxima pessoa aumenta o filtro por intuição e apaga uma
regra que estava certa.

## Resumo

| Regra | Ação | Uma frase |
|---|---|---|
| `data-ultima-mudanca` | remover | Horário da última gravação, muda sozinho |
| `data-nvram` | remover | Idem, marca de tempo do aparelho |
| `comentario-de-marcacao` | remover | Aponta de qual arquivo a config veio |
| `versao-do-sistema` | remover | Versão de firmware, muda em atualização |
| `uptime` | substituir | Tempo de operação, avança a cada segundo |
| `tempo-de-relogio` | substituir | Origem do NTP muda com a topologia |
| `numero-de-serie` | substituir | Identifica o aparelho físico, e é segredo |
| `endereco-mac-base` | substituir | Três octetos identificam a interface |
| `contador-de-pacotes` | substituir | Contadores de tráfego sobem a cada pacote |
| `memoria` | substituir | Quantidade livre varia com qualquer coisa |
| `buffer-de-log` | substituir | Contagem de linhas do log só cresce |
| `entrada-da-tabela-mac` | substituir | Tabela aprendida, muda de ordem e tamanho |
| `numero-de-conexao` | substituir | Numeração de sessão é efêmera |
| `hash-de-senha` | substituir | Hash muda a cada troca e não vai para log |
| `cabecalho-de-coleta` | remover | Carimba da coleta, e traz o número de série |
| `chave-criptografica` | substituir | Comunidade SNMP é segredo |

## `data-ultima-mudanca`

```
^!Last configuration change at .*$
```

O equipamento carimba a hora da última gravação **a cada vez que a configuração
é salva**, e não apenas quando o conteúdo muda. Salvar a mesma configuração de
volta duas vezes produz duas datas diferentes e zero diferenças de verdade.

O que me fez criar a regra: um equipamento que recebia `copy running-config
startup-config` de um script de backup todo dia. Toda noite, uma "mudança". O
script era inofensivo; o alerta era ruído puro.

## `data-nvram`

```
^!NVRAM config last updated at .*$
```

Mesma marca de tempo, dita de outro jeito. Aparece junto com a anterior em
`show running-config` e em `show startup-config`. Uma regra só com esta
resolveria; as duas existem porque a ordem das linhas varia entre modelos e
uma delas às vezes vem sem a outra.

## `comentario-de-marcacao`

```
^!.*configuration (from )?flash.*$
```

Aponta de qual arquivo de memória a configuração foi carregada. O mesmo estado
de configuração é `running-config` num equipamento e `startup-config` em outro,
por causa de como cada família de fabricante trata o boot. Comparar esse
comentário acusa mudança entre dois equipamentos **iguais**, que é a pior
falsa positiva possível: ela treina o leitor a desconfiar do próprio alerta.

## `versao-do-sistema`

```
^!Software Version .*$
```

A versão só muda quando há atualização de firmware, e atualização é um processo
planejado com janela, teste e aprovação prprpria. Se o resto das linhas é
idêntico, a diferença de texto na versão não informa nada de útil — e o
responsável pela atualização já tem o próprio registro.

Se você quiser que a atualização **vire** alerta, não é aqui: é uma mudança
esperada, declarada antes, como a de firmware dos outros projetos.

## `uptime`

```
^(\s*)(?:!(?:SNMP agent )?[Uu]ptime is |Uptime: )(.*)$
```

O uptime avança a cada segundo. Duas coletas com dez minutos de intervalo
têm 600 segundos de diferença e nenhuma mudança de configuração.

Trocar por placeholder fixo é o mínimo. Trocar só o **número** e manter a
unidade (`!Uptime is 6 days` para `!Uptime is <NORMALIZADO>`) é o mínimo também,
mas a segunda linha do placeholder é melhor: a unidade carrega informação de
que o aparelho está de pé há **mais de um dia**, o que muda o cálculo de
quando o último reboot ocorreu. Se o seu caso precisa disso, defina a regra
com duas partes em vez de apagar o dia inteiro.

## `tempo-de-relogio`

```
^(\s*)(Time source is ).*$
```

A origem do relógio muda com a topologia de NTP. Quando o servidor de tempo
da filial cai e o equipamento passa a usar outro, a configuração não mudou —
o **ambiente** mudou. Mas o alerta dispararia, e alguém passaria uma hora
procuro uma alteração de configuração que não existe.

## `numero-de-serie`

```
^(\s*)(serial (\w+) )(\S+).*$
```

O número de série identifica o aparelho físico. Dois backups do mesmo
equipamento têm o mesmo série — então, por que normalizar?

Porque ele também aparece na **troca de unidade**, e a revisão que acompanha um
backup não distingue "configurei outra coisa" de "troquei o switch". Além
disso, número de série em log e em histórico versionado é informação que não
precisa circular.

A regra preserva a palavra `serial` e a posição da linha, e substitui só o
valor: o diff continua dizendo que existe um número de série, sem dizer qual.

## `endereco-mac-base`

```
\b(?:[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}|[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2})\.[0-9a-fA-F]{2}(?:[0-9a-fA-F]{2}|[0-9a-fA-F]{2}:[0-9a-fA-F]{2})\b
```

Os três primeiros octetos do MAC são o **fabricante** — é o número da OUI, e é
estável. Os três últimos identificam a **interface**, e mudam com o slot
físico, com a stack e com o tipo de placa.

Comparar o endereço inteiro acusa troca de porta como mudança de
configuração. Em um chassi modular, trocar uma linha de cards renumera as
interfaces: mesmo wiring, mesmo comportamento, dez "mudanças" no diff.

O padrão aceita os dois formatos de MAC porque os equipamentos escrevem de
jeito diferente: `aabb.ccdd.eeff` (Cisco) e `aa:bb:cc:dd:ee:ff` ( Juniper,
Linux, ARP). Uma regra que só conhece o primeiro deixa a tabela do segundo
vazando inteira para o diff.

## `contador-de-pacotes`

```
^(\s*)(.*?)(\d+ packets input.*|\d+ packets output.*|\d+ bytes.*)$
```

Contadores sobem a cada pacote, então sobem sempre. Um `show running-config`
não deveria conter contadores — quando contém, veio de `show tech` ou de um
template que os interpôs.

O efeito de não normalizar é o pior caso conhecido: **o diff fica ilegível**.
Milhares de linhas de contador, todas diferentes, enterrando a meia dúzia de
linhas de configuração que são o que interessa.

## `memoria`

```
^(\s*)(.*?)(Free Memory|Used Memory|Total Memory).*$
```

Quantidade de memória livre muda com qualquer coisa, inclusive com o próprio
backup rodando. Não é configuração.

## `buffer-de-log`

```
^(\s*)(logging buffer: .*lines logged )(\d+).*$
```

A contagem de linhas do buffer só cresce. E ela cresce **por causa do alerta**:
o alerta dispara, alguém entra no equipamento, e o debug que a pessoa deixou
ligado para investigar preenche o buffer. A partir daí, todo backup seguinte
acusa uma mudança — que foi causada pela tentativa de investigar a mudança
anterior.

Este é o efeito que faz um sistema de detecção de drift se anular sozinho.

## `entrada-da-tabela-mac`

```
^\s+\d+\s+(?:[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}|(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2})\s+.*$
```

A tabela MAC é **estado operacional aprendido**, não configuração. O switch a
monta a partir de quem conversou com ele, e ela tem duas propriedades que
importam:

- **muda de ordem** a cada coleta, mesmo com os mesmos clientes;
- **muda de tamanho**, conforme gente entra e sai.

Normalizar cada linha para o mesmo placeholder resolve a primeira metade e
não a segunda. Com a ordem trocada, a diff linha a linha continuaria acusando
seis mudanças onde nada mudou. Por isso existe a fusão de repetidas
consecutivas: a tabela inteira vira uma linha, e o que muda é a contagem —
que fica **fora** do corpo da linha, num marcador à parte.

Isso é deliberado. A quantidade de clientes conectados é informação de
momento, não de configuração: se a contagem fosse comparada, ela viraria um
alerta a cada coleta. Quem precisa de contagem lê a tabela de vizinhos, que
existe justamente para isso e **não** está no backup.

## `numero-de-conexao`

```
^(\s*)(\d+)\s+(active|open)\s+.*$
```

Numeração de sessão é efêmera, e a ordem delas muda a cada coleta. Mesma
razão da tabela MAC: mesmo placeholder, mesma fusão.

## `hash-de-senha`

```
^(\s*)(username \S+ (password|secret) \d) .*$
```

O hash muda a cada troca de senha e **nunca** deve ser comparado nem impresso
em log ou histórico versionado. Um repositório de backup com hash de senha é um
repositório de credencial — e o `git log` guarda a versão anterior mesmo que
você apague a linha.

O que interessa é **existir** uma senha, e o que ela autentica. A regra
substitui o valor e mantém o tipo (`password` ou `secret`) e o algoritmo, que
continuam legíveis.

## `cabecalho-de-coleta`

```
^(?:###\s*colhido via SNMP em \d+|#\s*exportado via HTTP em \d+)(?:\s*###.*|\s*#.*)?$
```

O cabeçalho que o coletor coloca no topo do arquivo é **acréscimo da coleta**,
não parte da configuração. Ele carrega o número da coleta e, na via SNMP, o
número de série do equipamento.

Sem remover, uma diferença de coluna aparece no diff de todo equipamento e
nenhuma configuração mudou. E o número de série no cabeçalho continua
circulando em cada backup, por cima de todo o cuidado da regra
`numero-de-serie`.

## `chave-criptografica`

```
^(\s*)(snmp-server community \S+ \S+)( \S+)?.*$
```

Comunidade SNMP é segredo. A mesma razão do hash: não vai para log nem para
histórico. A regra substitui o valor, mas preserva a community e o modo de
acesso (`RO` ou `RW`), que continuam legíveis no diff — e é isso que importa
para auditoria: ver que a community existe e em que modo, não qual é.

## Regras que não existem e deviam existir

Nenhuma regra a mais está na tabela, e esta é a lista do que apareceu em campo
e **não** foi incluído. Ficam fora de propósito, porque o motivo de cada uma
depende do equipamento.

**Linhas de BGP com timestamp interno.** `<router-id>` e a lista de
neighbors mudam de ordem quando um session flap. Comparado como está, um flap
de dois segundos vira mudança de configuração. Comparado sem a lista, some a
informação de que o session existe. Trate com uma regra que guarda a contagem
como a tabela MAC.

**Contadores de interface em formato SNMP `ifInOctets`.** Hoje não há regra
para a saída crua do SNMP, só para a linha legível de `show tech`. Uma coleta
SNMP pura devolve contadores que a tabela atual não toca.

**Linhas de log que o equipamento imprime dentro da configuração.** Alguns
modelos imprimem `Last message repeated 5 times` no meio do output. É estado
do buffer aparecendo onde não deveria, e nenhuma regra remove.

**Timestamps em caminho de log.** `logging buffered 4096 informational` tem
tamanho fixo, mas `show logging` tem contagem e também tem "x`dr repetitions".
Precisa de regra própria quando alguém implementa coleta de log além da
configuração.

**Hostname e banner.** A maioria das ferramentas trata o hostname como
configuração — e é. Mas quando o equipamento está em DHCP com nome dinâmico, o
hostname muda sozinho e vira alerta diário. Nesse caso a regra existe e é
específica do ambiente.
