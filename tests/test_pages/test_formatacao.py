"""
tests/test_pages/test_formatacao.py

Testes dos helpers de formatação de exibição (core/formatacao.py).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from core.formatacao import (
    fmt_inteiro, fmt_data, disciplina_do_codigo,
    normalizar_busca, filtrar_documentos,
)


# ---------------------------------------------------------------------------
# fmt_inteiro
# ---------------------------------------------------------------------------

class TestFmtInteiro:

    def test_float_inteiro_remove_decimal(self):
        assert fmt_inteiro(1.0) == "1"

    def test_float_grande_remove_decimal(self):
        assert fmt_inteiro(12.0) == "12"

    def test_string_float_remove_decimal(self):
        assert fmt_inteiro("1.0") == "1"

    def test_inteiro_puro_retorna_string(self):
        assert fmt_inteiro(1) == "1"

    def test_none_retorna_travessao(self):
        assert fmt_inteiro(None) == "—"

    def test_nan_string_retorna_travessao(self):
        assert fmt_inteiro("nan") == "—"

    def test_string_vazia_retorna_travessao(self):
        assert fmt_inteiro("") == "—"

    def test_float_fracionario_preservado(self):
        assert fmt_inteiro(1.5) == "1.5"

    def test_string_texto_retorna_inalterada(self):
        assert fmt_inteiro("EXECUTIVO") == "EXECUTIVO"

    @pytest.mark.parametrize("entrada,esperado", [
        (0,      "0"),
        (0.0,    "0"),
        ("0.0",  "0"),
        (2,      "2"),
        (2.0,    "2"),
        ("2.0",  "2"),
        (10.0,   "10"),
        ("10.0", "10"),
    ])
    def test_matriz_fmt_inteiro(self, entrada, esperado):
        assert fmt_inteiro(entrada) == esperado


# ---------------------------------------------------------------------------
# fmt_data
# ---------------------------------------------------------------------------

class TestFmtData:

    def test_remove_hora_zerada(self):
        assert fmt_data("2025-06-09 00:00:00") == "2025-06-09"

    def test_data_simples_preservada(self):
        assert fmt_data("2025-06-09") == "2025-06-09"

    def test_none_retorna_travessao(self):
        assert fmt_data(None) == "—"

    def test_string_vazia_retorna_travessao(self):
        assert fmt_data("") == "—"

    def test_nan_string_retorna_travessao(self):
        assert fmt_data("nan") == "—"

    def test_hora_significativa_preservada(self):
        assert fmt_data("2025-06-09 14:30:00") == "2025-06-09 14:30:00"

    def test_data_sem_hora_nao_altera(self):
        assert fmt_data("2024-01-15") == "2024-01-15"

    @pytest.mark.parametrize("entrada,esperado", [
        ("2024-10-07 00:00:00", "2024-10-07"),
        ("2024-10-07",          "2024-10-07"),
        ("2025-01-01 00:00:00", "2025-01-01"),
        (None,                  "—"),
        ("",                    "—"),
    ])
    def test_matriz_fmt_data(self, entrada, esperado):
        assert fmt_data(entrada) == esperado


# ---------------------------------------------------------------------------
# disciplina_do_codigo
# ---------------------------------------------------------------------------

class TestDisciplinaDocodigo:

    def test_b3_do_codigo_exemplo(self):
        assert disciplina_do_codigo("DE-15.23.17.84-6B3-1004") == "B3"

    def test_a1_do_codigo(self):
        assert disciplina_do_codigo("DE-15.25.00.00-6A1-1001") == "A1"

    def test_f5_do_codigo(self):
        assert disciplina_do_codigo("DE-15.25.00.00-6F5-1001") == "F5"

    def test_codigo_invalido_retorna_vazio(self):
        assert disciplina_do_codigo("INVALIDO") == ""

    def test_string_vazia_retorna_vazio(self):
        assert disciplina_do_codigo("") == ""

    @pytest.mark.parametrize("codigo,esperado", [
        ("DE-15.23.17.84-6B3-1004", "B3"),
        ("DE-15.25.00.00-6A1-1001", "A1"),
        ("MC-15.25.00.00-6C1-1001", "C1"),
        ("RT-15.19.02.00-6C1-1001", "C1"),
    ])
    def test_matriz_disciplina_do_codigo(self, codigo, esperado):
        assert disciplina_do_codigo(codigo) == esperado


# ---------------------------------------------------------------------------
# normalizar_busca
# ---------------------------------------------------------------------------

class TestNormalizarBusca:

    def test_converte_maiusculas(self):
        assert normalizar_busca("DESENHO") == "desenho"

    def test_remove_acento_agudo(self):
        assert normalizar_busca("ação") == "acao"

    def test_remove_acento_circunflexo(self):
        assert normalizar_busca("câmara") == "camara"

    def test_remove_acento_til(self):
        assert normalizar_busca("ORATÓRIO") == "oratorio"

    def test_string_limpa_inalterada(self):
        assert normalizar_busca("de-15") == "de-15"

    def test_numero_inalterado(self):
        assert normalizar_busca("1001") == "1001"

    def test_sao_mateus(self):
        assert normalizar_busca("São Mateus") == "sao mateus"

    @pytest.mark.parametrize("entrada,esperado", [
        ("ORATÓRIO",    "oratorio"),
        ("São Mateus",  "sao mateus"),
        ("Elaboração",  "elaboracao"),
        ("6B3",         "6b3"),
        ("Análise",     "analise"),
    ])
    def test_matriz_normalizar(self, entrada, esperado):
        assert normalizar_busca(entrada) == esperado


# ---------------------------------------------------------------------------
# filtrar_documentos
# ---------------------------------------------------------------------------

class TestFiltrarDocumentos:

    def _docs(self):
        return [
            {
                "id": 1, "codigo": "DE-15.23.17.84-6B3-1004",
                "titulo": "LEVANTAMENTO TOPOGRÁFICO", "tipo": "DE",
                "trecho": "23", "nome_trecho": "São Mateus",
                "modalidade": "", "disciplina_display": "B3",
                "disciplina_desc": "ARQUITETURA - ACABAMENTO",
            },
            {
                "id": 2, "codigo": "DE-15.25.00.00-6A1-1001",
                "titulo": "FUNDAÇÕES", "tipo": "DE",
                "trecho": "25", "nome_trecho": "Ragueb Chohfi",
                "modalidade": "", "disciplina_display": "A1",
                "disciplina_desc": "MÉTODO CONSTRUTIVO E SEQUÊNCIA DE EXECUÇÃO",
            },
            {
                "id": 3, "codigo": "MC-15.19.02.00-6C1-1001",
                "titulo": "RELATÓRIO TÉCNICO", "tipo": "MC",
                "trecho": "19", "nome_trecho": "Oratório",
                "modalidade": "", "disciplina_display": "",
                "disciplina_desc": "",
            },
            # doc 4: disciplina vazia no banco, mas código contém 6B3
            # Simula o que _listar_documentos_enriquecidos produz via fallback do parser
            {
                "id": 4, "codigo": "DE-15.23.17.84-6B3-2001",
                "titulo": "PLANTA DE SITUAÇÃO", "tipo": "DE",
                "trecho": "23", "nome_trecho": "São Mateus",
                "modalidade": "", "disciplina_display": "B3",
                "disciplina_desc": "ARQUITETURA - ACABAMENTO",
            },
        ]

    def test_busca_vazia_retorna_todos(self):
        docs = self._docs()
        assert filtrar_documentos(docs, "") == docs

    def test_busca_espaco_retorna_todos(self):
        docs = self._docs()
        assert filtrar_documentos(docs, "   ") == docs

    def test_busca_por_codigo_prefixo(self):
        # Docs 1 e 4 têm código "DE-15.23…"
        ids = [d["id"] for d in filtrar_documentos(self._docs(), "DE-15.23")]
        assert 1 in ids and 4 in ids
        assert 2 not in ids and 3 not in ids

    def test_busca_por_subclasse_no_codigo(self):
        result = filtrar_documentos(self._docs(), "6C1")
        assert [d["id"] for d in result] == [3]

    def test_busca_por_titulo(self):
        result = filtrar_documentos(self._docs(), "levantamento")
        assert [d["id"] for d in result] == [1]

    def test_busca_case_insensitive(self):
        result = filtrar_documentos(self._docs(), "FUNDAÇÕES")
        assert [d["id"] for d in result] == [2]

    def test_busca_sem_acento(self):
        result = filtrar_documentos(self._docs(), "fundacoes")
        assert [d["id"] for d in result] == [2]

    def test_busca_por_tipo(self):
        result = filtrar_documentos(self._docs(), "MC")
        assert [d["id"] for d in result] == [3]

    def test_busca_por_nome_trecho_sem_acento(self):
        result = filtrar_documentos(self._docs(), "oratorio")
        assert [d["id"] for d in result] == [3]

    def test_busca_por_nome_trecho_com_acento(self):
        result = filtrar_documentos(self._docs(), "Oratório")
        assert [d["id"] for d in result] == [3]

    def test_busca_por_disciplina_codigo(self):
        # Encontra docs 1 e 4 (ambos têm disciplina_display="B3")
        ids = [d["id"] for d in filtrar_documentos(self._docs(), "B3")]
        assert 1 in ids and 4 in ids

    def test_busca_por_disciplina_descricao(self):
        # "ARQUITETURA" como palavra única encontra B3 via disciplina_desc
        ids = [d["id"] for d in filtrar_documentos(self._docs(), "ARQUITETURA")]
        assert 1 in ids and 4 in ids

    def test_busca_multi_palavra_and_arquitetura_acabamento(self):
        # "arquitetura acabamento" → AND: ambas palavras na desc "ARQUITETURA - ACABAMENTO"
        ids = [d["id"] for d in filtrar_documentos(self._docs(), "arquitetura acabamento")]
        assert 1 in ids and 4 in ids
        assert 2 not in ids and 3 not in ids

    def test_busca_multi_palavra_and_sem_match(self):
        # AND: "arquitetura" existe mas "inexistente" não → zero resultados
        assert filtrar_documentos(self._docs(), "arquitetura inexistente") == []

    def test_busca_multi_palavra_and_disciplina_vazia_no_banco(self):
        # Simula doc com disciplina_display vazia (não enriquecido)
        docs_sem_enriquecimento = [
            {
                "id": 99, "codigo": "DE-15.23.17.84-6B3-9999",
                "titulo": "SEM DISCIPLINA NO BANCO", "tipo": "DE",
                "trecho": "23", "nome_trecho": "São Mateus",
                "modalidade": "", "disciplina_display": "",
                "disciplina_desc": "",
            }
        ]
        # Sem enriquecimento do parser, "arquitetura acabamento" NÃO encontra
        assert filtrar_documentos(docs_sem_enriquecimento, "arquitetura acabamento") == []
        # Após enriquecimento (simulado atribuindo disciplina_desc), passa a encontrar
        docs_enriquecidos = [{**docs_sem_enriquecimento[0],
                              "disciplina_display": "B3",
                              "disciplina_desc": "ARQUITETURA - ACABAMENTO"}]
        assert len(filtrar_documentos(docs_enriquecidos, "arquitetura acabamento")) == 1

    def test_busca_prefixo_codigo_detalhado(self):
        # Prefixo exato "MC-15.19.02.00-6C1" encontra doc 3 cujo código começa assim
        result = filtrar_documentos(self._docs(), "MC-15.19.02.00-6C1")
        assert [d["id"] for d in result] == [3]

    def test_busca_por_sequencial(self):
        ids = [d["id"] for d in filtrar_documentos(self._docs(), "1001")]
        assert 2 in ids and 3 in ids

    def test_nenhum_resultado(self):
        assert filtrar_documentos(self._docs(), "INEXISTENTE") == []

    def test_campos_customizados(self):
        result = filtrar_documentos(self._docs(), "DE", campos=["tipo"])
        assert [d["id"] for d in result] == [1, 2, 4]

    def test_preserva_ordem_original(self):
        result = filtrar_documentos(self._docs(), "DE-15")
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2
