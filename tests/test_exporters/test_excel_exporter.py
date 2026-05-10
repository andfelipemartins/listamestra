"""
tests/test_exporters/test_excel_exporter.py

Testes dos exportadores Excel (Marco 10).
Verificam estrutura (abas, colunas) e conteúdo dos arquivos gerados.
"""

import io
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from core.exporters.excel_exporter import (
    exportar_lista_mestra,
    exportar_alertas,
    exportar_historico_revisoes,
    exportar_comparacao,
)
from core.engine.comparacao import ResultadoComparacao


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ler_excel(data: bytes) -> dict[str, pd.DataFrame]:
    """Lê bytes Excel e retorna dict aba → DataFrame."""
    return pd.read_excel(io.BytesIO(data), sheet_name=None)


# ---------------------------------------------------------------------------
# exportar_lista_mestra
# ---------------------------------------------------------------------------

class TestExportarListaMestra:

    def _df(self, rows: list[dict]) -> pd.DataFrame:
        return pd.DataFrame(rows)

    def test_retorna_bytes(self):
        df = self._df([{"codigo": "DE-15.25.00.00-6A1-1001", "titulo": "T", "tipo": "DE",
                         "nome_trecho": "Ragueb", "status_atual":"Aprovado",
                         "situacao": "APROVADO", "data_emissao": "2024-01-10"}])
        result = exportar_lista_mestra(df, "Contrato Teste")
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_aba_lista_mestra_existe(self):
        df = self._df([{"codigo": "DE-15.25.00.00-6A1-1001", "titulo": "T", "tipo": "DE",
                         "nome_trecho": "Ragueb", "status_atual":"Aprovado",
                         "situacao": "APROVADO", "data_emissao": "2024-01-10"}])
        abas = _ler_excel(exportar_lista_mestra(df, "C"))
        assert "Lista Mestra" in abas

    def test_colunas_presentes(self):
        df = self._df([{"codigo": "DE-15.25.00.00-6A1-1001", "titulo": "T", "tipo": "DE",
                         "nome_trecho": "Ragueb", "status_atual":"Aprovado",
                         "situacao": "APROVADO", "data_emissao": "2024-01-10"}])
        sheet = _ler_excel(exportar_lista_mestra(df, "C"))["Lista Mestra"]
        for col in ["Código", "Título", "Status Atual", "Tipo", "Trecho"]:
            assert col in sheet.columns

    def test_linhas_exportadas(self):
        df = self._df([
            {"codigo": "DE-15.25.00.00-6A1-1001", "titulo": "A", "tipo": "DE",
             "nome_trecho": "Ragueb", "status_atual":"Aprovado", "situacao": "APROVADO", "data_emissao": "2024-01-10"},
            {"codigo": "DE-15.25.00.00-6A1-1002", "titulo": "B", "tipo": "DE",
             "nome_trecho": "Ragueb", "status_atual":"Em Elaboração", "situacao": None, "data_emissao": None},
        ])
        sheet = _ler_excel(exportar_lista_mestra(df, "C"))["Lista Mestra"]
        assert len(sheet) == 2

    def test_dataframe_vazio_gera_arquivo_valido(self):
        df = pd.DataFrame(columns=["codigo", "titulo", "tipo", "nome_trecho", "status", "situacao", "data_emissao"])
        result = exportar_lista_mestra(df, "C")
        abas = _ler_excel(result)
        assert "Lista Mestra" in abas


# ---------------------------------------------------------------------------
# exportar_alertas
# ---------------------------------------------------------------------------

class TestExportarAlertas:

    def _alerta_prolongado(self, codigo="DE-15.25.00.00-6A1-1001"):
        return {
            "tipo": "analise_prolongada",
            "codigo": codigo,
            "titulo": "Título Teste",
            "dias": 45,
            "data_referencia": "2024-01-10",
            "mensagem": "Em Análise há 45 dias",
        }

    def _alerta_sem_inicio(self, codigo="DE-15.25.00.00-6A1-1002"):
        return {
            "tipo": "sem_inicio",
            "codigo": codigo,
            "titulo": "Título Teste",
            "dias": None,
            "data_referencia": None,
            "mensagem": "Previsto no ID mas sem revisão lançada",
        }

    def test_retorna_bytes(self):
        result = exportar_alertas([self._alerta_prolongado()], "C")
        assert isinstance(result, bytes)

    def test_duas_abas_presentes(self):
        alertas = [self._alerta_prolongado(), self._alerta_sem_inicio()]
        abas = _ler_excel(exportar_alertas(alertas, "C"))
        assert "Análise Prolongada" in abas
        assert "Sem Revisão" in abas

    def test_aba_prolongada_com_dados(self):
        alertas = [self._alerta_prolongado("DE-15.25.00.00-6A1-1001"),
                   self._alerta_prolongado("DE-15.25.00.00-6A1-1002")]
        sheet = _ler_excel(exportar_alertas(alertas, "C"))["Análise Prolongada"]
        assert len(sheet) == 2

    def test_aba_sem_revisao_com_dados(self):
        alertas = [self._alerta_sem_inicio()]
        sheet = _ler_excel(exportar_alertas(alertas, "C"))["Sem Revisão"]
        assert len(sheet) == 1
        assert "Código" in sheet.columns

    def test_lista_vazia_gera_abas_vazias(self):
        abas = _ler_excel(exportar_alertas([], "C"))
        assert "Análise Prolongada" in abas
        assert "Sem Revisão" in abas

    def test_apenas_prolongados_sem_revisao_vazia(self):
        alertas = [self._alerta_prolongado()]
        abas = _ler_excel(exportar_alertas(alertas, "C"))
        assert len(abas["Análise Prolongada"]) == 1
        assert len(abas["Sem Revisão"]) == 0

    def test_apenas_sem_inicio_prolongada_vazia(self):
        alertas = [self._alerta_sem_inicio()]
        abas = _ler_excel(exportar_alertas(alertas, "C"))
        assert len(abas["Análise Prolongada"]) == 0
        assert len(abas["Sem Revisão"]) == 1


# ---------------------------------------------------------------------------
# exportar_historico_revisoes
# ---------------------------------------------------------------------------

class TestExportarHistoricoRevisoes:

    def _revisao(self, emissao="EMISSÃO INICIAL", situacao="APROVADO"):
        return {
            "id": 1,
            "revisao": 0,
            "versao": 1,
            "label_revisao": "Rev0",
            "emissao_inicial": emissao,
            "data_elaboracao": "2024-01-01",
            "data_emissao": "2024-01-10",
            "data_analise": None,
            "dias_elaboracao": 9,
            "dias_analise": None,
            "situacao_real": situacao,
            "situacao": situacao,
            "retorno": None,
            "emissao_circular": "CIR-001",
            "analise_circular": None,
            "data_circular": None,
            "ultima_revisao": 1,
            "origem": "importacao_lista",
            "criado_em": "2024-01-10T10:00:00",
        }

    def _doc(self):
        return {"id": 1, "codigo": "DE-15.25.00.00-6A1-1001", "titulo": "Título Doc"}

    def test_retorna_bytes(self):
        result = exportar_historico_revisoes([self._revisao()], self._doc(), "C")
        assert isinstance(result, bytes)

    def test_aba_revisoes_existe(self):
        abas = _ler_excel(exportar_historico_revisoes([self._revisao()], self._doc(), "C"))
        assert "Revisões" in abas

    def test_colunas_presentes(self):
        sheet = _ler_excel(
            exportar_historico_revisoes([self._revisao()], self._doc(), "C")
        )["Revisões"]
        for col in ["Emissão", "Rev.", "Data Emissão", "Situação"]:
            assert col in sheet.columns

    def test_multiplas_revisoes(self):
        revisoes = [
            self._revisao("EMISSÃO INICIAL", "NÃO APROVADO"),
            self._revisao("REVISÃO FINAL", "APROVADO"),
        ]
        sheet = _ler_excel(
            exportar_historico_revisoes(revisoes, self._doc(), "C")
        )["Revisões"]
        assert len(sheet) == 2

    def test_sem_revisoes_gera_arquivo_valido(self):
        abas = _ler_excel(exportar_historico_revisoes([], self._doc(), "C"))
        assert "Revisões" in abas


# ---------------------------------------------------------------------------
# exportar_comparacao
# ---------------------------------------------------------------------------

class TestExportarComparacao:

    def _resultado(
        self,
        ausentes=None, extras=None, divergencias=None
    ) -> ResultadoComparacao:
        return ResultadoComparacao(
            ausentes=pd.DataFrame(ausentes or []),
            extras=pd.DataFrame(extras or []),
            divergencias=pd.DataFrame(divergencias or []),
            encontrados=pd.DataFrame(),
        )

    def test_retorna_bytes(self):
        result = exportar_comparacao(self._resultado(), "C")
        assert isinstance(result, bytes)

    def test_tres_abas_presentes(self):
        abas = _ler_excel(exportar_comparacao(self._resultado(), "C"))
        assert "Ausentes" in abas
        assert "Extras" in abas
        assert "Divergências" in abas

    def test_ausentes_com_dados(self):
        resultado = self._resultado(
            ausentes=[
                {"codigo": "DE-15.25.00.00-6A1-1001", "titulo": "T", "tipo": "DE", "nome_trecho": "Ragueb"},
                {"codigo": "DE-15.25.00.00-6A1-1002", "titulo": "T", "tipo": "DE", "nome_trecho": "Ragueb"},
            ]
        )
        sheet = _ler_excel(exportar_comparacao(resultado, "C"))["Ausentes"]
        assert len(sheet) == 2
        assert "Código" in sheet.columns

    def test_extras_com_dados(self):
        resultado = self._resultado(
            extras=[{"codigo": "DE-15.25.00.00-6A1-9999", "titulo": "Extra", "tipo": "DE", "nome_trecho": "—"}]
        )
        sheet = _ler_excel(exportar_comparacao(resultado, "C"))["Extras"]
        assert len(sheet) == 1

    def test_divergencias_com_dados(self):
        resultado = self._resultado(
            divergencias=[{
                "codigo": "DE-15.25.00.00-6A1-1001",
                "titulo_id": "Título A",
                "titulo_lista": "Título B",
                "nome_trecho": "Ragueb",
            }]
        )
        sheet = _ler_excel(exportar_comparacao(resultado, "C"))["Divergências"]
        assert len(sheet) == 1
        assert "Título (ID)" in sheet.columns
        assert "Título (Lista)" in sheet.columns

    def test_resultado_vazio_gera_abas_vazias(self):
        abas = _ler_excel(exportar_comparacao(self._resultado(), "C"))
        for aba in ["Ausentes", "Extras", "Divergências"]:
            assert len(abas[aba]) == 0
