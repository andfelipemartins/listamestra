"""
scripts/init_db.py

Cria o banco de dados SQLite com todas as tabelas iniciais.

Execute uma vez antes de rodar o app:
    python scripts/init_db.py

Pode ser re-executado com segurança — usa CREATE TABLE IF NOT EXISTS.
"""

import sqlite3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db", "sclme.db")


DDL = """
-- ============================================================
-- Contratos / Obras
-- ============================================================
CREATE TABLE IF NOT EXISTS contratos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nome            TEXT NOT NULL,
    cliente         TEXT,
    descricao       TEXT,
    padrao_codigo   TEXT DEFAULT 'linha15_metro_sp',
    ativo           INTEGER DEFAULT 1,
    criado_em       TEXT DEFAULT (datetime('now'))
);

-- ============================================================
-- Documentos previstos (vindos do ID / Índice de Documentos)
-- ============================================================
CREATE TABLE IF NOT EXISTS documentos_previstos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    contrato_id     INTEGER NOT NULL REFERENCES contratos(id),
    codigo          TEXT NOT NULL,
    titulo          TEXT,
    tipo            TEXT,
    disciplina      TEXT,
    trecho          TEXT,
    status_id       TEXT,
    origem          TEXT DEFAULT 'importacao_id',
    ativo           INTEGER DEFAULT 1,
    criado_em       TEXT DEFAULT (datetime('now')),
    UNIQUE(contrato_id, codigo)
);

-- ============================================================
-- Documentos controlados
-- ============================================================
CREATE TABLE IF NOT EXISTS documentos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    contrato_id     INTEGER NOT NULL REFERENCES contratos(id),
    codigo          TEXT NOT NULL,
    tipo            TEXT,
    titulo          TEXT,
    disciplina      TEXT,
    modalidade      TEXT,
    trecho          TEXT,
    nome_trecho     TEXT,
    responsavel     TEXT,
    origem          TEXT DEFAULT 'importacao_lista',
    observacoes     TEXT,
    criado_em       TEXT DEFAULT (datetime('now')),
    atualizado_em   TEXT DEFAULT (datetime('now')),
    UNIQUE(contrato_id, codigo)
);

-- ============================================================
-- Revisões / versões
-- ============================================================
CREATE TABLE IF NOT EXISTS revisoes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    documento_id        INTEGER NOT NULL REFERENCES documentos(id),
    revisao             INTEGER,
    versao              INTEGER,
    label_revisao       TEXT,
    data_elaboracao     TEXT,
    data_emissao        TEXT,
    data_analise        TEXT,
    dias_elaboracao     INTEGER,
    dias_analise        INTEGER,
    situacao_real       TEXT,
    situacao            TEXT,
    retorno             TEXT,
    emissao_circular    TEXT,
    analise_circular    TEXT,
    ultima_revisao      INTEGER DEFAULT 0,
    origem              TEXT DEFAULT 'importacao_lista',
    importacao_id       INTEGER,
    criado_em           TEXT DEFAULT (datetime('now')),
    UNIQUE(documento_id, revisao, versao)
);

-- ============================================================
-- Arquivos físicos/digitais
-- ============================================================
CREATE TABLE IF NOT EXISTS arquivos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    documento_id        INTEGER REFERENCES documentos(id),
    nome_arquivo        TEXT NOT NULL,
    extensao            TEXT,
    caminho             TEXT,
    origem              TEXT,
    data_modificacao    TEXT,
    tamanho_bytes       INTEGER,
    revisao_detectada   TEXT,
    tipo_detectado      TEXT,
    importacao_id       INTEGER,
    criado_em           TEXT DEFAULT (datetime('now')),
    UNIQUE(documento_id, nome_arquivo)
);

-- ============================================================
-- Lotes de importação
-- ============================================================
CREATE TABLE IF NOT EXISTS importacoes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    contrato_id         INTEGER REFERENCES contratos(id),
    origem              TEXT,
    arquivo_importado   TEXT,
    total_registros     INTEGER DEFAULT 0,
    total_erros         INTEGER DEFAULT 0,
    total_novos         INTEGER DEFAULT 0,
    total_atualizados   INTEGER DEFAULT 0,
    status              TEXT DEFAULT 'pendente',
    usuario             TEXT,
    criado_em           TEXT DEFAULT (datetime('now')),
    confirmado_em       TEXT
);

-- ============================================================
-- Inconsistências detectadas durante importações
-- ============================================================
CREATE TABLE IF NOT EXISTS inconsistencias (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    importacao_id       INTEGER REFERENCES importacoes(id),
    documento_codigo    TEXT,
    tipo_inconsistencia TEXT,
    descricao           TEXT,
    resolvida           INTEGER DEFAULT 0,
    criado_em           TEXT DEFAULT (datetime('now'))
);

-- ============================================================
-- Índices para performance
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_documentos_codigo    ON documentos(codigo);
CREATE INDEX IF NOT EXISTS idx_documentos_contrato  ON documentos(contrato_id);
CREATE INDEX IF NOT EXISTS idx_revisoes_documento   ON revisoes(documento_id);
CREATE INDEX IF NOT EXISTS idx_revisoes_situacao    ON revisoes(situacao);
CREATE INDEX IF NOT EXISTS idx_previstos_codigo     ON documentos_previstos(codigo);
"""


def init_db(db_path: str = DB_PATH, verbose: bool = True):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(DDL)
        conn.commit()

    if verbose:
        print(f"✅ Banco inicializado em: {db_path}")
        with sqlite3.connect(db_path) as conn:
            tabelas = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            print(f"   Tabelas criadas: {[t[0] for t in tabelas]}")


if __name__ == "__main__":
    init_db()
