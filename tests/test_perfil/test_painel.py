from pathlib import Path

import pytest

from core.perfil.modelo import ErroPerfil, carregar_yaml, perfil_de_dict
from core.perfil.painel import (
    classificar,
    classificar_categoria,
    resolver_situacao_oculta,
    resumir,
)


ROOT = Path(__file__).parents[2]


@pytest.fixture
def metro():
    return carregar_yaml(ROOT / "core" / "perfil" / "exemplos" / "metro.yaml")


def _perfil_base(painel=None):
    dados = {
        "nome": "Perfil de teste",
        "versao": "1",
        "vigencia_inicio": "2026-01-01",
        "codigo": {"segmentos": [{"nome": "codigo", "padrao_regex": "[A-Z]+"}]},
        "emissao": {
            "revisao": {"preliminar": "letras", "original": "numerica"}
        },
        "analise": {"inicial": "INICIAL", "transicoes": {}},
    }
    if painel is not None:
        dados["painel"] = painel
    return dados


@pytest.mark.parametrize(
    ("situacao", "grupo"),
    [
        (None, "a_emitir"),
        ("Em Desenvolvimento", "erro"),
        ("Em Análise", "em_analise"),
        ("Para Aprovação", "aprovado"),
        ("Em coleta de Assinaturas", "aprovado"),
        ("Aprovado", "aprovado"),
        ("Não Aprovado", "nao_aprovado"),
        ("Não Conforme", "inconsistente"),
        ("Inconsistente", "inconsistente"),
        ("Erro de Assinatura", "erro"),
        ("Cancelado", "cancelado"),
        ("Revisão Superada", "ignorado"),
    ],
)
def test_classifica_situacoes_reais_do_metro(metro, situacao, grupo):
    assert classificar(metro, situacao).id == grupo


def test_classificacao_ignora_maiusculas_acentos_e_espacos_extras(metro):
    assert classificar(metro, "  nao   aprovado  ").id == "nao_aprovado"


def test_situacao_oculta_usa_ultima_situacao_anterior_valida(metro):
    situacao = resolver_situacao_oculta(
        metro, ["Erro de Assinatura", "Não Aprovado", "Em Análise"]
    )

    assert situacao == "Não Aprovado"
    assert classificar(metro, situacao).id == "nao_aprovado"


def test_situacao_oculta_sem_anterior_volta_ao_estado_inicial(metro):
    situacao = resolver_situacao_oculta(metro, ["Em Desenvolvimento"])

    assert situacao == metro.analise.inicial
    assert classificar(metro, situacao).id == "em_analise"


def test_situacao_oculta_pula_estados_ignorados(metro):
    situacao = resolver_situacao_oculta(
        metro, ["Em Desenvolvimento", "Revisão Superada", "Aprovado"]
    )

    assert situacao == "Aprovado"


def test_estado_desconhecido_vai_para_grupo_nao_mapeado(metro):
    grupo = classificar(metro, "Aguardando validação local")

    assert (grupo.id, grupo.rotulo) == ("nao_mapeado", "NÃO MAPEADO")


def test_resumo_conta_grupos_e_calcula_avanco_excluindo_cancelados_e_ignorados(metro):
    resumo = resumir(
        metro,
        [
            None,
            "Aprovado",
            "Em Análise",
            "Cancelado",
            "Não Aprovado",
            "Erro de Assinatura",
            "Revisão Superada",
        ],
    )

    assert list(resumo.contagens) == [
        "a_emitir",
        "em_analise",
        "aprovado",
        "nao_aprovado",
        "inconsistente",
        "cancelado",
        "nao_mapeado",
    ]
    assert resumo.contagens == {
        "a_emitir": 1,
        "em_analise": 2,
        "aprovado": 1,
        "nao_aprovado": 1,
        "inconsistente": 0,
        "cancelado": 1,
        "nao_mapeado": 0,
    }
    assert resumo.total_previsto == 6
    assert resumo.percentual_avanco == pytest.approx(20.0)
    assert resumo.estados_nao_mapeados == ()


def test_resumo_lista_situacoes_nao_mapeadas_com_contagem_normalizada(metro):
    resumo = resumir(metro, ["Novo Estado", " novo   estado ", "Outra situação"])

    assert resumo.contagens["nao_mapeado"] == 3
    assert [(item.situacao, item.contagem) for item in resumo.estados_nao_mapeados] == [
        ("Novo Estado", 2),
        ("Outra situação", 1),
    ]


@pytest.mark.parametrize(
    ("alterar", "mensagem"),
    [
        (
            lambda p: p["grupos"].extend(
                [
                    {"id": "um", "rotulo": "Um", "estados": ["Situação"]},
                    {"id": "dois", "rotulo": "Dois", "estados": [" SITUACAO "]},
                ]
            ),
            "aparece em mais de um grupo",
        ),
        (
            lambda p: p["grupos"][0].pop("sem_emissao"),
            "sem_emissao: true",
        ),
        (
            lambda p: p["grupos"].append({"id": "a_emitir", "rotulo": "Duplicado"}),
            "Id de grupo repetido",
        ),
        (
            lambda p: p["grupos"][0].update(oculto_no_painel="sim"),
            "oculto_no_painel.*booleano",
        ),
        (
            lambda p: p.update(avanco=["fantasma"]),
            "grupo inexistente",
        ),
    ],
)
def test_validacoes_negativas_do_painel(alterar, mensagem):
    painel = {
        "grupos": [
            {"id": "a_emitir", "rotulo": "A EMITIR", "sem_emissao": True},
            {"id": "aprovado", "rotulo": "APROVADO", "estados": ["Aprovado"]},
        ],
        "avanco": ["aprovado"],
    }
    alterar(painel)

    with pytest.raises(ErroPerfil, match=mensagem):
        perfil_de_dict(_perfil_base(painel))


def test_perfil_sem_painel_recebe_estrutura_minima_sem_estados_de_cliente():
    perfil = perfil_de_dict(_perfil_base())

    assert [(grupo.id, grupo.rotulo) for grupo in perfil.painel.grupos] == [
        ("a_emitir", "A EMITIR"),
        ("em_analise", "EM ANÁLISE"),
        ("outros", "OUTROS"),
    ]
    assert classificar(perfil, None).id == "a_emitir"
    assert classificar(perfil, "Em Análise").id == "nao_mapeado"


def test_painel_spobras_usa_situacoes_do_manual():
    spobras = carregar_yaml(ROOT / "core" / "perfil" / "exemplos" / "spobras.yaml")

    assert classificar(spobras, "ENTREGUE").id == "em_analise"
    assert classificar(spobras, "LIBERADO PARA ANÁLISE").id == "em_analise"
    assert classificar(spobras, "APROVADO COM RESSALVAS").id == "aprovado"
    assert classificar(spobras, "A REVISAR").id == "nao_aprovado"
    assert classificar(spobras, "CANCELADO").id == "cancelado"
    assert all(not grupo.oculto_no_painel for grupo in spobras.painel.grupos)
    assert spobras.painel.categorias == ()


def _perfil_com_categorias(categorias):
    dados = _perfil_base(
        {
            "grupos": [
                {"id": "a_emitir", "rotulo": "A EMITIR", "sem_emissao": True},
            ],
            "categorias": categorias,
        }
    )
    dados["codigo"]["segmentos"] = [
        {"nome": "tipo", "padrao_regex": "[A-Z]+"},
        {"nome": "classe_subclasse", "padrao_regex": "[A-Z][0-9]"},
    ]
    return perfil_de_dict(dados)


def test_categoria_usa_primeira_regra_e_sigla_precede_classe():
    perfil = _perfil_com_categorias(
        [
            {
                "id": "qualidade",
                "rotulo": "QUALIDADE",
                "regras": [
                    {"tipo": ["PE", "MQ"]},
                    {"classe_subclasse": ["A7"]},
                ],
            },
            {"id": "arquitetura", "rotulo": "ARQUITETURA", "regras": [{"classe_subclasse": ["B3", "B7", "N3"]}]},
            {"id": "sistemas", "rotulo": "SISTEMAS", "regras": [{"classe_subclasse": ["P7"]}]},
            {"id": "civil", "rotulo": "CIVIL", "padrao": True},
        ]
    )

    assert classificar_categoria(perfil, {"tipo": "PE", "classe_subclasse": "B3"}).id == "qualidade"
    assert classificar_categoria(perfil, {"tipo": "DE", "classe_subclasse": "A7"}).id == "qualidade"
    assert classificar_categoria(perfil, {"tipo": "DE", "classe_subclasse": "N3"}).id == "arquitetura"
    assert classificar_categoria(perfil, {"tipo": "DE", "classe_subclasse": "P7"}).id == "sistemas"
    assert classificar_categoria(perfil, {"tipo": "DE", "classe_subclasse": "C1"}).id == "civil"


def test_categoria_sem_padrao_retorna_none_para_outros():
    perfil = _perfil_com_categorias(
        [{"id": "qualidade", "rotulo": "QUALIDADE", "regras": [{"tipo": ["PE"]}]}]
    )

    assert classificar_categoria(perfil, {"tipo": "DE", "classe_subclasse": "C1"}) is None


@pytest.mark.parametrize(
    ("categorias", "mensagem"),
    [
        (
            [
                {"id": "civil", "rotulo": "Civil", "regras": []},
                {"id": "CIVIL", "rotulo": "Outro", "regras": []},
            ],
            "Id de categoria repetido",
        ),
        (
            [{"id": "civil", "rotulo": "Civil", "regras": [{"classe": ["A1"]}]}],
            "caixa inexistente",
        ),
        (
            [
                {"id": "civil", "rotulo": "Civil", "regras": [], "padrao": True},
                {"id": "sistemas", "rotulo": "Sistemas", "regras": [], "padrao": True},
            ],
            "mais de uma categoria",
        ),
    ],
)
def test_validacoes_de_categorias(categorias, mensagem):
    with pytest.raises(ErroPerfil, match=mensagem):
        _perfil_com_categorias(categorias)
