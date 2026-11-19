from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from core.perfil import (
    DocumentoIndicador,
    EmissaoIndicador,
    ErroPerfil,
    calcular_indicador_aprovacao,
    carregar_yaml,
    perfil_de_dict,
)


ROOT = Path(__file__).parents[2]


@pytest.fixture
def metro():
    return carregar_yaml(ROOT / "core" / "perfil" / "exemplos" / "metro.yaml")


def _documento(grupo, emissoes, situacao=None, recorte="25"):
    return DocumentoIndicador(grupo, situacao, tuple(emissoes), recorte)


def test_aprovacao_na_copia_3_fica_dentro_do_limite(metro):
    documento = _documento(
        "aprovado",
        [
            EmissaoIndicador("preliminar", "1", "Não Aprovado"),
            EmissaoIndicador("preliminar", "2", "Não Aprovado"),
            EmissaoIndicador("preliminar", "3", "Aprovado"),
        ],
        "Aprovado",
    )

    resultado = calcular_indicador_aprovacao(
        metro, metro.painel.indicadores[0], [documento]
    )

    assert (resultado.geral.dentro_limite, resultado.geral.fora_limite) == (1, 0)
    assert resultado.geral.percentual == 100


def test_aprovacao_na_quarta_emissao_fica_dentro_do_limite(metro):
    documento = _documento(
        "aprovado",
        [
            EmissaoIndicador("preliminar", str(numero), "Aprovado" if numero == 4 else "Não Aprovado")
            for numero in range(1, 5)
        ],
        "Aprovado",
    )

    resultado = calcular_indicador_aprovacao(
        metro, metro.painel.indicadores[0], [documento]
    )

    assert (resultado.geral.dentro_limite, resultado.geral.fora_limite) == (1, 0)
    assert resultado.geral.percentual == 100


def test_emissoes_com_mesma_revisao_e_versoes_diferentes_contam_como_revisoes(metro):
    documento = _documento(
        "aprovado",
        [
            EmissaoIndicador("preliminar", "1", "Não Aprovado", versao=1),
            EmissaoIndicador("preliminar", "1", "Não Aprovado", versao=2),
            EmissaoIndicador("preliminar", "2", "Não Aprovado", versao=1),
            EmissaoIndicador("preliminar", "2", "Aprovado", versao=2),
        ],
        "Aprovado",
    )

    resultado = calcular_indicador_aprovacao(
        metro, metro.painel.indicadores[0], [documento]
    )

    assert (resultado.geral.dentro_limite, resultado.geral.fora_limite) == (1, 0)


def test_quinta_emissao_aprovada_excede_limite_de_tres_revisoes(metro):
    documento = _documento(
        "aprovado",
        [
            EmissaoIndicador("preliminar", "1", "Não Aprovado", versao=1),
            EmissaoIndicador("preliminar", "1", "Não Aprovado", versao=2),
            EmissaoIndicador("preliminar", "2", "Não Aprovado", versao=1),
            EmissaoIndicador("preliminar", "2", "Não Aprovado", versao=2),
            EmissaoIndicador("preliminar", "3", "Aprovado", versao=1),
        ],
        "Aprovado",
    )

    resultado = calcular_indicador_aprovacao(
        metro, metro.painel.indicadores[0], [documento]
    )

    assert (resultado.geral.dentro_limite, resultado.geral.fora_limite) == (0, 1)


def test_indicador_resolve_situacao_oculta_pela_historica_valida(metro):
    documento = DocumentoIndicador(
        "erro",
        "Erro de Assinatura",
        (
            EmissaoIndicador(
                "preliminar",
                "1",
                "Erro de Assinatura",
                situacoes_mais_recentes=("Erro de Assinatura", "Aprovado"),
            ),
        ),
        "25",
        situacoes_mais_recentes=("Erro de Assinatura", "Aprovado"),
    )

    resultado = calcular_indicador_aprovacao(
        metro, metro.painel.indicadores[0], [documento]
    )

    assert resultado.geral.dentro_limite == 1
    assert resultado.geral.fora_limite == 0


def test_nao_aprovado_na_copia_5_so_entra_com_opcao_ligada(metro):
    documento = _documento(
        "nao_aprovado",
        [EmissaoIndicador("preliminar", str(numero), "Não Aprovado") for numero in range(1, 6)],
        "Não Aprovado",
    )
    indicador = metro.painel.indicadores[0]

    ligado = calcular_indicador_aprovacao(
        metro,
        replace(indicador, contar_estourados_sem_aprovacao=True),
        [documento],
    )
    desligado = calcular_indicador_aprovacao(
        metro, replace(indicador, contar_estourados_sem_aprovacao=False), [documento]
    )

    assert (ligado.geral.dentro_limite, ligado.geral.fora_limite) == (0, 1)
    assert desligado.geral.percentual is None


def test_reaberturas_a1_a2_nao_entram_na_contagem_do_primeiro_ciclo(metro):
    emissoes = [
        EmissaoIndicador("preliminar", "1", "Não Aprovado"),
        EmissaoIndicador("preliminar", "2", "Não Aprovado"),
        EmissaoIndicador("preliminar", "3", "Não Aprovado"),
        EmissaoIndicador("original", "0", "Aprovado"),
        EmissaoIndicador("preliminar", "A1", "Não Aprovado"),
        EmissaoIndicador("preliminar", "A2", "Não Aprovado"),
    ]
    documento = _documento("aprovado", emissoes, "Não Aprovado")

    resultado = calcular_indicador_aprovacao(
        metro, metro.painel.indicadores[0], [documento]
    )

    assert resultado.geral.dentro_limite == 1
    assert resultado.geral.fora_limite == 0


def test_cancelado_nunca_entra_na_base(metro):
    documento = _documento(
        "cancelado",
        [EmissaoIndicador("preliminar", str(numero), "Não Aprovado") for numero in range(1, 6)],
        "Cancelado",
    )
    ignorado = _documento(
        "ignorado",
        [EmissaoIndicador("preliminar", "5", "Revisão Superada")],
        "Revisão Superada",
        recorte="23",
    )
    a_emitir = _documento("a_emitir", (), None, recorte="19")

    resultado = calcular_indicador_aprovacao(
        metro, metro.painel.indicadores[0], [documento, ignorado, a_emitir]
    )

    assert resultado.geral.base == 0
    assert resultado.geral.percentual is None
    assert set(resultado.por_recorte) == {"19"}
    assert all(contagem.base == 0 for contagem in resultado.por_recorte.values())


def test_base_vazia_retorna_sem_dados(metro):
    resultado = calcular_indicador_aprovacao(metro, metro.painel.indicadores[0], [])

    assert resultado.geral.base == 0
    assert resultado.geral.percentual is None


@pytest.mark.parametrize(
    ("alterar", "mensagem"),
    [
        (lambda i: i.update(limite_revisoes=0), "limite_revisoes"),
        (lambda i: i.update(meta_percentual=101), "meta_percentual"),
        (lambda i: i.update(contar_estourados_sem_aprovacao="sim"), "precisa ser booleano"),
        (lambda i: i.update(ciclos="cada_ciclo"), "ainda não suportado"),
        (lambda i: i.update(rotulo_meta=" "), "rótulo da meta"),
    ],
)
def test_validacao_dos_campos_do_indicador(alterar, mensagem):
    dados = {
        "nome": "Perfil de teste",
        "versao": "1",
        "vigencia_inicio": "2026-01-01",
        "codigo": {"segmentos": [{"nome": "codigo", "padrao_regex": "[A-Z]+"}]},
        "emissao": {"revisao": {"preliminar": "numerica", "original": "numerica"}},
        "analise": {"inicial": "INICIAL", "transicoes": {}},
        "painel": {
            "grupos": [
                {"id": "a_emitir", "rotulo": "A EMITIR", "sem_emissao": True},
                {"id": "aprovado", "rotulo": "APROVADO", "estados": ["Aprovado"]},
            ],
            "avanco": ["aprovado"],
            "indicadores": [
                {
                    "tipo": "aprovacao_em_ate_n_revisoes",
                    "id": "aprovacao",
                    "rotulo": "Aprovados no limite",
                    "limite_revisoes": 3,
                    "meta_percentual": 80,
                    "rotulo_meta": "Meta",
                    "contar_estourados_sem_aprovacao": True,
                    "ciclos": "primeira_aprovacao",
                }
            ],
        },
    }
    alterar(dados["painel"]["indicadores"][0])

    with pytest.raises(ErroPerfil, match=mensagem):
        perfil_de_dict(dados)


def test_cada_ciclo_e_recusado_com_mensagem_clara():
    dados = {
        "nome": "Perfil de teste",
        "versao": "1",
        "vigencia_inicio": "2026-01-01",
        "codigo": {"segmentos": [{"nome": "codigo", "padrao_regex": "[A-Z]+"}]},
        "emissao": {"revisao": {"preliminar": "numerica", "original": "numerica"}},
        "analise": {"inicial": "INICIAL", "transicoes": {}},
        "painel": {
            "grupos": [{"id": "a_emitir", "rotulo": "A EMITIR", "sem_emissao": True}],
            "indicadores": [
                {
                    "tipo": "aprovacao_em_ate_n_revisoes",
                    "id": "a",
                    "rotulo": "Aprovados",
                    "limite_revisoes": 3,
                    "meta_percentual": 80,
                    "rotulo_meta": "Meta",
                    "contar_estourados_sem_aprovacao": True,
                    "ciclos": "cada_ciclo",
                }
            ],
        },
    }

    with pytest.raises(ErroPerfil, match="ainda não suportado"):
        perfil_de_dict(dados)


def test_perfil_sem_indicadores_continua_valido():
    spobras = carregar_yaml(ROOT / "core" / "perfil" / "exemplos" / "spobras.yaml")

    assert spobras.painel.indicadores == ()


def test_rotulo_padrao_do_indicador_usa_o_limite_do_perfil():
    perfil = carregar_yaml(ROOT / "core" / "perfil" / "exemplos" / "metro.yaml")

    assert perfil.painel.indicadores[0].rotulo == "Aprovados até a Revisão 3"
    assert perfil.painel.indicadores[0].contar_estourados_sem_aprovacao is False


def test_rotulo_declarado_no_perfil_prevalece_sobre_o_rotulo_gerado():
    caminho = ROOT / "core" / "perfil" / "exemplos" / "metro.yaml"
    with caminho.open(encoding="utf-8") as arquivo:
        dados = yaml.safe_load(arquivo)
    dados["painel"]["indicadores"][0]["rotulo"] = "Qualidade da primeira aprovação"

    perfil = perfil_de_dict(dados)

    assert perfil.painel.indicadores[0].rotulo == "Qualidade da primeira aprovação"
