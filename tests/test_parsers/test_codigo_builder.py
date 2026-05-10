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
    parsear_lista_codigos,
    mesclar_codigos,
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

    def test_tipo_ic_dois_chars(self):
        codigo = montar_codigo_linha15("IC", "25", "00", "00", "6", "B", "2", "2001")
        assert codigo == "IC-15.25.00.00-6B2-2001"

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


# ---------------------------------------------------------------------------
# parsear_lista_codigos
# ---------------------------------------------------------------------------

class TestParsearListaCodigos:

    def test_codigo_unico_valido(self):
        validos, invalidos = parsear_lista_codigos("DE-15.25.00.00-6A1-1001", _registry)
        assert len(validos) == 1
        assert len(invalidos) == 0
        assert validos[0][0] == "DE-15.25.00.00-6A1-1001"

    def test_multiplos_validos(self):
        texto = "DE-15.25.00.00-6F2-1001\nDE-15.25.00.00-6F2-1002\nDE-15.25.00.00-6F2-1003"
        validos, invalidos = parsear_lista_codigos(texto, _registry)
        assert len(validos) == 3
        assert len(invalidos) == 0

    def test_codigo_invalido_detectado(self):
        validos, invalidos = parsear_lista_codigos("INVALIDO", _registry)
        assert len(validos) == 0
        assert len(invalidos) == 1
        assert invalidos[0][0] == "INVALIDO"

    def test_mistura_validos_e_invalidos(self):
        texto = "DE-15.25.00.00-6A1-1001\nNAO_VALIDO\nMC-15.25.00.00-6A1-1002"
        validos, invalidos = parsear_lista_codigos(texto, _registry)
        assert len(validos) == 2
        assert len(invalidos) == 1
        assert invalidos[0][0] == "NAO_VALIDO"

    def test_linhas_vazias_ignoradas(self):
        texto = "\nDE-15.25.00.00-6A1-1001\n\n\nDE-15.25.00.00-6A1-1002\n"
        validos, invalidos = parsear_lista_codigos(texto, _registry)
        assert len(validos) == 2
        assert len(invalidos) == 0

    def test_espacos_extras_normalizados(self):
        texto = "  DE-15.25.00.00-6A1-1001  \n  DE-15.25.00.00-6A1-1002  "
        validos, invalidos = parsear_lista_codigos(texto, _registry)
        assert len(validos) == 2
        assert validos[0][0] == "DE-15.25.00.00-6A1-1001"

    def test_minusculas_normalizadas_para_maiusculas(self):
        validos, invalidos = parsear_lista_codigos("de-15.25.00.00-6a1-1001", _registry)
        assert len(validos) == 1
        assert validos[0][0] == "DE-15.25.00.00-6A1-1001"

    def test_texto_vazio_retorna_listas_vazias(self):
        validos, invalidos = parsear_lista_codigos("", _registry)
        assert validos == []
        assert invalidos == []

    def test_apenas_espacos_retorna_listas_vazias(self):
        validos, invalidos = parsear_lista_codigos("   \n   \n   ", _registry)
        assert validos == []
        assert invalidos == []

    def test_resultado_valido_tem_parsed_valido(self):
        validos, _ = parsear_lista_codigos("DE-15.25.00.00-6A1-1001", _registry)
        codigo, parsed = validos[0]
        assert parsed.valido is True
        assert parsed.tipo == "DE"

    def test_resultado_invalido_tem_mensagem(self):
        _, invalidos = parsear_lista_codigos("RUIM", _registry)
        codigo, erro = invalidos[0]
        assert erro.mensagem != ""

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

    def test_desmonta_tipo_ic(self):
        resultado = desmontar_codigo_linha15("IC-15.25.00.00-6B2-2001", _registry)
        assert resultado is not None
        assert resultado["tipo"] == "IC"


# ---------------------------------------------------------------------------
# mesclar_codigos
# ---------------------------------------------------------------------------

class TestMesclarCodigos:

    def _parse(self, texto: str) -> list:
        validos, _ = parsear_lista_codigos(texto, _registry)
        return validos

    def test_adiciona_a_lista_vazia(self):
        merged, dup = mesclar_codigos(self._parse("DE-15.25.00.00-6A1-1001"), [])
        assert len(merged) == 1
        assert dup == 0

    def test_adiciona_a_lista_existente(self):
        existentes = self._parse("DE-15.25.00.00-6A1-1001")
        novos      = self._parse("DE-15.25.00.00-6A1-1002")
        merged, dup = mesclar_codigos(novos, existentes)
        assert len(merged) == 2
        assert dup == 0

    def test_duplicata_nao_adicionada(self):
        existentes = self._parse("DE-15.25.00.00-6A1-1001")
        novos      = self._parse("DE-15.25.00.00-6A1-1001")
        merged, dup = mesclar_codigos(novos, existentes)
        assert len(merged) == 1
        assert dup == 1

    def test_mistura_novos_e_duplicatas(self):
        existentes = self._parse("DE-15.25.00.00-6A1-1001\nDE-15.25.00.00-6A1-1002")
        novos      = self._parse("DE-15.25.00.00-6A1-1002\nDE-15.25.00.00-6A1-1003")
        merged, dup = mesclar_codigos(novos, existentes)
        assert len(merged) == 3
        assert dup == 1

    def test_preserva_ordem_existentes_primeiro(self):
        existentes = self._parse("DE-15.25.00.00-6A1-1001\nDE-15.25.00.00-6A1-1002")
        novos      = self._parse("DE-15.25.00.00-6A1-1003")
        merged, _  = mesclar_codigos(novos, existentes)
        assert merged[0][0] == "DE-15.25.00.00-6A1-1001"
        assert merged[1][0] == "DE-15.25.00.00-6A1-1002"
        assert merged[2][0] == "DE-15.25.00.00-6A1-1003"

    def test_listas_vazias(self):
        merged, dup = mesclar_codigos([], [])
        assert merged == []
        assert dup == 0

    def test_multiplas_duplicatas_contadas(self):
        existentes = self._parse("DE-15.25.00.00-6A1-1001\nDE-15.25.00.00-6A1-1002\nDE-15.25.00.00-6A1-1003")
        novos      = self._parse("DE-15.25.00.00-6A1-1001\nDE-15.25.00.00-6A1-1002")
        merged, dup = mesclar_codigos(novos, existentes)
        assert len(merged) == 3
        assert dup == 2
