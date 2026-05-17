"""
tests/test_services/test_cadastro_service.py

Testes do CadastroService.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scripts"),
)

from init_db import init_db
from db.connection import get_connection
from core.repositories.contract_repository import ContractRepository
from core.repositories.documento_repository import DocumentoRepository
from core.repositories.revisao_repository import RevisaoRepository
from core.services.cadastro_service import (
    CadastroService,
    ResultadoCadastro,
    ResultadoValidacao,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Inicializa um banco temporario e aponta o cadastro_importer para ele.

    O importer mantem singletons de repositorio criados sem db_path.
    Substituimos por instancias apontando para o tmp_path do teste.
    """
    path = str(tmp_path / "test.db")
    init_db(path, verbose=False)

    from core.importers import cadastro_importer
    monkeypatch.setattr(
        cadastro_importer,
        "_documento_repository",
        DocumentoRepository(path),
    )
    monkeypatch.setattr(
        cadastro_importer,
        "_revisao_repository",
        RevisaoRepository(path),
    )
    return path


@pytest.fixture
def contrato_id(db_path):
    return ContractRepository(db_path).criar_contrato("Contrato Teste", "Cliente X")


@pytest.fixture
def service(db_path):
    return CadastroService(db_path=db_path)


_CODIGO_VALIDO = "DE-15.25.00.00-6A1-1001"
_CODIGO_VALIDO2 = "DE-15.25.00.00-6A1-1002"
_CODIGO_INVALIDO = "XYZ-INVALIDO-123"


def _doc_fields(titulo="Meu Documento", responsavel="Fulano", modalidade="CIVIL"):
    return {
        "titulo": titulo,
        "responsavel": responsavel,
        "modalidade": modalidade,
    }


def _rev_fields(label="0", versao=1, **kwargs):
    base = {
        "label_revisao": label,
        "versao": versao,
        "data_elaboracao": None,
        "data_emissao": None,
        "data_analise": None,
        "situacao": "APROVADO",
        "situacao_real": None,
        "analise_interna": None,
        "data_circular": None,
        "num_circular": None,
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# Validação de código
# ---------------------------------------------------------------------------

class TestValidarCodigo:

    def test_codigo_valido_retorna_resultado_valido(self, service, contrato_id):
        resultado = service.validar_codigo(contrato_id, _CODIGO_VALIDO)

        assert isinstance(resultado, ResultadoValidacao)
        assert resultado.valido is True
        assert resultado.codigo == _CODIGO_VALIDO
        assert resultado.mensagem_erro is None

    def test_codigo_valido_extrai_dados_derivados(self, service, contrato_id):
        resultado = service.validar_codigo(contrato_id, _CODIGO_VALIDO)

        assert resultado.dados_derivados["tipo"] == "DE"
        assert resultado.dados_derivados["disciplina"] == "A1"
        assert resultado.dados_derivados["fase"] == "6"
        assert resultado.dados_derivados["trecho"] == "25"

    def test_codigo_invalido_retorna_resultado_invalido(self, service, contrato_id):
        resultado = service.validar_codigo(contrato_id, _CODIGO_INVALIDO)

        assert resultado.valido is False
        assert resultado.mensagem_erro is not None
        assert resultado.dados_derivados == {}

    def test_documento_novo_sem_existente_nem_revisoes(self, service, contrato_id):
        resultado = service.validar_codigo(contrato_id, _CODIGO_VALIDO)

        assert resultado.documento_existente is None
        assert resultado.revisoes_existentes == []

    def test_documento_existente_retorna_doc_e_revisoes(self, service, contrato_id):
        service.cadastrar_documento_manual(
            contrato_id, _CODIGO_VALIDO, _doc_fields(), _rev_fields()
        )

        resultado = service.validar_codigo(contrato_id, _CODIGO_VALIDO)

        assert resultado.valido is True
        assert resultado.documento_existente is not None
        assert resultado.documento_existente["codigo"] == _CODIGO_VALIDO
        assert len(resultado.revisoes_existentes) == 1


# ---------------------------------------------------------------------------
# Normalização e preparação de payload
# ---------------------------------------------------------------------------

class TestNormalizacaoPayload:

    def test_normalizar_strip_em_strings(self, service):
        doc_norm, rev_norm = service.normalizar_payload_formulario(
            {"titulo": "  Titulo  ", "responsavel": "  Ana  ", "modalidade": "CIVIL"},
            _rev_fields(label="  1  "),
        )

        assert doc_norm["titulo"] == "Titulo"
        assert doc_norm["responsavel"] == "Ana"
        assert rev_norm["label_revisao"] == "1"

    def test_normalizar_strings_vazias_viram_none(self, service):
        doc_norm, _ = service.normalizar_payload_formulario(
            {"titulo": "", "responsavel": "   ", "modalidade": ""},
            _rev_fields(),
        )

        assert doc_norm["titulo"] is None
        assert doc_norm["responsavel"] is None
        assert doc_norm["modalidade"] is None

    def test_normalizar_versao_default_um(self, service):
        _, rev_norm = service.normalizar_payload_formulario(
            _doc_fields(),
            {"label_revisao": "0", "versao": None},
        )

        assert rev_norm["versao"] == 1


class TestValidacaoCamposObrigatorios:

    def test_sem_titulo_retorna_erro(self, service):
        erros = service.validar_campos_obrigatorios(
            {"titulo": ""}, {"label_revisao": "0"}
        )
        assert any("Descrição" in e for e in erros)

    def test_sem_label_revisao_retorna_erro(self, service):
        erros = service.validar_campos_obrigatorios(
            {"titulo": "Doc"}, {"label_revisao": ""}
        )
        assert any("Revisão" in e for e in erros)

    def test_campos_validos_sem_erros(self, service):
        erros = service.validar_campos_obrigatorios(
            {"titulo": "Doc"}, {"label_revisao": "0"}
        )
        assert erros == []


class TestPreparacaoPayload:

    def test_preparar_documento_extrai_disciplina_e_fase_do_codigo(
        self, service, contrato_id
    ):
        payload = service.preparar_documento_para_cadastro(
            contrato_id, _CODIGO_VALIDO, _doc_fields()
        )

        assert payload["contrato_id"] == contrato_id
        assert payload["codigo"] == _CODIGO_VALIDO
        assert payload["disciplina"] == "A1"
        assert payload["fase"] == "6"
        assert payload["tipo"] == "DE"
        assert payload["origem"] == "cadastro_manual"

    def test_preparar_revisao_converte_label_numerico_em_int(self, service):
        documento = {"id": 42}
        payload = service.preparar_revisao_para_cadastro(
            documento, _rev_fields(label="3", versao=2)
        )

        assert payload["documento_id"] == 42
        assert payload["revisao"] == 3
        assert payload["versao"] == 2
        assert payload["label_revisao"] == "3"

    def test_preparar_revisao_label_alfanumerico_revisao_none(self, service):
        documento = {"id": 1}
        payload = service.preparar_revisao_para_cadastro(
            documento, _rev_fields(label="A1")
        )

        assert payload["revisao"] is None
        assert payload["label_revisao"] == "A1"


# ---------------------------------------------------------------------------
# Cadastro completo
# ---------------------------------------------------------------------------

class TestCadastroDocumentoManual:

    def test_cadastro_novo_retorna_sucesso(self, service, contrato_id):
        resultado = service.cadastrar_documento_manual(
            contrato_id, _CODIGO_VALIDO, _doc_fields(), _rev_fields()
        )

        assert isinstance(resultado, ResultadoCadastro)
        assert resultado.sucesso is True
        assert resultado.codigo == _CODIGO_VALIDO
        assert resultado.documento_id is not None
        assert resultado.revisao_id is not None
        assert resultado.documento_existente is False
        assert resultado.erros == []
        assert "sucesso" in resultado.mensagem.lower()

    def test_cadastro_sem_titulo_retorna_erro_estruturado(self, service, contrato_id):
        resultado = service.cadastrar_documento_manual(
            contrato_id, _CODIGO_VALIDO,
            _doc_fields(titulo=""),
            _rev_fields(),
        )

        assert resultado.sucesso is False
        assert resultado.erros
        assert any("Descrição" in e for e in resultado.erros)
        assert resultado.documento_id is None

    def test_cadastro_sem_label_revisao_retorna_erro_estruturado(
        self, service, contrato_id
    ):
        resultado = service.cadastrar_documento_manual(
            contrato_id, _CODIGO_VALIDO, _doc_fields(), _rev_fields(label="")
        )

        assert resultado.sucesso is False
        assert any("Revisão" in e for e in resultado.erros)

    def test_cadastro_em_documento_existente_marca_flag(self, service, contrato_id):
        service.cadastrar_documento_manual(
            contrato_id, _CODIGO_VALIDO, _doc_fields(), _rev_fields(label="0")
        )

        resultado = service.cadastrar_documento_manual(
            contrato_id, _CODIGO_VALIDO, _doc_fields(), _rev_fields(label="1")
        )

        assert resultado.sucesso is True
        assert resultado.documento_existente is True

    def test_cadastro_revisao_duplicada_gera_alerta(self, service, contrato_id):
        service.cadastrar_documento_manual(
            contrato_id, _CODIGO_VALIDO, _doc_fields(), _rev_fields(label="0")
        )

        resultado = service.cadastrar_documento_manual(
            contrato_id, _CODIGO_VALIDO, _doc_fields(), _rev_fields(label="0")
        )

        assert resultado.sucesso is False
        assert resultado.alertas
        assert "já existe" in resultado.mensagem.lower()

    def test_cadastro_persiste_no_banco(self, service, contrato_id, db_path):
        service.cadastrar_documento_manual(
            contrato_id, _CODIGO_VALIDO, _doc_fields(titulo="Persistido"), _rev_fields()
        )

        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT titulo, disciplina, fase FROM documentos WHERE codigo = ?",
                (_CODIGO_VALIDO,),
            ).fetchone()

        assert row["titulo"] == "Persistido"
        assert row["disciplina"] == "A1"
        assert row["fase"] == "6"


# ---------------------------------------------------------------------------
# Consultas auxiliares
# ---------------------------------------------------------------------------

class TestConsultasAuxiliares:

    def test_buscar_documento_existente_retorna_none(self, service, contrato_id):
        assert service.buscar_documento_existente(contrato_id, _CODIGO_VALIDO) is None

    def test_buscar_documento_existente_retorna_dict(self, service, contrato_id):
        service.cadastrar_documento_manual(
            contrato_id, _CODIGO_VALIDO, _doc_fields(), _rev_fields()
        )

        doc = service.buscar_documento_existente(contrato_id, _CODIGO_VALIDO)

        assert doc is not None
        assert doc["codigo"] == _CODIGO_VALIDO

    def test_listar_revisoes_existentes_vazio(self, service, contrato_id):
        service.cadastrar_documento_manual(
            contrato_id, _CODIGO_VALIDO2, _doc_fields(), _rev_fields()
        )
        doc = service.buscar_documento_existente(contrato_id, _CODIGO_VALIDO2)

        revisoes = service.listar_revisoes_existentes(doc["id"])

        assert len(revisoes) == 1


# ---------------------------------------------------------------------------
# Independência de Streamlit
# ---------------------------------------------------------------------------

class TestIndependenciaStreamlit:

    def test_modulo_nao_importa_streamlit(self):
        import core.services.cadastro_service as mod
        import inspect

        source = inspect.getsource(mod)
        # Filtra a docstring inicial para evitar falso-positivo em texto descritivo.
        codigo = "\n".join(
            linha for linha in source.splitlines()
            if not linha.strip().startswith(('"', "#"))
        )
        assert "import streamlit" not in codigo
        assert "from streamlit" not in codigo
        # Nao deve referenciar session_state via o alias usual `st.`
        assert "st.session_state" not in codigo
        # E streamlit nao deve ser carregado como atributo do modulo
        assert not hasattr(mod, "st")

    def test_servico_funciona_sem_session_state(self, service, contrato_id):
        resultado = service.cadastrar_documento_manual(
            contrato_id, _CODIGO_VALIDO, _doc_fields(), _rev_fields()
        )
        assert resultado.sucesso is True
