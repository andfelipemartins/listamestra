"""
tests/test_parsers/test_codigo_builder.py

Testes de montar_codigo_linha15 e desmontar_codigo_linha15.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from core.parsers.codigo_builder import (
    montar_codigo_linha15,
    desmontar_codigo_linha15,
    LINHA15_TIPOS,
    LINHA15_TRECHOS,
    LINHA15_CLASSES,
)
from core.parsers.registry import ParserRegistry

_registry = ParserRegistry()


# ---------------------------------------------------------------------------
# Constantes públicas
# ---------------------------------------------------------------------------

class TestConstantes:

    def test_tipos_nao_vazio(self):
        assert len(LINHA15_TIPOS) > 0

    def test_trechos_conhecidos(self):
        for codigo in ("00", "19", "23", "25"):
            assert codigo in LINHA15_TRECHOS

    def test_classes_A_a_I(self):
        for letra in "ABCDEFGHI":
            assert letra in LINHA15_CLASSES

    def test_de_esta_nos_tipos(self):
        assert "DE" in LINHA15_TIPOS

    def test_mc_esta_nos_tipos(self):
        assert "MC" in LINHA15_TIPOS


# ---------------------------------------------------------------------------
# montar_codigo_linha15
# ---------------------------------------------------------------------------

class TestMontarCodigo:

    def test_caso_basico(self):
        codigo = montar_codigo_linha15("DE", "25", "00", "00", "6", "A", "1", "1001")
        assert codigo == "DE-15.25.00.00-6A1-1001"

    def test_tipo_lowercase_normalizado(self):
        codigo = montar_codigo_linha15("de", "25", "00", "00", "6", "A", "1", "1001")
        assert codigo == "DE-15.25.00.00-6A1-1001"

    def test_classe_lowercase_normalizada(self):
        codigo = montar_codigo_linha15("DE", "25", "00", "00", "6", "a", "1", "1001")
        assert codigo == "DE-15.25.00.00-6A1-1001"

    def test_trecho_zero_padded(self):
        codigo = montar_codigo_linha15("DE", "19", "00", "00", "6", "A", "1", "1001")
        assert "15.19." in codigo

    def test_sequencial_zero_padded(self):
        codigo = montar_codigo_linha15("DE", "25", "00", "00", "6", "A", "1", "5")
        assert codigo.endswith("-0005")

    def test_trecho_geral(self):
        codigo = montar_codigo_linha15("ID", "00", "00", "00", "6", "A", "1", "0001")
        assert codigo == "ID-15.00.00.00-6A1-0001"

    def test_tipo_tres_letras(self):
        codigo = montar_codigo_linha15("ICS", "25", "00", "00", "6", "B", "2", "2001")
        assert codigo == "ICS-15.25.00.00-6B2-2001"

    def test_resultado_valido_pelo_parser(self):
        codigo = montar_codigo_linha15("DE", "25", "00", "00", "6", "A", "1", "1001")
        parsed = _registry.parse(codigo)
        assert parsed.valido is True

    def test_multiplos_tipos(self):
        for tipo in ("DE", "MC", "MD", "RT"):
            codigo = montar_codigo_linha15(tipo, "25", "00", "00", "6", "A", "1", "1001")
            assert codigo.startswith(f"{tipo}-15.")

    def test_multiplas_classes(self):
        for classe in "ABCDEFGHI":
            codigo = montar_codigo_linha15("DE", "25", "00", "00", "6", classe, "1", "1001")
            parsed = _registry.parse(codigo)
            assert parsed.valido is True
            assert parsed.extras["classe"] == classe


# ---------------------------------------------------------------------------
# desmontar_codigo_linha15
# ---------------------------------------------------------------------------

class TestDesmontarCodigo:

    def test_desmonta_codigo_valido(self):
        resultado = desmontar_codigo_linha15("DE-15.25.00.00-6A1-1001", _registry)
        assert resultado is not None
        assert resultado["tipo"] == "DE"
        assert resultado["trecho"] == "25"
        assert resultado["subtrecho"] == "00"
        assert resultado["unidade"] == "00"
        assert resultado["etapa"] == "6"
        assert resultado["classe"] == "A"
        assert resultado["subclasse"] == "1"
        assert resultado["sequencial"] == "1001"

    def test_desmonta_codigo_invalido_retorna_none(self):
        resultado = desmontar_codigo_linha15("INVALIDO", _registry)
        assert resultado is None

    def test_desmonta_string_vazia_retorna_none(self):
        resultado = desmontar_codigo_linha15("", _registry)
        assert resultado is None

    def test_round_trip(self):
        original = "DE-15.25.00.00-6A1-1001"
        partes = desmontar_codigo_linha15(original, _registry)
        assert partes is not None
        reconstruido = montar_codigo_linha15(**partes)
        assert reconstruido == original

    def test_round_trip_trecho_19(self):
        original = "MC-15.19.01.00-6C2-0042"
        partes = desmontar_codigo_linha15(original, _registry)
        assert partes is not None
        reconstruido = montar_codigo_linha15(**partes)
        assert reconstruido == original

    def test_desmonta_tipo_tres_letras(self):
        resultado = desmontar_codigo_linha15("ICS-15.25.00.00-6B2-2001", _registry)
        assert resultado is not None
        assert resultado["tipo"] == "ICS"
