"""cfgbackup - backup de configuracao com deteccao de mudanca.

cfgbackup - configuration backup with change detection.

Coleta configuracao de equipamentos de rede **ficticios** por SNMP e por
interface HTTP simuladas, normaliza antes de comparar, e classifica a mudanca
em tres estados: sem mudanca, mudanca esperada e mudanca inesperada. Nenhum
equipamento real e acessado.
"""

__version__ = "1.0.0"

__all__ = [
    "__version__",
    "coletor",
    "diferenca",
    "historico",
    "normalizador",
    "simulador",
]