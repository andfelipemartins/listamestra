"""
tests/test_services/test_dashboard_service.py

Testes do DashboardService.
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
from core.engine.status import STATUS_ORDEM
from core.services.dashboard_service import DashboardService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path, verbose=False)
    with get_connection(db_path) as conn:
        conn.execute("INSERT INTO contratos (nome) VALUES ('Contrato Teste')")
        cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return db_path, cid


@pytest.fixture
def service(db):
    db_path, _ = db
    return DashboardService(db_path=db_path)


# ---------------------------------------------------------------------------
# Helpers de inserção (mesmo padrão de test_status.py)
# ---------------------------------------------------------------------------

def _inserir_previsto(conn, contrato_id, codigo, trecho="25"):
    conn.execute(
        "INSERT INTO documentos_previstos (contrato_id, codigo, trecho, tipo) VALUES (?, ?, ?, ?)",
        (contrato_id, codigo, trecho, codigo.split("-")[0]),
    )


def _inserir_doc_revisao(
    conn, contrato_id, codigo, label="1",
    situacao=None, data_emissao=None,
):
    conn.execute(
        "INSERT OR IGNORE INTO documentos (contrato_id, codigo, tipo) VALUES (?, ?, ?)",
        (contrato_id, codigo, codigo.split("-")[0]),
    )
    doc_id = conn.execute(
        "SELECT id FROM documentos WHERE contrato_id=? AND codigo=?",
        (contrato_id, codigo),
    ).fetchone()[0]
    try:
        revisao_int = int(label)
    except (TypeError, ValueError):
        revisao_int = 1
    conn.execute(
        """INSERT INTO revisoes
           (documento_id, revisao, versao, label_revisao, situacao, data_emissao, ultima_revisao)
           VALUES (?, ?, 1, ?, ?, ?, 1)""",
        (doc_id, revisao_int, label, situacao, data_emissao),
    )


# ---------------------------------------------------------------------------
# Dashboard sem dados
# ---------------------------------------------------------------------------

class TestDashboardVazio:

    def test_progresso_retorna_dataframe_vazio(self, service, db):
        _, cid = db
        df = service.carregar_progresso(cid)
        assert df.empty

    def test_metricas_zeradas(self, service, db):
        _, cid = db
        m = service.carregar_metricas_principais(cid)
        assert m["total_previstos"] == 0
        assert m["ja_aprovados"] == 0
        assert m["percentual_avanco"] == 0.0
        for s in STATUS_ORDEM:
            assert m["contagem_por_status"][s] == 0

    def test_distribuicao_vazia(self, service, db):
        _, cid = db
        dist = service.carregar_distribuicao_status(cid)
        assert dist["geral"].empty
        assert dist["por_trecho"].empty

    def test_progresso_por_trecho_vazio(self, service, db):
        _, cid = db
        assert service.carregar_progresso_por_trecho(cid) == []

    def test_progresso_por_disciplina_vazio(self, service, db):
        _, cid = db
        assert service.carregar_progresso_por_disciplina(cid) == []

    def test_resumo_completo_consistente(self, service, db):
        _, cid = db
        resumo = service.carregar_resumo_dashboard(cid)
        assert resumo["progresso_df"].empty
        assert resumo["metricas_principais"]["total_previstos"] == 0
        assert resumo["progresso_por_trecho"] == []
        assert resumo["alertas"] == []


# ---------------------------------------------------------------------------
# Dashboard com previstos sem revisão
# ---------------------------------------------------------------------------

class TestApenasPrevistos:

    def test_metricas_contam_em_elaboracao(self, service, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001")
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1002")
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1003")

        m = service.carregar_metricas_principais(cid)
        assert m["total_previstos"] == 3
        assert m["total_em_elaboracao"] == 3
        assert m["ja_aprovados"] == 0
        assert m["percentual_avanco"] == 0.0

    def test_distribuicao_geral_concentrada_em_elaboracao(self, service, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001")
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1002")

        dist = service.carregar_distribuicao_status(cid)
        geral = dist["geral"]
        em_elab = geral[geral["status_atual"] == "Em Elaboração"].iloc[0]["qtd"]
        assert em_elab == 2


# ---------------------------------------------------------------------------
# Dashboard com mix de revisões
# ---------------------------------------------------------------------------

class TestComRevisoes:

    @pytest.fixture
    def cenario(self, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            # 1 Aprovado em trecho 25
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001", trecho="25")
            _inserir_doc_revisao(
                conn, cid, "DE-15.25.00.00-6A1-1001",
                label="0", situacao="APROVADO", data_emissao="2024-10-07",
            )
            # 1 Em Análise em trecho 25
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1002", trecho="25")
            _inserir_doc_revisao(
                conn, cid, "DE-15.25.00.00-6A1-1002",
                data_emissao="2024-11-01",
            )
            # 1 Em Revisão em trecho 23
            _inserir_previsto(conn, cid, "DE-15.23.17.84-6B3-1001", trecho="23")
            _inserir_doc_revisao(
                conn, cid, "DE-15.23.17.84-6B3-1001",
                situacao="NÃO APROVADO", data_emissao="2024-09-01",
            )
            # 1 Em Elaboração em trecho 23 (sem revisão)
            _inserir_previsto(conn, cid, "DE-15.23.17.84-6B3-1002", trecho="23")
        return db_path, cid

    def test_total_previstos(self, service, cenario):
        _, cid = cenario
        m = service.carregar_metricas_principais(cid)
        assert m["total_previstos"] == 4

    def test_contagem_por_status(self, service, cenario):
        _, cid = cenario
        m = service.carregar_metricas_principais(cid)
        assert m["total_aprovados"] == 1
        assert m["total_em_analise"] == 1
        assert m["total_em_revisao"] == 1
        assert m["total_em_elaboracao"] == 1

    def test_ja_aprovados_conta_label_zero(self, service, cenario):
        _, cid = cenario
        m = service.carregar_metricas_principais(cid)
        assert m["ja_aprovados"] == 1
        assert m["percentual_avanco"] == pytest.approx(25.0)

    def test_percentuais_somam_cem(self, service, cenario):
        _, cid = cenario
        m = service.carregar_metricas_principais(cid)
        soma = sum(m["percentual_por_status"].values())
        assert soma == pytest.approx(100.0)

    def test_distribuicao_geral_tem_todos_status(self, service, cenario):
        _, cid = cenario
        dist = service.carregar_distribuicao_status(cid)
        statuses = set(dist["geral"]["status_atual"].tolist())
        assert statuses == set(STATUS_ORDEM)

    def test_distribuicao_por_trecho_inclui_todas_combinacoes(self, service, cenario):
        _, cid = cenario
        dist = service.carregar_distribuicao_status(cid)
        por_trecho = dist["por_trecho"]
        trechos_presentes = set(por_trecho["nome_trecho"].unique())
        # 2 trechos × 4 status = 8 linhas
        assert len(por_trecho) == len(trechos_presentes) * len(STATUS_ORDEM)

    def test_progresso_por_trecho_estrutura(self, service, cenario):
        _, cid = cenario
        lista = service.carregar_progresso_por_trecho(cid)
        assert len(lista) == 2
        item = lista[0]
        assert {"trecho", "nome_trecho", "total", "ja_aprovados", "percentual",
                "contagem_status"} <= set(item.keys())

    def test_progresso_por_trecho_25(self, service, cenario):
        _, cid = cenario
        lista = service.carregar_progresso_por_trecho(cid)
        t25 = next(x for x in lista if x["trecho"] == "25")
        assert t25["total"] == 2
        assert t25["ja_aprovados"] == 1
        assert t25["percentual"] == pytest.approx(50.0)
        assert t25["nome_trecho"] == "Ragueb Chohfi"

    def test_progresso_por_disciplina(self, service, cenario):
        _, cid = cenario
        lista = service.carregar_progresso_por_disciplina(cid)
        disciplinas = {item["disciplina"] for item in lista}
        # Códigos A1 (3 docs no trecho 25/23 e o outro 6A1) e B3 (2 docs no trecho 23)
        assert "A1" in disciplinas
        assert "B3" in disciplinas


# ---------------------------------------------------------------------------
# Resumo consolidado
# ---------------------------------------------------------------------------

class TestResumoDashboard:

    def test_resumo_contem_todas_as_chaves(self, service, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001")

        resumo = service.carregar_resumo_dashboard(cid)
        assert {
            "progresso_df",
            "metricas_principais",
            "distribuicao_status",
            "progresso_por_trecho",
            "progresso_por_disciplina",
            "alertas",
            "resumo_pendencias",
            "ultima_importacao",
            "ultimas_importacoes",
        } <= set(resumo.keys())

    def test_resumo_pendencias_estrutura(self, service, db):
        _, cid = db
        resumo = service.carregar_resumo_dashboard(cid)
        pend = resumo["resumo_pendencias"]
        assert {"total", "analise_prolongada", "sem_inicio", "alertas"} <= set(pend.keys())
        assert pend["total"] == 0

    def test_resumo_pendencias_sem_inicio(self, service, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001")
            conn.execute(
                "INSERT INTO documentos (contrato_id, codigo, tipo) VALUES (?, ?, 'DE')",
                (cid, "DE-15.25.00.00-6A1-1001"),
            )

        pend = service.carregar_pendencias_resumidas(cid)
        assert pend["sem_inicio"] == 1


# ---------------------------------------------------------------------------
# Independência de Streamlit/Plotly
# ---------------------------------------------------------------------------

class TestIndependenciaUI:

    def test_modulo_nao_importa_streamlit(self):
        import core.services.dashboard_service as mod
        import inspect

        source = inspect.getsource(mod)
        codigo = "\n".join(
            linha for linha in source.splitlines()
            if not linha.strip().startswith(('"', "#"))
        )
        assert "import streamlit" not in codigo
        assert "from streamlit" not in codigo
        assert not hasattr(mod, "st")

    def test_modulo_nao_importa_plotly(self):
        import core.services.dashboard_service as mod
        import inspect

        source = inspect.getsource(mod)
        codigo = "\n".join(
            linha for linha in source.splitlines()
            if not linha.strip().startswith(('"', "#"))
        )
        assert "import plotly" not in codigo
        assert "from plotly" not in codigo
        assert not hasattr(mod, "px")
        assert not hasattr(mod, "go")
