from datetime import date, datetime
from pathlib import Path

import pytest
import yaml
from django.urls import reverse
from django.utils import timezone

from contas.models import Usuario
from contratos.models import Contrato, Participacao, PerfilContrato
from documentos.models import Analise, Documento, Emissao
from documentos.servicos import carregar_lista_mestra


PERFIL_METRO = Path(__file__).resolve().parents[2] / "core" / "perfil" / "exemplos" / "metro.yaml"


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato da Lista Mestra",
        codigo_interno="CT-LM68",
        cliente="Cliente de teste",
    )


@pytest.fixture
def perfil_modelo(contrato):
    with PERFIL_METRO.open(encoding="utf-8") as arquivo:
        definicao = _json_compatibility(yaml.safe_load(arquivo))
    definicao["vigencia_inicio"] = "2020-01-01"
    return PerfilContrato.objects.create(
        contrato=contrato,
        versao=1,
        vigencia_inicio=date(2020, 1, 1),
        definicao=definicao,
    )


@pytest.fixture
def usuario(contrato, django_user_model):
    pessoa = django_user_model.objects.create_user(
        username="gestor-lista-mestra",
        password="senha-segura",
        first_name="Ana",
        last_name="Gestora",
    )
    Participacao.objects.create(
        usuario=pessoa,
        contrato=contrato,
        papel=Usuario.Perfil.EQUIPE,
        ativo=True,
    )
    return pessoa


def _json_compatibility(valor):
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {chave: _json_compatibility(item) for chave, item in valor.items()}
    if isinstance(valor, list):
        return [_json_compatibility(item) for item in valor]
    return valor


def _documento(contrato, codigo, titulo, disciplina):
    tipo = codigo.split("-", 1)[0]
    return Documento.objects.create(
        contrato=contrato,
        identificador_base=codigo,
        tipo=tipo,
        titulo=titulo,
        disciplina=disciplina,
        atributos={
            "tipo": tipo,
            "linha": "15",
            "trecho": "25",
            "subtrecho": "00",
            "unidade": "00",
            "etapa": "6",
            "classe": "A1",
            "sequencial": codigo.rsplit("-", 1)[-1],
        },
    )


def _emissao(
    documento,
    revisao,
    data_emissao,
    *,
    fase=Emissao.Fase.PRELIMINAR,
    versao=1,
    situacao=None,
    data_analise=None,
    retorno="",
    observacao="",
):
    emissao = Emissao.objects.create(
        documento=documento,
        revisao=revisao,
        versao=versao,
        fase=fase,
        data_emissao=data_emissao,
        origem=Emissao.Origem.CLIENTE,
        observacao=observacao,
    )
    if situacao:
        Analise.objects.create(
            emissao=emissao,
            etapa="Análise do cliente",
            situacao=situacao,
            origem=Analise.Origem.IMPORTADO_PW,
            data_analise=data_analise,
            documento_retorno=retorno,
            observacao="Observação da análise",
        )
    return emissao


@pytest.fixture
def dados_emissoes(contrato, perfil_modelo):
    desenho = _documento(
        contrato,
        "DE-15.25.00.00-6A1-1001",
        "Projeto da estação Norte",
        "P7",
    )
    primeira = _emissao(desenho, "1", date(2026, 1, 5), observacao="Nota da emissão")
    segunda = _emissao(
        desenho,
        "2",
        date(2026, 2, 5),
        fase=Emissao.Fase.ORIGINAL,
        situacao="Em análise",
        data_analise=date(2026, 2, 10),
        retorno="RV-22",
    )
    Analise.objects.create(
        emissao=segunda,
        etapa="Análise anterior",
        situacao="Não aprovado",
        origem=Analise.Origem.MANUAL,
        data_analise=date(2026, 2, 8),
        documento_retorno="RV-21",
    )
    memorial = _documento(
        contrato,
        "MC-15.25.00.00-6A1-1002",
        "Memorial da estação Sul",
        "A7",
    )
    terceira = _emissao(
        memorial,
        "1",
        date(2026, 1, 15),
        situacao="Reprovado",
        data_analise=date(2026, 1, 20),
        retorno="IT-17",
    )
    cancelado = _documento(
        contrato,
        "DE-15.25.00.00-6A1-1003",
        "Documento cancelado",
        "P7",
    )
    cancelado.cancelado_em = timezone.now()
    cancelado.save(update_fields=("cancelado_em",))
    quarta = _emissao(cancelado, "1", date(2026, 3, 2))
    return {
        "desenho": desenho,
        "memorial": memorial,
        "cancelado": cancelado,
        "primeira": primeira,
        "segunda": segunda,
        "terceira": terceira,
        "quarta": quarta,
    }


@pytest.mark.django_db
def test_lista_mestra_tem_uma_linha_por_emissao_e_rotulo_cronologico(
    contrato, perfil_modelo, usuario, dados_emissoes
):
    dados = carregar_lista_mestra(usuario, contrato.pk)
    linhas = dados["pagina"].object_list

    assert len(linhas) == 3
    do_desenho = [linha for linha in linhas if linha["documento"] == dados_emissoes["desenho"]]
    assert [linha["emissao"].pk for linha in do_desenho] == [
        dados_emissoes["primeira"].pk,
        dados_emissoes["segunda"].pk,
    ]
    assert [linha["rotulo_cronologico"] for linha in do_desenho] == [
        "Emissão Inicial",
        "Revisão 1",
    ]
    nomes_segmentos = [campo.nome for campo in dados["segmentos_codigo"]]
    valores_segmentos = dict(zip(nomes_segmentos, do_desenho[0]["segmentos"]))
    assert {"tipo", "trecho", "classe"}.issubset(nomes_segmentos)
    assert valores_segmentos["tipo"] == "DE"
    assert valores_segmentos["trecho"] == "25"
    assert do_desenho[0]["situacao"] == "Em análise"
    assert do_desenho[0]["data_analise"] is None
    assert do_desenho[1]["situacao"] == "Em análise"
    assert do_desenho[1]["data_analise"] == date(2026, 2, 10)
    assert do_desenho[1]["documento_retorno"] == "RV-22"
    assert do_desenho[1]["observacao"] == "Observação da análise"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("parametro", "valor", "codigo_esperado"),
    [
        ("q", "estação Sul", "MC-15.25.00.00-6A1-1002"),
        ("q", "1001", "DE-15.25.00.00-6A1-1001"),
        ("tipo", "MC", "MC-15.25.00.00-6A1-1002"),
        ("disciplina", "A7", "MC-15.25.00.00-6A1-1002"),
        ("fase", Emissao.Fase.ORIGINAL, "DE-15.25.00.00-6A1-1001"),
        ("situacao", "Reprovado", "MC-15.25.00.00-6A1-1002"),
    ],
)
def test_lista_mestra_busca_e_filtra_por_get(
    client, contrato, perfil_modelo, usuario, dados_emissoes, parametro, valor, codigo_esperado
):
    client.force_login(usuario)

    resposta = client.get(
        reverse("lista_mestra"),
        {"contrato": contrato.pk, parametro: valor},
    )

    assert resposta.status_code == 200
    assert codigo_esperado in resposta.content.decode()
    linhas = resposta.context["pagina"].object_list
    assert linhas
    assert {linha["codigo"] for linha in linhas} == {codigo_esperado}


@pytest.mark.django_db
def test_lista_mestra_oculta_cancelados_ate_a_caixa_ser_marcada(
    client, contrato, perfil_modelo, usuario, dados_emissoes
):
    client.force_login(usuario)

    resposta_padrao = client.get(reverse("lista_mestra"), {"contrato": contrato.pk})
    resposta_cancelados = client.get(
        reverse("lista_mestra"),
        {"contrato": contrato.pk, "mostrar_cancelados": "1"},
    )

    assert resposta_padrao.context["total_filtrado"] == 3
    assert resposta_cancelados.context["total_filtrado"] == 4
    assert dados_emissoes["cancelado"].identificador_base not in resposta_padrao.content.decode()
    assert dados_emissoes["cancelado"].identificador_base in resposta_cancelados.content.decode()


@pytest.mark.django_db
def test_lista_mestra_exige_participacao_no_contrato(
    client, contrato, perfil_modelo, django_user_model
):
    externo = django_user_model.objects.create_user(username="sem-participacao", password="senha")
    client.force_login(externo)

    resposta = client.get(reverse("lista_mestra"), {"contrato": contrato.pk})

    assert resposta.status_code == 403


@pytest.mark.django_db
def test_lista_mestra_limita_consultas_com_varias_emissoes(
    client, contrato, perfil_modelo, usuario, dados_emissoes, django_assert_max_num_queries
):
    client.force_login(usuario)

    with django_assert_max_num_queries(13):
        resposta = client.get(reverse("lista_mestra"), {"contrato": contrato.pk})

    assert resposta.status_code == 200
