"""
tests/test_importers/test_lista_importer.py

Testes do importador da Lista de Documentos (Excel → SQLite).

Execute com:
    pytest tests/ -v
"""

import os
import sys
import tempfile

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from core.importers.lista_importer import ListaImporter, ResultadoImportacao
from db.connection import get_connection

# Importa init_db para montar o schema em cada teste
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scripts"))
from init_db import init_db


# ---------------------------------------------------------------------------
# Helpers de fixture
# ---------------------------------------------------------------------------

def _linha(
    codigo: str,
    revisao = 1,
    versao: int = 1,
    sigla: str = "DE",
    trecho: int = 25,
    nome_trecho: str = "Ragueb Chohfi",
    modalidade: str = "CIVIL",
    estrutura: str = "REURBANIZAÇÃO - PAISAGISMO",
    elaboracao: str = "ROMA",
    descricao: str = "Adequação viária - elementos construtivos",
    situacao: str = "NÃO APROVADO",
    situacao_real: str = "NÃO LIBERADO",
    retorno: str = "575-23/10/2024",
    dias_elaboracao: int = 10,
    dias_analise: int = 16,
) -> list:
    """Cria uma linha com 62 colunas simulando a planilha real."""
    row = [None] * 62
    row[0]  = 1              # ITEM
    row[1]  = sigla          # SIGLA
    row[2]  = 15             # LINHA
    row[3]  = trecho         # TRECHO
    row[4]  = 0              # SUBTRECHO
    row[5]  = 0              # UNIDADE
    row[6]  = 6              # ETAPA
    row[7]  = "N3"           # CLASSE E SUBCLASSE
    row[8]  = 1001           # SEQUENCIAL
    row[9]  = codigo         # CÓDIGO
    row[10] = revisao        # REVISÃO
    row[11] = versao         # VERSÃO
    row[12] = nome_trecho    # NOME DO TRECHO
    row[13] = None           # EMISSÃO INICIAL
    row[14] = None           # ÚLTIMA REVISÃO
    row[15] = elaboracao     # ELABORAÇÃO
    row[16] = modalidade     # MODALIDADE
    row[17] = 6              # ETAPA (2ª coluna)
    row[18] = estrutura      # ESTRUTURA
    row[19] = descricao      # DESCRIÇÃO
    row[20] = 1              # FASE
    row[21] = "2024-09-27"   # DATA RECEBIMENTO/ELABORAÇÃO
    row[22] = "2024-10-07"   # DATA EMISSÃO
    row[23] = dias_elaboracao  # DIAS ELABORAÇÃO
    row[24] = "EMISSÃO INICIAL"  # EMISSÃO
    row[25] = "2024-10-23"   # DATA ANÁLISE
    row[26] = dias_analise   # DIAS ANÁLISE
    row[27] = situacao_real  # SITUAÇÃO REAL
    row[28] = situacao       # SITUAÇÃO
    row[29] = retorno        # RETORNO
    row[30] = None           # ANÁLISE INTERNA
    row[31] = None           # DATA CIRCULAR
    row[32] = None           # Nº CIRCULAR
    # Colunas 33-61: distribuição (ALYA / METRÔ) — não importadas no Marco 2
    return row


def _df(*linhas: list) -> pd.DataFrame:
    return pd.DataFrame(list(linhas))


# ---------------------------------------------------------------------------
# Fixture de banco de dados temporário
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    """Banco temporário com schema inicializado e um contrato de teste."""
    db_path = str(tmp_path / "test_sclme.db")
    init_db(db_path, verbose=False)
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO contratos (nome, cliente) VALUES ('Contrato Teste', 'Metrô SP')"
        )
        contrato_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return db_path, contrato_id


@pytest.fixture
def importer(db):
    db_path, _ = db
    return ListaImporter(db_path=db_path)


# ---------------------------------------------------------------------------
# Testes de importação básica
# ---------------------------------------------------------------------------

class TestImportacaoBasica:

    def test_importa_documento_simples(self, db, importer):
        db_path, contrato_id = db
        resultado = importer._importar_df(
            _df(_linha("DE-15.25.00.00-6N3-1001")), "test.xlsx", contrato_id
        )

        assert resultado.novos_documentos == 1
        assert resultado.novas_revisoes == 1
        assert resultado.erros == 0

        with get_connection(db_path) as conn:
            doc = conn.execute(
                "SELECT * FROM documentos WHERE codigo = ?", ("DE-15.25.00.00-6N3-1001",)
            ).fetchone()
        assert doc is not None
        assert doc["tipo"] == "DE"
        assert doc["trecho"] == "25"
        assert doc["nome_trecho"] == "Ragueb Chohfi"
        assert doc["modalidade"] == "CIVIL"
        assert doc["responsavel"] == "ROMA"

    def test_revisao_campos_gravados(self, db, importer):
        db_path, contrato_id = db
        importer._importar_df(
            _df(_linha("DE-15.25.00.00-6N3-1001", revisao=1, dias_elaboracao=10, dias_analise=16)),
            "test.xlsx", contrato_id,
        )

        with get_connection(db_path) as conn:
            rev = conn.execute(
                "SELECT r.* FROM revisoes r JOIN documentos d ON r.documento_id = d.id WHERE d.codigo = ?",
                ("DE-15.25.00.00-6N3-1001",),
            ).fetchone()
        assert rev["revisao"] == 1
        assert rev["versao"] == 1
        assert rev["label_revisao"] == "1"
        assert rev["dias_elaboracao"] == 10
        assert rev["dias_analise"] == 16
        assert rev["situacao"] == "NÃO APROVADO"
        assert rev["situacao_real"] == "NÃO LIBERADO"

    def test_multiplos_documentos_distintos(self, db, importer):
        db_path, contrato_id = db
        resultado = importer._importar_df(
            _df(
                _linha("DE-15.25.00.00-6N3-1001", sigla="DE"),
                _linha("MD-15.25.00.00-6N3-1001", sigla="MD"),
                _linha("MC-15.25.00.00-6N3-1001", sigla="MC"),
            ),
            "test.xlsx", contrato_id,
        )

        assert resultado.novos_documentos == 3
        assert resultado.novas_revisoes == 3
        assert resultado.total_lidas == 3

    def test_trecho_zero_formatado_com_dois_digitos(self, db, importer):
        db_path, contrato_id = db
        importer._importar_df(
            _df(_linha("PE-15.00.00.00-6A9-1002", trecho=0, sigla="PE")),
            "test.xlsx", contrato_id,
        )

        with get_connection(db_path) as conn:
            doc = conn.execute(
                "SELECT trecho FROM documentos WHERE codigo = ?", ("PE-15.00.00.00-6A9-1002",)
            ).fetchone()
        assert doc["trecho"] == "00"


# ---------------------------------------------------------------------------
# Testes de múltiplas revisões
# ---------------------------------------------------------------------------

class TestMultiplasRevisoes:

    def test_mesmo_codigo_duas_revisoes(self, db, importer):
        db_path, contrato_id = db
        resultado = importer._importar_df(
            _df(
                _linha("DE-15.25.00.00-6N3-1001", revisao=1),
                _linha("DE-15.25.00.00-6N3-1001", revisao=2),
            ),
            "test.xlsx", contrato_id,
        )

        # Apenas 1 documento, mas 2 revisões
        assert resultado.novos_documentos == 1
        assert resultado.documentos_atualizados == 1
        assert resultado.novas_revisoes == 2

        with get_connection(db_path) as conn:
            docs = conn.execute(
                "SELECT COUNT(*) AS n FROM documentos WHERE codigo = ?",
                ("DE-15.25.00.00-6N3-1001",),
            ).fetchone()
            revs = conn.execute(
                "SELECT revisao, ultima_revisao FROM revisoes r "
                "JOIN documentos d ON r.documento_id = d.id "
                "WHERE d.codigo = ? ORDER BY revisao",
                ("DE-15.25.00.00-6N3-1001",),
            ).fetchall()
        assert docs["n"] == 1
        assert len(revs) == 2

    def test_ultima_revisao_marcada_corretamente(self, db, importer):
        db_path, contrato_id = db
        importer._importar_df(
            _df(
                _linha("DE-15.25.00.00-6N3-1001", revisao=1),
                _linha("DE-15.25.00.00-6N3-1001", revisao=2),
                _linha("DE-15.25.00.00-6N3-1001", revisao=3),
            ),
            "test.xlsx", contrato_id,
        )

        with get_connection(db_path) as conn:
            revs = conn.execute(
                "SELECT revisao, ultima_revisao FROM revisoes r "
                "JOIN documentos d ON r.documento_id = d.id "
                "WHERE d.codigo = ? ORDER BY revisao",
                ("DE-15.25.00.00-6N3-1001",),
            ).fetchall()

        ultimas = [r for r in revs if r["ultima_revisao"] == 1]
        assert len(ultimas) == 1
        assert ultimas[0]["revisao"] == 3

    def test_ultima_revisao_dois_documentos_independentes(self, db, importer):
        db_path, contrato_id = db
        importer._importar_df(
            _df(
                _linha("DE-15.25.00.00-6N3-1001", revisao=1),
                _linha("DE-15.25.00.00-6N3-1001", revisao=2),
                _linha("MD-15.25.00.00-6N3-1001", sigla="MD", revisao=1),
            ),
            "test.xlsx", contrato_id,
        )

        with get_connection(db_path) as conn:
            ultimas = conn.execute(
                "SELECT d.codigo, r.revisao FROM revisoes r "
                "JOIN documentos d ON r.documento_id = d.id "
                "WHERE r.ultima_revisao = 1 ORDER BY d.codigo"
            ).fetchall()

        assert len(ultimas) == 2
        by_codigo = {r["codigo"]: r["revisao"] for r in ultimas}
        assert by_codigo["DE-15.25.00.00-6N3-1001"] == 2
        assert by_codigo["MD-15.25.00.00-6N3-1001"] == 1


# ---------------------------------------------------------------------------
# Testes de reimportação (idempotência)
# ---------------------------------------------------------------------------

class TestReimportacao:

    def test_reimportacao_nao_duplica_documento(self, db, importer):
        db_path, contrato_id = db
        df = _df(_linha("DE-15.25.00.00-6N3-1001"))
        importer._importar_df(df, "test.xlsx", contrato_id)
        importer._importar_df(df, "test.xlsx", contrato_id)

        with get_connection(db_path) as conn:
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM documentos WHERE codigo = ?",
                ("DE-15.25.00.00-6N3-1001",),
            ).fetchone()["n"]
        assert n == 1

    def test_reimportacao_nao_duplica_revisao(self, db, importer):
        db_path, contrato_id = db
        df = _df(_linha("DE-15.25.00.00-6N3-1001", revisao=1))
        importer._importar_df(df, "test.xlsx", contrato_id)
        importer._importar_df(df, "test.xlsx", contrato_id)

        with get_connection(db_path) as conn:
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM revisoes r "
                "JOIN documentos d ON r.documento_id = d.id WHERE d.codigo = ?",
                ("DE-15.25.00.00-6N3-1001",),
            ).fetchone()["n"]
        assert n == 1

    def test_segunda_importacao_conta_como_atualizado(self, db, importer):
        db_path, contrato_id = db
        df = _df(_linha("DE-15.25.00.00-6N3-1001"))
        importer._importar_df(df, "test.xlsx", contrato_id)
        resultado2 = importer._importar_df(df, "test.xlsx", contrato_id)

        assert resultado2.novos_documentos == 0
        assert resultado2.documentos_atualizados == 1
        assert resultado2.novas_revisoes == 0
        assert resultado2.revisoes_atualizadas == 1


# ---------------------------------------------------------------------------
# Testes de inconsistências / códigos inválidos
# ---------------------------------------------------------------------------

class TestInconsistencias:

    def test_codigo_invalido_registra_inconsistencia(self, db, importer):
        db_path, contrato_id = db
        resultado = importer._importar_df(
            _df(_linha("CODIGO_INVALIDO")), "test.xlsx", contrato_id
        )

        assert any(i["tipo"] == "codigo_invalido" for i in resultado.inconsistencias)

        with get_connection(db_path) as conn:
            incs = conn.execute("SELECT * FROM inconsistencias").fetchall()
        assert len(incs) > 0
        assert incs[0]["tipo_inconsistencia"] == "codigo_invalido"

    def test_codigo_invalido_nao_impede_demais_linhas(self, db, importer):
        db_path, contrato_id = db
        resultado = importer._importar_df(
            _df(
                _linha("CODIGO_INVALIDO"),
                _linha("DE-15.25.00.00-6N3-1001"),
            ),
            "test.xlsx", contrato_id,
        )

        # Documento inválido ainda é inserido (código é armazenado mesmo sem parse ok)
        assert resultado.total_lidas == 2
        assert resultado.erros == 0  # erro_processamento não ocorreu
        assert len(resultado.inconsistencias) >= 1

    def test_linha_com_codigo_vazio_ignorada(self, db, importer):
        db_path, contrato_id = db
        linha_vazia = _linha("DE-15.25.00.00-6N3-1001")
        linha_vazia[9] = None  # zera o CÓDIGO

        resultado = importer._importar_df(
            _df(_linha("DE-15.25.00.00-6N3-1001"), linha_vazia),
            "test.xlsx", contrato_id,
        )
        # _ler_planilha filtra linhas com código vazio, mas aqui chamamos _importar_df
        # diretamente com o DataFrame sem filtro — a linha vazia vai para processamento
        # e gera inconsistência ou erro
        assert resultado.total_lidas == 2


# ---------------------------------------------------------------------------
# Testes da tabela importacoes
# ---------------------------------------------------------------------------

class TestRegistroImportacao:

    def test_importacao_registrada(self, db, importer):
        db_path, contrato_id = db
        resultado = importer._importar_df(
            _df(_linha("DE-15.25.00.00-6N3-1001")), "lista_mestra.xlsx", contrato_id
        )

        with get_connection(db_path) as conn:
            imp = conn.execute(
                "SELECT * FROM importacoes WHERE id = ?", (resultado.importacao_id,)
            ).fetchone()

        assert imp is not None
        assert imp["status"] == "concluido"
        assert imp["arquivo_importado"] == "lista_mestra.xlsx"
        assert imp["total_registros"] == 1
        assert imp["origem"] == "lista_documentos"

    def test_duas_importacoes_geram_dois_registros(self, db, importer):
        db_path, contrato_id = db
        df = _df(_linha("DE-15.25.00.00-6N3-1001"))
        r1 = importer._importar_df(df, "v1.xlsx", contrato_id)
        r2 = importer._importar_df(df, "v2.xlsx", contrato_id)

        assert r1.importacao_id != r2.importacao_id

        with get_connection(db_path) as conn:
            total = conn.execute("SELECT COUNT(*) AS n FROM importacoes").fetchone()["n"]
        assert total == 2

    def test_contagens_na_importacao_conferem(self, db, importer):
        db_path, contrato_id = db
        resultado = importer._importar_df(
            _df(
                _linha("DE-15.25.00.00-6N3-1001"),
                _linha("MD-15.25.00.00-6N3-1001", sigla="MD"),
            ),
            "test.xlsx", contrato_id,
        )

        with get_connection(db_path) as conn:
            imp = conn.execute(
                "SELECT * FROM importacoes WHERE id = ?", (resultado.importacao_id,)
            ).fetchone()

        assert imp["total_novos"] == 2
        assert imp["total_atualizados"] == 0
        assert imp["total_erros"] == 0  # nenhuma inconsistência nem exceção


# ---------------------------------------------------------------------------
# Testes de propriedades de ResultadoImportacao
# ---------------------------------------------------------------------------

class TestResultadoImportacao:

    def test_total_documentos_e_soma(self, db, importer):
        db_path, contrato_id = db
        df = _df(
            _linha("DE-15.25.00.00-6N3-1001"),
            _linha("MD-15.25.00.00-6N3-1001", sigla="MD"),
        )
        resultado = importer._importar_df(df, "test.xlsx", contrato_id)
        assert resultado.total_documentos == resultado.novos_documentos + resultado.documentos_atualizados

    def test_total_revisoes_e_soma(self, db, importer):
        db_path, contrato_id = db
        resultado = importer._importar_df(
            _df(
                _linha("DE-15.25.00.00-6N3-1001", revisao=1),
                _linha("DE-15.25.00.00-6N3-1001", revisao=2),
            ),
            "test.xlsx", contrato_id,
        )
        assert resultado.total_revisoes == resultado.novas_revisoes + resultado.revisoes_atualizadas
        assert resultado.total_revisoes == 2

    def test_total_inconsistencias_reflete_lista(self, db, importer):
        db_path, contrato_id = db
        resultado = importer._importar_df(
            _df(_linha("CODIGO_INVALIDO")), "test.xlsx", contrato_id
        )
        assert resultado.total_inconsistencias == len(resultado.inconsistencias)
        assert resultado.total_inconsistencias >= 1


# ---------------------------------------------------------------------------
# Testes de semântica do log de importação (total_erros)
# ---------------------------------------------------------------------------

class TestTotalErros:

    def test_codigo_invalido_aparece_em_total_erros(self, db, importer):
        db_path, contrato_id = db
        resultado = importer._importar_df(
            _df(_linha("CODIGO_INVALIDO")), "test.xlsx", contrato_id
        )

        with get_connection(db_path) as conn:
            imp = conn.execute(
                "SELECT total_erros FROM importacoes WHERE id = ?", (resultado.importacao_id,)
            ).fetchone()

        # total_erros inclui inconsistências de validação, não só exceções
        assert imp["total_erros"] >= 1

    def test_importacao_limpa_tem_zero_erros(self, db, importer):
        db_path, contrato_id = db
        resultado = importer._importar_df(
            _df(_linha("DE-15.25.00.00-6N3-1001")), "test.xlsx", contrato_id
        )

        with get_connection(db_path) as conn:
            imp = conn.execute(
                "SELECT total_erros FROM importacoes WHERE id = ?", (resultado.importacao_id,)
            ).fetchone()

        assert imp["total_erros"] == 0


# ---------------------------------------------------------------------------
# Testes de label de revisão (numérico vs. textual)
# ---------------------------------------------------------------------------

class TestLabelRevisao:

    def test_label_numerico_preservado(self, db, importer):
        db_path, contrato_id = db
        importer._importar_df(_df(_linha("DE-15.25.00.00-6N3-1001", revisao=1)), "test.xlsx", contrato_id)
        with get_connection(db_path) as conn:
            rev = conn.execute(
                "SELECT revisao, label_revisao FROM revisoes r "
                "JOIN documentos d ON r.documento_id=d.id WHERE d.codigo=?",
                ("DE-15.25.00.00-6N3-1001",),
            ).fetchone()
        assert rev["revisao"] == 1
        assert rev["label_revisao"] == "1"

    def test_label_texto_preservado(self, db, importer):
        """Revisão 'A' deve ser salva como label_revisao='A', revisao=None."""
        db_path, contrato_id = db
        importer._importar_df(_df(_linha("DE-15.25.00.00-6N3-1001", revisao="A")), "test.xlsx", contrato_id)
        with get_connection(db_path) as conn:
            rev = conn.execute(
                "SELECT revisao, label_revisao FROM revisoes r "
                "JOIN documentos d ON r.documento_id=d.id WHERE d.codigo=?",
                ("DE-15.25.00.00-6N3-1001",),
            ).fetchone()
        assert rev["label_revisao"] == "A"
        assert rev["revisao"] is None

    def test_label_texto_alfanumerico(self, db, importer):
        db_path, contrato_id = db
        importer._importar_df(_df(_linha("DE-15.25.00.00-6N3-1001", revisao="B1")), "test.xlsx", contrato_id)
        with get_connection(db_path) as conn:
            rev = conn.execute(
                "SELECT label_revisao FROM revisoes r "
                "JOIN documentos d ON r.documento_id=d.id WHERE d.codigo=?",
                ("DE-15.25.00.00-6N3-1001",),
            ).fetchone()
        assert rev["label_revisao"] == "B1"

    def test_label_texto_nao_e_zero(self, db, importer):
        """Revisão textual nunca deve virar '0' (o literal para revisão numérica zero)."""
        db_path, contrato_id = db
        importer._importar_df(_df(_linha("DE-15.25.00.00-6N3-1001", revisao="A1")), "test.xlsx", contrato_id)
        with get_connection(db_path) as conn:
            rev = conn.execute(
                "SELECT label_revisao FROM revisoes r "
                "JOIN documentos d ON r.documento_id=d.id WHERE d.codigo=?",
                ("DE-15.25.00.00-6N3-1001",),
            ).fetchone()
        assert rev["label_revisao"] != "0"
        assert rev["label_revisao"] == "A1"

    def test_duas_revisoes_texto_distintas_inseridas(self, db, importer):
        """Duas revisões textuais diferentes (A e B) devem gerar dois registros."""
        db_path, contrato_id = db
        resultado = importer._importar_df(
            _df(
                _linha("DE-15.25.00.00-6N3-1001", revisao="A"),
                _linha("DE-15.25.00.00-6N3-1001", revisao="B"),
            ),
            "test.xlsx", contrato_id,
        )
        assert resultado.novas_revisoes == 2
        with get_connection(db_path) as conn:
            labels = [r["label_revisao"] for r in conn.execute(
                "SELECT label_revisao FROM revisoes r "
                "JOIN documentos d ON r.documento_id=d.id WHERE d.codigo=? ORDER BY r.id",
                ("DE-15.25.00.00-6N3-1001",),
            ).fetchall()]
        assert labels == ["A", "B"]

    def test_reimportacao_revisao_texto_nao_duplica(self, db, importer):
        """Reimportar a mesma revisão textual não cria duplicata."""
        db_path, contrato_id = db
        df = _df(_linha("DE-15.25.00.00-6N3-1001", revisao="A"))
        importer._importar_df(df, "test.xlsx", contrato_id)
        importer._importar_df(df, "test.xlsx", contrato_id)
        with get_connection(db_path) as conn:
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM revisoes r "
                "JOIN documentos d ON r.documento_id=d.id WHERE d.codigo=?",
                ("DE-15.25.00.00-6N3-1001",),
            ).fetchone()["n"]
        assert n == 1


# ---------------------------------------------------------------------------
# Testes de integridade de schema (UNIQUE em revisoes)
# ---------------------------------------------------------------------------

class TestIntegridadeSchema:

    def test_unique_revisao_impedido_por_insert_direto(self, db):
        db_path, contrato_id = db
        import sqlite3

        with get_connection(db_path) as conn:
            conn.execute(
                "INSERT INTO documentos (contrato_id, codigo, tipo) VALUES (?, ?, ?)",
                (contrato_id, "DE-15.25.00.00-6N3-9999", "DE"),
            )
            doc_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute(
                "INSERT INTO revisoes (documento_id, revisao, versao) VALUES (?, 1, 1)",
                (doc_id,),
            )
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO revisoes (documento_id, revisao, versao) VALUES (?, 1, 1)",
                    (doc_id,),
                )
