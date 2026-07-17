"""
db/connection.py

Fábrica de conexões SQLite para o SCLME.

Toda conexão aberta por este módulo garante:
- PRAGMA foreign_keys = ON  (integridade referencial enforçada)
- row_factory = sqlite3.Row  (acesso às colunas pelo nome)

Uso:
    from db.connection import get_connection

    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM documentos").fetchall()
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "sclme.db")


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """
    Retorna uma conexão SQLite configurada.
    Usar preferencialmente como context manager (with get_connection() as conn).
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn
