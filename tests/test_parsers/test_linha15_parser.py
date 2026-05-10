"""
tests/test_parsers/test_linha15_parser.py

Testes do parser de código documental para a Linha 15 — Metrô de SP.

Execute com:
    pytest tests/ -v
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from core.parsers.linha15_parser import Linha15Parser
from core.parsers.registry import ParserRegistry
from core.parsers.base_parser import CodigoParseado, ErroDeparse


@pytest.fixture
def parser():
    return Linha15Parser()


@pytest.fixture
def registry():
    return ParserRegistry()


class TestCasosValidos:

    @pytest.mark.parametrize("codigo,tipo_esperado,trecho_esperado,seq_esperado", [
        ("DE-15.25.00.00-6A1-1001", "DE",  "25", "1001"),
        ("RT-15.25.00.00-6A1-1001", "RT",  "25", "1001"),
        ("ID-15.25.00.00-6A9-1001", "ID",  "25", "1001"),
        ("DE-15.23.17.84-6B3-1001", "DE",  "23", "1001"),
        ("MC-15.25.00.00-6F2-1001", "MC",  "25", "1001"),
        ("MD-15.23.17.84-6B3-1001", "MD",  "23", "1001"),
        ("NS-15.25.00.00-6F5-1001", "NS",  "25", "1001"),
        ("TC-15.25.00.00-6C1-1001", "TC",  "25", "1001"),
        ("LM-15.23.17.84-6B3-1001", "LM",  "23", "1001"),
        ("PE-15.00.00.00-6A9-1002", "PE",  "00", "1002"),
        ("MQ-15.00.00.00-6A9-1001", "MQ",  "00", "1001"),
        ("DE-15.19.02.00-6C1-1001", "DE",  "19", "1001"),
        ("IC-15.25.00.00-6A1-1001", "IC",  "25", "1001"),
    ])
    def test_codigo_valido_retorna_parsed(
        self, parser, codigo, tipo_esperado, trecho_esperado, seq_esperado
    ):
        resultado = parser.parse(codigo)
        assert isinstance(resultado, CodigoParseado), (
            f"Esperava CodigoParseado para '{codigo}', mas obteve: {resultado}"
        )
        assert resultado.valido is True
        assert resultado.tipo == tipo_esperado
        assert resultado.extras["trecho"] == trecho_esperado
        assert resultado.extras["sequencial"] == seq_esperado

    def test_codigo_maiusculo_e_minusculo_sao_equivalentes(self, parser):
        resultado_upper = parser.parse("DE-15.25.00.00-6A1-1001")
        resultado_lower = parser.parse("de-15.25.00.00-6a1-1001")
        assert resultado_upper.tipo == resultado_lower.tipo
        assert resultado_upper.identificador_base == resultado_lower.identificador_base

    def test_codigo_com_espacos_extras_e_aceito(self, parser):
        resultado = parser.parse("  DE-15.25.00.00-6A1-1001  ")
        assert isinstance(resultado, CodigoParseado)
        assert resultado.valido is True

    def test_identificador_base_sem_revisao(self, parser):
        r1 = parser.parse("DE-15.25.00.00-6A1-1001")
        r2 = parser.parse("DE-15.25.00.00-6A1-1001")
        assert isinstance(r1, CodigoParseado)
        assert isinstance(r2, CodigoParseado)
        assert r1.identificador_base == r2.identificador_base

    def test_descricao_tipo_conhecidos(self, parser):
        for sigla in ["DE", "IC", "MC", "MD", "RT", "ID", "PE", "LM", "NS", "TC"]:
            codigo = f"{sigla}-15.25.00.00-6A1-1001"
            resultado = parser.parse(codigo)
            assert isinstance(resultado, CodigoParseado)
            assert resultado.descricao_tipo != ""

    def test_campos_extras_presentes(self, parser):
        resultado = parser.parse("DE-15.25.00.00-6A1-1001")
        assert isinstance(resultado, CodigoParseado)
        campos_esperados = [
            "linha", "trecho", "nome_trecho", "subtrecho", "unidade",
            "etapa", "classe", "descricao_classe", "subclasse", "sequencial", "avisos"
        ]
        for campo in campos_esperados:
            assert campo in resultado.extras, f"Campo '{campo}' ausente em extras"

    def test_nome_trecho_ragueb(self, parser):
        resultado = parser.parse("DE-15.25.00.00-6A1-1001")
        assert isinstance(resultado, CodigoParseado)
        assert "Ragueb" in resultado.extras["nome_trecho"]

    def test_nome_trecho_sao_mateus(self, parser):
        resultado = parser.parse("DE-15.23.17.84-6B3-1001")
        assert isinstance(resultado, CodigoParseado)
        assert "Mateus" in resultado.extras["nome_trecho"]

    def test_parser_usado_identificado(self, parser):
        resultado = parser.parse("DE-15.25.00.00-6A1-1001")
        assert isinstance(resultado, CodigoParseado)
        assert resultado.parser_usado == "linha15_metro_sp"


class TestCasosInvalidos:

    @pytest.mark.parametrize("codigo,fragmento_mensagem", [
        ("",               "vazio"),
        ("DE",             "segmentos"),
        ("DE-15",          "segmentos"),
        ("DE-15.25.00.00-6A1", "segmentos"),     # 3 partes — agora capturado por < 4
        ("DE-99.25.00.00-6A1-1001", "linha"),    # linha != 15 validada no parse()
        ("DE-15.25-6A1-1001",      "bloco numérico"),
        ("DE-15.25.00.00-A1-1001", "padrão"),
        ("DE-15.25.00.00-6A-1001", "padrão"),
        ("DE-15.25.00.00-6A1-100", "padrão"),
        ("1DE-15.25.00.00-6A1-1001", "tipo documental"),
        # tipos não catalogados devem ser rejeitados
        ("ICS-15.25.00.00-6A1-1001", "catalogado"),
        ("DEF-15.25.00.00-6A1-1001", "catalogado"),
        ("SZ-15.25.00.00-6A1-1001",  "catalogado"),
        ("ZZ-15.25.00.00-6A1-1001",  "catalogado"),
        # EX não pertence à Lista Mestra Principal
        ("EX-15.25.00.00-6A1-1001",  "catalogado"),
    ])
    def test_codigo_invalido_retorna_erro(self, parser, codigo, fragmento_mensagem):
        resultado = parser.parse(codigo)
        assert isinstance(resultado, ErroDeparse), (
            f"Esperava ErroDeparse para '{codigo}', mas obteve: {resultado}"
        )
        assert resultado.valido is False
        assert fragmento_mensagem.lower() in resultado.mensagem.lower(), (
            f"Mensagem esperada conter '{fragmento_mensagem}', "
            f"mas foi: '{resultado.mensagem}'"
        )

    def test_erro_contem_codigo_original(self, parser):
        codigo = "INVALIDO"
        resultado = parser.parse(codigo)
        assert isinstance(resultado, ErroDeparse)
        assert resultado.codigo_original == codigo

    def test_erro_identifica_parser(self, parser):
        resultado = parser.parse("INVALIDO")
        assert isinstance(resultado, ErroDeparse)
        assert resultado.parser_usado == "linha15_metro_sp"


class TestAceita:

    @pytest.mark.parametrize("codigo,esperado", [
        ("DE-15.25.00.00-6A1-1001", True),
        ("RT-15.23.17.84-6B3-1001", True),
        ("de-15.25.00.00-6a1-1001", True),
        ("DE-99.25.00.00-6A1-1001", False),
        ("DE-1.25.00.00-6A1-1001",  False),
        ("INVALIDO",                False),
        ("",                        False),
    ])
    def test_aceita_apenas_linha_15(self, parser, codigo, esperado):
        assert parser.aceita(codigo) == esperado, (
            f"aceita('{codigo}') deveria ser {esperado}"
        )


class TestRegistry:

    def test_registry_detecta_parser_linha15(self, registry):
        p = registry.detectar_parser("DE-15.25.00.00-6A1-1001")
        assert p is not None
        assert p.nome == "linha15_metro_sp"

    def test_registry_parse_codigo_valido(self, registry):
        resultado = registry.parse("DE-15.25.00.00-6A1-1001")
        assert isinstance(resultado, CodigoParseado)
        assert resultado.tipo == "DE"

    def test_registry_parse_codigo_invalido(self, registry):
        resultado = registry.parse("CODIGO_INEXISTENTE")
        assert isinstance(resultado, ErroDeparse)

    def test_registry_parse_vazio(self, registry):
        resultado = registry.parse("")
        assert isinstance(resultado, ErroDeparse)
        assert "vazio" in resultado.mensagem.lower()

    def test_registry_parse_com_parser_explicito(self, registry):
        resultado = registry.parse(
            "DE-15.25.00.00-6A1-1001",
            parser="linha15_metro_sp"
        )
        assert isinstance(resultado, CodigoParseado)

    def test_registry_parse_com_parser_inexistente(self, registry):
        resultado = registry.parse(
            "DE-15.25.00.00-6A1-1001",
            parser="parser_que_nao_existe"
        )
        assert isinstance(resultado, ErroDeparse)
        assert "não encontrado" in resultado.mensagem.lower()

    def test_registry_parse_lote(self, registry):
        codigos = [
            "DE-15.25.00.00-6A1-1001",
            "RT-15.23.17.84-6B3-1001",
            "INVALIDO",
        ]
        resultados = registry.parse_lote(codigos)
        assert len(resultados) == 3
        assert isinstance(resultados["DE-15.25.00.00-6A1-1001"], CodigoParseado)
        assert isinstance(resultados["RT-15.23.17.84-6B3-1001"], CodigoParseado)
        assert isinstance(resultados["INVALIDO"], ErroDeparse)

    def test_registry_lista_parsers_disponiveis(self, registry):
        disponiveis = registry.parsers_disponiveis()
        assert "linha15_metro_sp" in disponiveis
