"""
tests/test_engine/test_pendencias.py

Testes das onze categorias calculadas pelo motor de pendencias.
"""

import os
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from core.engine.comparacao import comparar_id_lista
from core.engine.pendencias import Pendencia, TipoPendencia, detectar_pendencias
from core.repositories.contract_repository import ContractRepository
from core.repositories.documento_repository import DocumentoRepository
from core.repositories.revisao_repository import RevisaoRepository
from db.connection import get_connection
from scripts.init_db import init_db


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "pendencias.db")
    init_db(path, verbose=False)
    return path


@pytest.fixture
def contrato_id(db_path):
    return ContractRepository(db_path).criar_contrato("Contrato Pendencias")


def _previsto(db_path, contrato_id, codigo, titulo="Titulo", **campos):
    with get_connection(db_path=db_path) as conn:
        conn.execute(
            """
            INSERT INTO documentos_previstos
                (contrato_id, codigo, titulo, tipo, disciplina, trecho, ativo)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                contrato_id,
                codigo,
                titulo,
                campos.get("tipo", "DE"),
                campos.get("disciplina", "F2"),
                campos.get("trecho", "25"),
                campos.get("ativo", 1),
            ),
        )


def _documento(db_path, contrato_id, codigo, titulo="Titulo", **campos):
    return DocumentoRepository(db_path).criar_documento({
        "contrato_id": contrato_id,
        "codigo": codigo,
        "titulo": titulo,
        "tipo": campos.get("tipo", "DE"),
        "disciplina": campos.get("disciplina", "F2"),
        "trecho": campos.get("trecho", "25"),
    })


def _revisao(db_path, documento_id, **campos):
    revisao_id = RevisaoRepository(db_path).criar_revisao({
        "documento_id": documento_id,
        "revisao": campos.get("revisao", 1),
        "versao": campos.get("versao", 1),
        "label_revisao": campos.get("label_revisao", "1"),
        "data_emissao": campos.get("data_emissao"),
        "data_analise": campos.get("data_analise"),
        "situacao": campos.get("situacao"),
        "ultima_revisao": campos.get("ultima_revisao", 1),
    })
    if campos.get("criado_em"):
        with get_connection(db_path=db_path) as conn:
            conn.execute(
                "UPDATE revisoes SET criado_em = ? WHERE id = ?",
                (campos["criado_em"], revisao_id),
            )
    return revisao_id


def _importacao(db_path, contrato_id):
    with get_connection(db_path=db_path) as conn:
        cur = conn.execute(
            "INSERT INTO importacoes (contrato_id, origem) VALUES (?, 'teste')",
            (contrato_id,),
        )
        return int(cur.lastrowid)


def _arquivo(db_path, importacao_id, nome, documento_id=None):
    with get_connection(db_path=db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO arquivos (documento_id, nome_arquivo, importacao_id)
            VALUES (?, ?, ?)
            """,
            (documento_id, nome, importacao_id),
        )
        return int(cur.lastrowid)


def _buscar(db_path, contrato_id, tipo, chave):
    return next(
        (
            p for p in detectar_pendencias(contrato_id, db_path=db_path)
            if p.tipo is tipo and p.chave == str(chave)
        ),
        None,
    )


class TestContratoDoMotor:
    def test_enum_tem_exatamente_onze_categorias(self):
        assert len(TipoPendencia) == 11

    def test_retorna_dataclasses_tipadas(self, db_path, contrato_id):
        _previsto(db_path, contrato_id, "DOC-001")
        resultado = detectar_pendencias(contrato_id, db_path=db_path)
        assert resultado
        assert all(isinstance(item, Pendencia) for item in resultado)

    def test_contrato_vazio_retorna_lista_vazia(self, db_path, contrato_id):
        assert detectar_pendencias(contrato_id, db_path=db_path) == []

    def test_limite_negativo_e_rejeitado(self, db_path, contrato_id):
        with pytest.raises(ValueError):
            detectar_pendencias(contrato_id, db_path=db_path, dias_analise=-1)


class TestOnzeCategorias:
    def test_previsto_sem_inicio(self, db_path, contrato_id):
        _previsto(db_path, contrato_id, "DOC-SEM-INICIO")
        item = _buscar(
            db_path, contrato_id, TipoPendencia.PREVISTO_SEM_INICIO, "DOC-SEM-INICIO"
        )
        assert item is not None
        assert item.codigo == "DOC-SEM-INICIO"

    def test_previsto_estagnado(self, db_path, contrato_id):
        codigo = "DOC-ESTAGNADO"
        _previsto(db_path, contrato_id, codigo)
        documento_id = _documento(db_path, contrato_id, codigo)
        _revisao(
            db_path,
            documento_id,
            situacao="NÃO APROVADO",
            data_emissao="2026-01-01",
            criado_em="2026-01-01 00:00:00",
        )
        item = _buscar(db_path, contrato_id, TipoPendencia.PREVISTO_ESTAGNADO, codigo)
        assert item is not None
        assert item.dias > 60
        assert item.documento_id == documento_id

    def test_previsto_aprovado_nao_fica_estagnado(self, db_path, contrato_id):
        codigo = "DOC-APROVADO"
        _previsto(db_path, contrato_id, codigo)
        documento_id = _documento(db_path, contrato_id, codigo)
        _revisao(
            db_path,
            documento_id,
            situacao="APROVADO",
            data_emissao="2026-01-01",
            criado_em="2026-01-01 00:00:00",
        )
        assert _buscar(
            db_path, contrato_id, TipoPendencia.PREVISTO_ESTAGNADO, codigo
        ) is None

    def test_lista_sem_id(self, db_path, contrato_id):
        codigo = "DOC-EXTRA"
        _documento(db_path, contrato_id, codigo)
        assert _buscar(db_path, contrato_id, TipoPendencia.LISTA_SEM_ID, codigo)

    def test_lista_sem_id_equivale_a_comparacao(self, db_path, contrato_id):
        _documento(db_path, contrato_id, "DOC-EXTRA-1")
        _documento(db_path, contrato_id, "DOC-EXTRA-2")
        engine = {
            p.codigo for p in detectar_pendencias(contrato_id, db_path=db_path)
            if p.tipo is TipoPendencia.LISTA_SEM_ID
        }
        comparacao = set(comparar_id_lista(contrato_id, db_path).extras["codigo"])
        assert engine == comparacao

    def test_previsto_inativo_nao_evitar_lista_sem_id(self, db_path, contrato_id):
        codigo = "DOC-ID-INATIVO"
        _previsto(db_path, contrato_id, codigo, ativo=0)
        _documento(db_path, contrato_id, codigo)
        assert _buscar(db_path, contrato_id, TipoPendencia.LISTA_SEM_ID, codigo)

    def test_arquivo_sem_documento(self, db_path, contrato_id):
        importacao_id = _importacao(db_path, contrato_id)
        arquivo_id = _arquivo(db_path, importacao_id, "arquivo-solto.pdf")
        item = _buscar(
            db_path, contrato_id, TipoPendencia.ARQUIVO_SEM_DOCUMENTO, arquivo_id
        )
        assert item is not None
        assert item.codigo is None
        assert "arquivo-solto.pdf" in item.mensagem

    def test_arquivo_sem_importacao_e_excluido(self, db_path, contrato_id):
        with get_connection(db_path=db_path) as conn:
            cur = conn.execute(
                "INSERT INTO arquivos (nome_arquivo) VALUES ('sem-lote.pdf')"
            )
            arquivo_id = int(cur.lastrowid)
        assert _buscar(
            db_path, contrato_id, TipoPendencia.ARQUIVO_SEM_DOCUMENTO, arquivo_id
        ) is None

    def test_documento_sem_arquivo(self, db_path, contrato_id):
        codigo = "DOC-SEM-ARQUIVO"
        documento_id = _documento(db_path, contrato_id, codigo)
        item = _buscar(
            db_path, contrato_id, TipoPendencia.DOCUMENTO_SEM_ARQUIVO, codigo
        )
        assert item is not None
        assert item.documento_id == documento_id

    def test_codigo_invalido(self, db_path, contrato_id):
        importacao_id = _importacao(db_path, contrato_id)
        with get_connection(db_path=db_path) as conn:
            conn.execute(
                """
                INSERT INTO inconsistencias
                    (importacao_id, documento_codigo, tipo_inconsistencia, descricao)
                VALUES (?, 'CODIGO-RUIM', 'codigo_invalido', 'Formato invalido')
                """,
                (importacao_id,),
            )
        item = _buscar(
            db_path, contrato_id, TipoPendencia.CODIGO_INVALIDO, "CODIGO-RUIM"
        )
        assert item is not None
        assert item.mensagem == "Formato invalido"

    def test_codigo_invalido_resolvido_e_ignorado(self, db_path, contrato_id):
        importacao_id = _importacao(db_path, contrato_id)
        with get_connection(db_path=db_path) as conn:
            conn.execute(
                """
                INSERT INTO inconsistencias
                    (importacao_id, documento_codigo, tipo_inconsistencia, resolvida)
                VALUES (?, 'CODIGO-OK', 'codigo_invalido', 1)
                """,
                (importacao_id,),
            )
        assert _buscar(
            db_path, contrato_id, TipoPendencia.CODIGO_INVALIDO, "CODIGO-OK"
        ) is None

    def test_revisao_sem_data(self, db_path, contrato_id):
        codigo = "DOC-SEM-DATA"
        documento_id = _documento(db_path, contrato_id, codigo)
        _revisao(db_path, documento_id, data_emissao=None)
        assert _buscar(db_path, contrato_id, TipoPendencia.REVISAO_SEM_DATA, codigo)

    def test_documento_sem_titulo(self, db_path, contrato_id):
        codigo = "DOC-SEM-TITULO"
        _documento(db_path, contrato_id, codigo, titulo="   ")
        assert _buscar(
            db_path, contrato_id, TipoPendencia.DOCUMENTO_SEM_TITULO, codigo
        )

    def test_divergencia_titulo(self, db_path, contrato_id):
        codigo = "DOC-DIVERGENTE"
        _previsto(db_path, contrato_id, codigo, titulo="Titulo do ID")
        _documento(db_path, contrato_id, codigo, titulo="Titulo da Lista")
        item = _buscar(
            db_path, contrato_id, TipoPendencia.DIVERGENCIA_TITULO, codigo
        )
        assert item is not None
        assert "Titulo do ID" in item.mensagem
        assert "Titulo da Lista" in item.mensagem

    def test_divergencia_titulo_equivale_a_comparacao(self, db_path, contrato_id):
        _previsto(db_path, contrato_id, "DOC-DIV-1", titulo="ID 1")
        _documento(db_path, contrato_id, "DOC-DIV-1", titulo="Lista 1")
        _previsto(db_path, contrato_id, "DOC-IGUAL", titulo="Mesmo")
        _documento(db_path, contrato_id, "DOC-IGUAL", titulo="Mesmo")
        engine = {
            p.codigo for p in detectar_pendencias(contrato_id, db_path=db_path)
            if p.tipo is TipoPendencia.DIVERGENCIA_TITULO
        }
        comparacao = set(
            comparar_id_lista(contrato_id, db_path).divergencias["codigo"]
        )
        assert engine == comparacao

    def test_titulos_iguais_com_espacos_nao_divergem(self, db_path, contrato_id):
        codigo = "DOC-TITULO-IGUAL"
        _previsto(db_path, contrato_id, codigo, titulo=" Mesmo titulo ")
        _documento(db_path, contrato_id, codigo, titulo="Mesmo titulo")
        assert _buscar(
            db_path, contrato_id, TipoPendencia.DIVERGENCIA_TITULO, codigo
        ) is None

    def test_emitido_sem_analise(self, db_path, contrato_id):
        codigo = "DOC-SEM-ANALISE"
        documento_id = _documento(db_path, contrato_id, codigo)
        _revisao(db_path, documento_id, data_emissao="2026-07-01", data_analise=None)
        assert _buscar(
            db_path, contrato_id, TipoPendencia.EMITIDO_SEM_ANALISE, codigo
        )

    def test_analise_atrasada(self, db_path, contrato_id):
        codigo = "DOC-ATRASADO"
        _previsto(db_path, contrato_id, codigo)
        documento_id = _documento(db_path, contrato_id, codigo)
        data_antiga = (date.today() - timedelta(days=90)).isoformat()
        _revisao(
            db_path,
            documento_id,
            data_emissao=data_antiga,
            situacao="EM ANALISE",
        )
        item = _buscar(db_path, contrato_id, TipoPendencia.ANALISE_ATRASADA, codigo)
        assert item is not None
        assert item.dias >= 89


def test_documento_regular_nao_gera_pendencia(db_path, contrato_id):
    codigo = "DOC-REGULAR"
    _previsto(db_path, contrato_id, codigo, titulo="Projeto regular")
    documento_id = _documento(db_path, contrato_id, codigo, titulo="Projeto regular")
    _revisao(
        db_path,
        documento_id,
        label_revisao="0",
        revisao=0,
        situacao="APROVADO",
        data_emissao="2026-07-01",
        data_analise="2026-07-10",
    )
    importacao_id = _importacao(db_path, contrato_id)
    _arquivo(db_path, importacao_id, "DOC-REGULAR-0-1.pdf", documento_id)

    assert detectar_pendencias(contrato_id, db_path=db_path) == []
