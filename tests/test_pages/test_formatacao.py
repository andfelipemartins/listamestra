"""
tests/test_pages/test_formatacao.py

Testes dos helpers de formatação de exibição (core/formatacao.py).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from core.formatacao import fmt_inteiro, fmt_data, disciplina_do_codigo


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
