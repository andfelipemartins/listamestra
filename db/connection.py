"""
db/connection.py

Fábrica de conexões SQLite para o SCLME.

Toda conexão aberta por este módulo garante:
- PRAGMA foreign_keys = ON  (integridade referencial enforçada)
- row_factory = sqlite3.Row  (acesso às colunas pelo nome)

Seleção de banco por modo (variável de ambiente `SCLME_DB_MODE`):
- `demo`            → data/demo/sclme_demo.db (fictício, versionado, p/ apresentação)
- qualquer outro    → db/sclme.db (operacional local, NÃO versionado)

Uso:
    from db.connection import get_connection

    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM documentos").fetchall()
"""

import os
import sqlite3
from typing import Optional

_BASE = os.path.dirname(__file__)
_PROJECT_ROOT = os.path.dirname(_BASE)

# Caminhos canônicos dos bancos.
DB_PATH_OPERACIONAL = os.path.join(_BASE, "sclme.db")
DB_PATH_DEMO = os.path.join(_PROJECT_ROOT, "data", "demo", "sclme_demo.db")


def modo_demo() -> bool:
    """True quando SCLME_DB_MODE=demo (case-insensitive)."""
    return os.environ.get("SCLME_DB_MODE", "").strip().lower() == "demo"


def resolver_db_path() -> str:
    """Caminho do banco conforme o modo atual (resolvido em tempo de chamada)."""
    return DB_PATH_DEMO if modo_demo() else DB_PATH_OPERACIONAL


# Compatibilidade: DB_PATH resolvido no import (consumido por vários módulos).
DB_PATH = resolver_db_path()


def _garantir_demo(path: str) -> None:
    """Gera o banco demo se ele for o alvo e ainda não existir (Streamlit Cloud).

    Falha silenciosa: se a geração não for possível, segue com o caminho — o
    sqlite criará um arquivo vazio e o app exibirá ausência de dados, sem quebrar.
    """
    if path != DB_PATH_DEMO or os.path.exists(path):
        return
    try:
        from scripts.create_demo_db import criar_banco_demo
        criar_banco_demo(path)
    except Exception:
        pass


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    Retorna uma conexão SQLite configurada.

    Sem `db_path`, resolve o banco pelo modo atual (`SCLME_DB_MODE`). Usar
    preferencialmente como context manager (with get_connection() as conn).
    """
    path = db_path or resolver_db_path()
    _garantir_demo(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn
