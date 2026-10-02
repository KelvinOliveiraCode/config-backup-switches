# Como normalizar uma configuração

Um equipamento com vida devolve uma configuração diferente a cada coleta. Não
porque alguém mexeu: porque o uptime avançou, um contador subiu, a tabela MAC
ganhou uma entrada. A diferença entre duas coletas de dez minutos de intervalo
tem linhas, e nenhuma delas é mudança de configuração.

Este documento explica **como** normalizar, e não **o quê**. A lista de regras e
o motivo de cada uma estão em [`o-que-nao-comparar.md`](o-que-nao-comparar.md).

## O problema com não normalizar

O efeito não é irritante, é destrutivo:

1. A primeira coleta gera 12 "mudanças".
2. Alguém abre o diff, vê que são uptime e contador, e fecha.
3. A segunda coleta gera 12 de novo.
4. Na terceira semana, alguém desativa o alerta porque é sempre ruído.
5. Alguém desabilita uma ACL de verdade. O alerta não dispara — porque foi
   desligado no passo 4.

O sistema que existe para avisar de mudança se anula sozinho. Nenhum passo
desse é irracional: cada um parece a decisão certa tomada com a informação
disponível naquele momento.

## Quatro perguntas antes de escrever uma regra

**Essa linha muda sozinha?** Uptime, contadores, data, MAC aprendido, sessão.
Resposta sim: regra de remover ou substituir.

**Ela muda junto com o que o equipamento está fazendo?** Conexões ativas, filas,
tabelas aprendidas. Resposta sim, mas a solução é outra: ver
[conjuntos que mudam de ordem](#conjuntos-que-mudam-de-ordem).

**Ela é segredo?** Senha em texto, hash, comunidade SNMP, chave. Substitua
pelo valor, e não remova: o diff precisa mostrar que o campo **existe**,
porque "não tem senha" e "a senha sumiu" são coisas diferentes.

**Ela descreve a configuração ou o momento?** Endereço IP de uma interface com
DHCP, rota aprendida por BGP. Se é o momento, ela pertence a uma tabela
operacional — e a resposta não é normalizar, é não coletar.

## Remover ou substituir

**Remover** a linha inteira, quando ela não carrega informação útil:

```
^!Last configuration change at .*$
```

**Substituir** quando o que importa é a **presença** do campo:

```
^(\s*)(snmp-server community \S+ \S+)( \S+)?.*$
```

Remover a linha da comunidade SNMP apagaria do diff a diferença entre
`snmp-server community X RO` e nenhuma linha — e essa é exatamente a mudança
que alguém quer ver.

## A ordem da tabela decide

A primeira regra que casa vence. Isso torna a ordem parte da semântica, e não
uma escolha de leitura:

```python
_r("uptime", r"^(\s*)(?:Uptime: )(.*)$", SUBSTITUIR, ...)
_r("memoria", r"^(\s*)(.*?)(Free Memory|Used Memory).*$", SUBSTITUIR, ...)
```

Com `uptime` antes de `memoria`, a linha `Uptime: 3 days` vira
`<UPTIME NORMALIZADO>`. Com a ordem invertida, uma regra geral demais captura
linhas que deviam ser preservadas — e a próxima pessoa não entende por que
`Free Memory` sumiu do backup.

Cada regra carrega seu **nome**, e o nome é o que aparece no relatório. É por
isso que nome duplicado é erro na carga: em qualquer lugar que use o nome como
chave, uma sobrescreve a outra.

## Conjuntos que mudam de ordem

Este é o caso que quebra a normalização linha a linha.

A tabela MAC e a tabela de sessões mudam de **ordem** a cada coleta, mesmo com
os mesmos clientes. Normalizar cada linha para o mesmo placeholder resolve o
conteúdo e não a ordem — e a diff linha a linha continua acusando seis
mudanças onde nada mudou.

A solução é fundir as repetições consecutivas depois de normalizar:

```
<tabela mac>
<tabela mac>
<tabela mac>
      vira
<TABELA MAC>
```

Só **consecutivas**, porque duas linhas de configuração idênticas que por acaso
ficam lado a lado são duplicata real, e escondê-la é pior do que exagerar o
diff.

## A contagem fica fora da linha

Depois da fusão, a linha é a mesma independente do tamanho da tabela — e é
correto. A **quantidade** de entradas é informação do momento, não da
configuração. Se ela ficasse no corpo da linha, um andar com gente entrando e
saindo geraria alerta a cada coleta.

Por isso o marcador é separado, e não concatenado. Quem precisa saber quantos
clientes estão conectados lê a tabela de vizinhos, que existe exatamente para
isso e não está no backup.

## O teste que prova que a normalização funciona

Um filtro de normalização que **acusa** tudo é tão inútil quanto um que não
acusa nada. A prova é negativa e tem que ser explícita:

```powershell
# duas coletas, ticks diferentes, nada alterado
python -m cfgbackup coletar --saida saida/a --ticks 7
python -m cfgbackup coletar --saida saida/b --ticks 23
python -m cfgbackup comparar --anterior saida/a --atual saida/b
# tem de sair: sem mudanca inesperada
```

O intervalo grande de propósito. Com ticks vizinhos, uma regra que só remove
`!Uptime is 6 days` passa o teste e falha no próximo minuto.

E o outro lado, que é tão importante quanto: um equipamento com uma linha de
configuração a mais **tem de acusar**. Sem o teste positivo, é fácil escrever
uma normalização que descarta a configuração inteira e passa em tudo.

## O que a tabela não cobre

A tabela é específica do dialeto. `o-que-nao-comparar.md` lista as regras que
apareceram em campo e ficaram de fora de propósito — porque o motivo de
excluir depende do equipamento, e uma regra "geral demais" é pior do que
nenhuma.

Quando um equipamento novo entrar na frota, a primeira tarefa é olhar o que a
tabela **não** cobre, e não rodar a coleta e ver o que aparece no diff.