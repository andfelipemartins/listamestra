from dataclasses import FrozenInstanceError
import csv
from pathlib import Path

import pytest

from core.perfil.codigo import CodigoInterpretado, ErroCodigo, interpretar, montar
from core.perfil.ciclo import ErroCiclo, EstadoEmissao, aplicar, iniciar, rotulo_cronologico
from core.perfil.modelo import ErroPerfil, carregar_yaml, perfil_de_dict
from core.perfil.series import (
    SerieLetras,
    SerieLetraMaisNumero,
    SerieNumerica,
    SerieZeroDepoisLetras,
)


ROOT = Path(__file__).parents[2]


@pytest.fixture
def metro():
    return carregar_yaml(ROOT / "core" / "perfil" / "exemplos" / "metro.yaml")


@pytest.fixture
def spobras():
    return carregar_yaml(ROOT / "core" / "perfil" / "exemplos" / "spobras.yaml")


def test_metro_interpreta_e_monta_codigo(metro):
    resultado = interpretar(metro, "DE-15.25.00.00-6A1-1001")

    assert isinstance(resultado, CodigoInterpretado)
    assert resultado.segmentos["tipo"] == "DE"
    assert resultado.segmentos["trecho"] == "25"
    assert resultado.segmentos["etapa"] == "6"
    assert resultado.segmentos["classe"] == "A1"
    assert resultado.segmentos["sequencial"] == "1001"
    assert resultado.revisao is None
    assert resultado.identificador_base == "DE-15.25.00.00-6A1-1001"
    assert resultado.significados["tipo"] == "Desenho"
    assert resultado.significados["classe"] == "Método construtivo"
    assert montar(metro, resultado.segmentos) == resultado.original.upper()


def test_metro_interpreta_classe_e_subclasse_com_rotulo(metro):
    resultado = interpretar(metro, "DE-15.25.00.00-6P7-1513")

    assert isinstance(resultado, CodigoInterpretado)
    assert resultado.segmentos["classe"] == "P7"
    assert resultado.significados["classe"] == "Iluminação"


def test_metro_rejeita_classe_que_nao_consta_nas_tabelas(metro):
    resultado = interpretar(metro, "DE-15.25.00.00-6X1-1513")

    assert isinstance(resultado, ErroCodigo)
    assert resultado.segmento == "classe"
    assert "classe e subclasse" in resultado.mensagem


def test_codigo_metro_invalido_aponta_segmento(metro):
    resultado = interpretar(metro, "DE-15.2X.00.00-6A1-1001")

    assert isinstance(resultado, ErroCodigo)
    assert resultado.segmento == "trecho"
    assert "trecho" in resultado.mensagem


def test_spobras_revisao_faz_parte_do_codigo(spobras):
    resultado = interpretar(spobras, "DE-CC-EE-WW-5E-001-A")

    assert isinstance(resultado, CodigoInterpretado)
    assert resultado.segmentos["classificacao"] == "DE"
    assert resultado.segmentos["estagio"] == "5"
    assert resultado.segmentos["classe"] == "E"
    assert resultado.segmentos["sequencial"] == "001"
    assert resultado.revisao == "A"
    assert resultado.identificador_base == "DE-CC-EE-WW-5E-001"
    assert montar(spobras, resultado.segmentos) == "DE-CC-EE-WW-5E-001-A"


def test_spobras_aceita_alfa_numerico_de_dois_caracteres(spobras):
    resultado = interpretar(spobras, "DE-C7-EE-0W-5E-001-1")
    assert isinstance(resultado, CodigoInterpretado)
    assert resultado.segmentos["programa"] == "C7"
    assert resultado.revisao == "1"


def test_equivalencia_real(metro, spobras):
    fixture = ROOT / "tests" / "test_perfil" / "fixtures" / "equivalencia_metro_spobras.tsv"
    with fixture.open(encoding="utf-8", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo, delimiter="\t"))

    assert len(linhas) == 281
    for linha in linhas:
        codigo_metro = interpretar(metro, linha["metro"])
        codigo_spobras = interpretar(spobras, linha["spobras"])

        assert isinstance(codigo_metro, CodigoInterpretado), (linha["metro"], codigo_metro)
        assert isinstance(codigo_spobras, CodigoInterpretado), (linha["spobras"], codigo_spobras)
        assert codigo_spobras.identificador_base == linha["spobras"].rsplit("-", 1)[0]
        assert codigo_spobras.revisao == "A"


def test_spobras_rejeita_letra_no_sequencial_e_classe_fora_da_tabela(spobras):
    sequencial_com_letra = interpretar(spobras, "DE-CC-EE-WW-5E-0A1-A")
    classe_fora_da_tabela = interpretar(spobras, "DE-CC-EE-WW-51-001-A")

    assert isinstance(sequencial_com_letra, ErroCodigo)
    assert isinstance(classe_fora_da_tabela, ErroCodigo)
    assert classe_fora_da_tabela.segmento == "classe"


def test_validacao_do_perfil_reporta_regex_e_segmentos_repetidos(metro):
    dados = {
        "nome": "Teste",
        "versao": "1",
        "vigencia_inicio": "2024-01-01",
        "codigo": {
            "segmentos": [
                {"nome": "codigo", "padrao_regex": "["},
                {"nome": "codigo", "padrao_regex": "\\d+"},
            ]
        },
        "emissao": {
            "revisao": {"preliminar": "letras", "original": "numerica"}
        },
        "analise": {"inicial": "INICIAL", "transicoes": {}},
    }
    with pytest.raises(ErroPerfil, match="Regex inválida"):
        perfil_de_dict(dados)

    dados["codigo"]["segmentos"] = [
        {"nome": "codigo", "padrao_regex": "[A-Z]+"},
        {"nome": "codigo", "padrao_regex": "\\d+"},
    ]
    with pytest.raises(ErroPerfil, match="repetidos"):
        perfil_de_dict(dados)


def test_perfil_e_estruturas_sao_imutaveis(metro):
    with pytest.raises(FrozenInstanceError):
        metro.nome = "Outro"
    with pytest.raises(TypeError):
        metro.codigo.campos[0].valores["XX"] = "Inválido"


def test_restricao_entre_segmentos():
    sintetico = perfil_de_dict(
        {
            "nome": "Perfil sintético",
            "versao": "1",
            "vigencia_inicio": "2024-01-01",
            "codigo": {
                "segmentos": [
                    {"nome": "tipo", "rotulo": "tipo", "padrao_regex": "[A-Z]{2}"},
                    {"sep": "-"},
                    {"nome": "classe", "rotulo": "classe", "padrao_regex": "\\d"},
                ],
                "restricoes": [
                    {
                        "se_segmento": "tipo",
                        "igual_a": "DE",
                        "entao_segmento": "classe",
                        "em": ["1"],
                    }
                ],
            },
            "emissao": {
                "revisao": {"preliminar": "numerica", "original": "numerica"}
            },
            "analise": {"inicial": "INICIAL", "transicoes": {}},
        }
    )
    valido = interpretar(sintetico, "DE-1")
    invalido = interpretar(sintetico, "DE-2")

    assert isinstance(valido, CodigoInterpretado)
    assert isinstance(invalido, ErroCodigo)
    assert invalido.segmento == "classe"
    assert "classe deve estar" in invalido.mensagem


def test_series_fechadas_e_transbordos():
    numerica = SerieNumerica(inicio=1)
    letras = SerieLetras(proibidas=("O",))
    zero_letras = SerieZeroDepoisLetras(proibidas=("O",))
    mista = SerieLetraMaisNumero(proibidas=("O",))

    assert numerica.primeira() == "1"
    assert numerica.proxima("2") == "3"
    assert letras.proxima("N") == "P"
    assert letras.proxima("Z") == "AA"
    assert not letras.valida("O")
    assert zero_letras.primeira() == "0"
    assert zero_letras.proxima("0") == "A"
    assert mista.primeira() == "A1"
    assert mista.proxima("A1") == "A2"


def _aplicar(perfil, estado, situacao):
    novo = aplicar(perfil, estado, situacao)
    assert isinstance(novo, EstadoEmissao), getattr(novo, "mensagem", "")
    return novo


def test_ciclo_metro_d018_completo(metro):
    estado = iniciar(metro)
    assert (estado.revisao, estado.versao) == ("1", "1")
    estado = _aplicar(metro, estado, "NÃO CONFORME")
    assert (estado.revisao, estado.versao) == ("1", "2")
    estado = _aplicar(metro, estado, "INCONSISTENTE")
    assert (estado.revisao, estado.versao, estado.bloqueia_medicao) == ("1", "3", True)
    estado = _aplicar(metro, estado, "NÃO APROVADO")
    assert (estado.revisao, estado.versao) == ("2", "1")
    estado = _aplicar(metro, estado, "APROVADO")
    assert (estado.revisao, estado.versao, estado.fase) == ("0", "1", "original")
    estado = _aplicar(metro, estado, "REABRIR")
    assert (estado.revisao, estado.versao) == ("A1", "1")
    estado = _aplicar(metro, estado, "NÃO APROVADO")
    assert (estado.revisao, estado.versao) == ("A2", "1")
    estado = _aplicar(metro, estado, "APROVADO")
    assert (estado.revisao, estado.versao) == ("A", "1")
    estado = _aplicar(metro, estado, "REABRIR")
    assert (estado.revisao, estado.versao) == ("B1", "1")
    estado = _aplicar(metro, estado, "CANCELADO")
    assert estado.fase == "encerrado"
    erro = aplicar(metro, estado, "APROVADO")
    assert isinstance(erro, ErroCiclo)


def test_ciclo_spobras_continua_letras_apos_aprovacao(spobras):
    estado = iniciar(spobras)
    assert estado.revisao == "A"
    estado = _aplicar(spobras, estado, "NÃO APROVADO")
    assert estado.revisao == "B"
    estado = _aplicar(spobras, estado, "APROVADO")
    assert (estado.revisao, estado.fase) == ("1", "original")
    estado = _aplicar(spobras, estado, "REABRIR")
    assert estado.revisao == "C"
    estado = _aplicar(spobras, estado, "A REVISAR")
    assert estado.revisao == "D"
    estado = _aplicar(spobras, estado, "APROVADO")
    assert estado.revisao == "2"


def test_rotulos_cronologicos():
    assert rotulo_cronologico([]) == []
    assert rotulo_cronologico(["Rev 1 Ver 1", "Rev 1 Ver 2", "Rev 2 Ver 1"]) == [
        "Emissão Inicial",
        "Revisão 1",
        "Revisão 2",
    ]


def test_perfil_com_serie_desconhecida_e_segmento_de_revisao_invalido():
    dados = {
        "nome": "Teste",
        "versao": "1",
        "vigencia_inicio": "2024-01-01",
        "codigo": {
            "segmentos": [{"nome": "codigo", "padrao_regex": "[A-Z]+"}],
            "revisao_no_codigo": True,
            "segmento_revisao": "rev",
        },
        "emissao": {"revisao": {"preliminar": "inventada", "original": "numerica"}},
        "analise": {"inicial": "INICIAL", "transicoes": {}},
    }
    with pytest.raises(ErroPerfil, match="segmento de revisão existente"):
        perfil_de_dict(dados)

    dados["codigo"]["revisao_no_codigo"] = False
    dados["codigo"].pop("segmento_revisao")
    with pytest.raises(ErroPerfil, match="Série inválida"):
        perfil_de_dict(dados)
