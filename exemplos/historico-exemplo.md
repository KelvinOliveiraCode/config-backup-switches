# Historico de mudancas de configuracao

> Documento gerado por `cfgbackup`. As configuracoes sao ficticias:
> nenhum equipamento real e acessado.

---
## SW-LAB-02 - sem mudanca

- **data**: 2026-01-15 14:00
- **operador**: sistema de backup
- **estado**: `sem_mudanca`
- **mudancas**: 0 (0 esperada(s), 0 inesperada(s))

As configuracoes normalizadas sao identicas. Nenhuma linha sobreviveu a tabela de normalizacao como diferenca.
---

## SW-LAB-01 - sem mudanca

- **data**: 2026-01-15 14:00
- **operador**: sistema de backup
- **estado**: `sem_mudanca`
- **mudancas**: 0 (0 esperada(s), 0 inesperada(s))

As configuracoes normalizadas sao identicas. Nenhuma linha sobreviveu a tabela de normalizacao como diferenca.
---

## FW-LAB-01 - sem mudanca

- **data**: 2026-01-15 14:00
- **operador**: sistema de backup
- **estado**: `sem_mudanca`
- **mudancas**: 0 (0 esperada(s), 0 inesperada(s))

As configuracoes normalizadas sao identicas. Nenhuma linha sobreviveu a tabela de normalizacao como diferenca.
---

## SW-LAB-02 - MUDANCA INESPERADA

- **data**: 2026-01-20 09:30
- **operador**: kelvin
- **estado**: `inesperada`
- **mudancas**: 2 (1 esperada(s), 1 inesperada(s))

```diff
--- SW-LAB-02 (anterior)
+++ SW-LAB-02 (atual)
@@ -0,0 +1,2 @@
+ line vty 0 4
+  exec-timeout 5 0
```

### Mudancas declaradas previamente

- + exec-timeout 5 0  (esperada: reducao do timeout de sessao conforme politica de seguranca de 2026-01)

### Mudancas nao declaradas (drift)

- + line vty 0 4
---

## SW-LAB-01 - MUDANCA INESPERADA

- **data**: 2026-01-20 09:30
- **operador**: kelvin
- **estado**: `inesperada`
- **mudancas**: 1 (0 esperada(s), 1 inesperada(s))

```diff
--- SW-LAB-01 (anterior)
+++ SW-LAB-01 (atual)
@@ -0,0 +1 @@
+ spanning-tree mode rapid-pvst
```

### Mudancas nao declaradas (drift)

- + spanning-tree mode rapid-pvst
---

## FW-LAB-01 - MUDANCA INESPERADA

- **data**: 2026-01-20 09:30
- **operador**: kelvin
- **estado**: `inesperada`
- **mudancas**: 1 (0 esperada(s), 1 inesperada(s))

```diff
--- FW-LAB-01 (anterior)
+++ FW-LAB-01 (atual)
@@ -0,0 +1 @@
+ access-list 100 permit tcp any any eq 8080
```

### Mudancas nao declaradas (drift)

- + access-list 100 permit tcp any any eq 8080
---

