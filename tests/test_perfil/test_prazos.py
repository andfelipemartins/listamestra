from datetime import date
from pathlib import Path

import pytest
import yaml

from core.perfil.feriados import feriados_nacionais
from core.perfil.modelo import ErroPerfil, carregar_yaml, perfil_de_dict
from core.perfil.prazos import AvaliacaoPrazo, avaliar, indicador, vencimento


ROOT = Path(__file__).parents[2]


def test_vencimento_util_pula_fim_de_semana_e_sexta_feira_santa():
    assert vencimento(
        date(2025, 4, 16), 3, "uteis", feriados_nacionais(2025)
    ) == date(2025, 4, 23)


def test_vencimento_corrido_conta_a_partir_do_dia_seguinte():
    assert vencimento(date(2026, 1, 1), 15, "corridos") == date(2026, 1, 16)


def test_excecao_de_prazo_por_sigla():
    regra = {
        "dias": 15,
        "tipo_dia": "corridos",
        "excecoes": [{"siglas": ["MM", "MO"], "dias": 30}],
    }

    manual = avaliar(regra, date(2026, 1, 1), date(2026, 1, 31), date(2026, 2, 1), sigla="MO")
    desenho = avaliar(regra, date(2026, 1, 1), date(2026, 1, 31), date(2026, 2, 1), sigla="DE")

    assert manual == AvaliacaoPrazo("no_prazo", date(2026, 1, 31), 0)
    assert desenho == AvaliacaoPrazo("atrasado", date(2026, 1, 16), 15)


def test_regra_filtrada_por_grupo_nao_avalia_outro_grupo():
    regra = {"dias": 15, "tipo_dia": "corridos", "so_quando_grupo": ["nao_aprovado"]}

    assert avaliar(regra, date(2026, 1, 1), None, date(2026, 1, 20), grupo="aprovado") is None
    assert avaliar(regra, date(2026, 1, 1), None, date(2026, 1, 20), grupo="NAO_APROVADO").situacao == "aberto_atrasado"


def test_prazo_aberto_vencido_informa_dias_de_atraso():
    resultado = avaliar(
        {"dias": 15, "tipo_dia": "corridos"},
        date(2026, 1, 1),
        None,
        date(2026, 1, 20),
    )

    assert resultado == AvaliacaoPrazo("aberto_atrasado", date(2026, 1, 16), 4)


def test_indicador_usa_concluidos_e_abertos_vencidos_na_base():
    resultado = indicador(
        [
            AvaliacaoPrazo("no_prazo", date(2026, 1, 16), 0),
            AvaliacaoPrazo("atrasado", date(2026, 1, 16), 2),
            AvaliacaoPrazo("aberto_atrasado", date(2026, 1, 16), 4),
            AvaliacaoPrazo("aberto_no_prazo", date(2026, 1, 30), 0),
        ]
    )

    assert resultado.dentro == 1
    assert resultado.fora == 2
    assert resultado.base == 3
    assert resultado.percentual_cumprido == pytest.approx(100 / 3)


def test_perfil_metro_carrega_prazos_configurados():
    perfil = carregar_yaml(ROOT / "core" / "perfil" / "exemplos" / "metro.yaml")

    assert perfil.prazos.meta_percentual == 80
    assert perfil.prazos.meta_cronograma == 80
    assert perfil.prazos.feriados.nacionais is True
    assert [regra.id for regra in perfil.prazos.regras] == ["analise_cliente", "devolucao_nossa"]
    assert perfil.prazos.regras[0].meta_percentual is None
    assert perfil.prazos.regras[0].excecoes[0].siglas == ("MM", "MO", "MP", "MQ", "MU")
    assert perfil.prazos.regras[0].excecoes[0].dias == 30
    assert perfil.prazos.regras[0].dias == 15
    assert perfil.prazos.regras[0].tipo_dia == "uteis"
    assert perfil.prazos.regras[1].meta_percentual == 80
    assert perfil.prazos.regras[1].tipo_dia == "corridos"
    assert perfil.prazos.regras[1].so_quando_grupo == ("nao_aprovado", "inconsistente")


def test_meta_especifica_da_regra_substitui_o_padrao():
    with (ROOT / "core" / "perfil" / "exemplos" / "metro.yaml").open(encoding="utf-8") as arquivo:
        dados = yaml.safe_load(arquivo)
    dados["prazos"]["regras"][1]["meta_percentual"] = 65
    dados["prazos"]["meta_cronograma"] = 75

    perfil = perfil_de_dict(dados)

    assert perfil.prazos.regras[1].meta_percentual == 65
    assert perfil.prazos.meta_cronograma == 75


def test_perfil_antigo_com_meta_geral_aplica_padrao_as_regras_e_cronograma():
    with (ROOT / "core" / "perfil" / "exemplos" / "metro.yaml").open(encoding="utf-8") as arquivo:
        dados = yaml.safe_load(arquivo)
    dados["prazos"].pop("meta_cronograma")
    for regra in dados["prazos"]["regras"]:
        regra.pop("meta_percentual", None)

    perfil = perfil_de_dict(dados)

    assert [regra.meta_percentual for regra in perfil.prazos.regras] == [80, 80]
    assert perfil.prazos.meta_cronograma == 80


def test_excecao_mo_aplica_30_dias_uteis():
    perfil = carregar_yaml(ROOT / "core" / "perfil" / "exemplos" / "metro.yaml")
    regra = perfil.prazos.regras[0]

    resultado = avaliar(
        regra,
        date(2026, 1, 1),
        date(2026, 2, 12),
        date(2026, 2, 12),
        sigla="MO",
    )

    assert resultado == AvaliacaoPrazo("no_prazo", date(2026, 2, 12), 0)


def test_spobras_permanece_sem_secao_de_prazos():
    perfil = carregar_yaml(ROOT / "core" / "perfil" / "exemplos" / "spobras.yaml")

    assert perfil.prazos is None


def test_validacao_rejeita_tipo_de_dia_invalido():
    dados = {
        "nome": "Perfil de teste",
        "versao": "1",
        "vigencia_inicio": "2026-01-01",
        "codigo": {"segmentos": [{"nome": "codigo", "padrao_regex": "[A-Z]+"}]},
        "emissao": {"revisao": {"preliminar": "letras", "original": "numerica"}},
        "analise": {"inicial": "INICIAL", "transicoes": {}},
        "prazos": {
            "meta_percentual": 80,
            "regras": [
                {
                    "id": "prazo",
                    "rotulo": "Prazo",
                    "dias": 15,
                    "tipo_dia": "uteis_com_feriados_facultativos",
                    "inicio": "emissao",
                    "fim": "analise",
                }
            ],
        },
    }

    with pytest.raises(ErroPerfil, match="uteis.*corridos"):
        perfil_de_dict(dados)
