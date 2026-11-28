from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml
from django.urls import reverse
from django.utils import timezone

from acoes.services import carregar_resumo_inicio
from contas.models import Usuario
from contratos.models import Contrato, Participacao, PerfilContrato
from documentos.models import Analise, Documento, Emissao


RAIZ = Path(__file__).resolve().parents[2]
PERFIL_METRO = RAIZ / "core" / "perfil" / "exemplos" / "metro.yaml"
HOJE = date(2026, 11, 23)


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato da Minha mesa",
        codigo_interno="CT-MESA",
        cliente="Cliente de teste",
    )


@pytest.fixture
def perfil_modelo(contrato):
    with PERFIL_METRO.open(encoding="utf-8") as arquivo:
        definicao = yaml.safe_load(arquivo)
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
        username="equipe-mesa", password="senha-segura", first_name="Ana", last_name="Equipe"
    )
    Participacao.objects.create(
        usuario=pessoa,
        contrato=contrato,
        papel=Usuario.Perfil.EQUIPE,
        ativo=True,
    )
    return pessoa


def _documento(contrato, identificador, *, titulo="Documento"):
    return Documento.objects.create(
        contrato=contrato,
        identificador_base=identificador,
        titulo=titulo,
        tipo="DE",
        atributos={"tipo": "DE"},
    )


def _emissao(documento, data, *, situacao=None, data_analise=None):
    emissao = Emissao.objects.create(
        documento=documento,
        revisao="1",
        versao=1,
        fase=Emissao.Fase.PRELIMINAR,
        data_emissao=data,
        origem=Emissao.Origem.CLIENTE,
    )
    if situacao is not None:
        Analise.objects.create(
            emissao=emissao,
            etapa="Análise do cliente",
            situacao=situacao,
            origem=Analise.Origem.IMPORTADO_PW,
            data_analise=data_analise,
        )
    return emissao


def _configurar_prazos_corridos(perfil_modelo, dias=1):
    for regra in perfil_modelo.definicao["prazos"]["regras"]:
        regra.update(dias=dias, tipo_dia="corridos")
    perfil_modelo.save(update_fields=("definicao",))


def _indicadores(resumo):
    return {item["id"]: item["quantidade"] for item in resumo["indicadores_inicio"]}


@pytest.mark.django_db
def test_resumo_da_mesa_conta_acoes_documentos_em_analise_atrasos_e_aprovacoes(
    contrato, perfil_modelo, usuario
):
    _configurar_prazos_corridos(perfil_modelo)
    cliente_atrasado = _documento(
        contrato, "DE-15.25.00.00-6G6-1001", titulo="Documento atrasado"
    )
    _emissao(cliente_atrasado, HOJE - timedelta(days=10))
    cliente_em_dia = _documento(
        contrato, "DE-15.25.00.00-6G6-1002", titulo="Documento em análise"
    )
    _emissao(cliente_em_dia, HOJE)
    erro = _documento(contrato, "DE-15.25.00.00-6J2-1003")
    _emissao(erro, HOJE, situacao="Erro de Assinatura", data_analise=HOJE)
    aprovada_na_semana = _documento(contrato, "DE-15.25.00.00-6A1-1004")
    _emissao(
        aprovada_na_semana,
        HOJE - timedelta(days=10),
        situacao="Aprovado",
        data_analise=HOJE - timedelta(days=6),
    )
    aprovada_fora_da_semana = _documento(contrato, "DE-15.25.00.00-6A1-1005")
    _emissao(
        aprovada_fora_da_semana,
        HOJE - timedelta(days=20),
        situacao="Aprovado",
        data_analise=HOJE - timedelta(days=7),
    )
    nao_aprovada = _documento(contrato, "DE-15.25.00.00-6A1-1006")
    _emissao(nao_aprovada, HOJE, situacao="Não Aprovado", data_analise=HOJE)

    resumo = carregar_resumo_inicio(usuario, contrato.pk, hoje=HOJE)

    assert _indicadores(resumo) == {
        "pendencias": 4,
        "analise-cliente": 2,
        "atrasados": 1,
        "aprovados": 1,
    }
    assert resumo["documentos_analise_cliente"][0]["codigo"] == cliente_atrasado.identificador_base
    assert resumo["documentos_analise_cliente"][0]["etiqueta"].startswith("Atrasado há ")
    assert resumo["documentos_analise_cliente"][1]["etiqueta"] == "Em análise"


@pytest.mark.django_db
def test_pacote_da_mesa_usa_classe_completa_e_sinaliza_atraso_critico(
    contrato, perfil_modelo, usuario
):
    _configurar_prazos_corridos(perfil_modelo)
    documento = _documento(contrato, "DE-15.25.00.00-6G6-2001")
    _emissao(documento, HOJE - timedelta(days=100))

    resumo = carregar_resumo_inicio(usuario, contrato.pk, hoje=HOJE)

    pacote = resumo["pacotes_pendencias"][0]
    assert pacote["rotulo"] == "6G6 · Terraplenagem"
    assert pacote["quantidade"] == 1
    assert pacote["situacao"] == "Crítico"
    assert pacote["percentual"] == 100
    assert resumo["pacotes_destaque"] == [{"rotulo": "6G6 · Terraplenagem", "quantidade": 1}]


@pytest.mark.django_db
def test_faixas_do_perfil_aparecem_inclusive_com_contagem_zero(
    contrato, perfil_modelo, usuario
):
    resumo = carregar_resumo_inicio(usuario, contrato.pk, hoje=HOJE)

    assert [faixa["rotulo"] for faixa in resumo["faixas_atraso_inicio"]] == [
        "Leve",
        "Moderado",
        "Grave",
        "Crítico",
    ]
    assert [faixa["quantidade"] for faixa in resumo["faixas_atraso_inicio"]] == [0, 0, 0, 0]


@pytest.mark.django_db
def test_inicio_usa_antecedencia_de_alerta_do_perfil(contrato, perfil_modelo, usuario):
    perfil_modelo.definicao["prazos"]["regras"][0].update(dias=1, tipo_dia="corridos")
    perfil_modelo.save(update_fields=("definicao",))
    documento = _documento(contrato, "DE-15.25.00.00-6A1-9101")
    _emissao(documento, HOJE + timedelta(days=3))

    resumo_padrao = carregar_resumo_inicio(usuario, contrato.pk, hoje=HOJE)

    assert resumo_padrao["documentos_analise_cliente"] == []

    perfil_modelo.definicao["prazos"]["dias_alerta_vencimento"] = 5
    perfil_modelo.save(update_fields=("definicao",))
    resumo_configurado = carregar_resumo_inicio(usuario, contrato.pk, hoje=HOJE)

    assert [
        item["codigo"] for item in resumo_configurado["documentos_analise_cliente"]
    ] == [documento.identificador_base]


@pytest.mark.django_db
def test_atividade_recente_so_e_carregada_para_admin_do_contrato(
    contrato, perfil_modelo, usuario, django_user_model
):
    _documento(contrato, "DE-15.25.00.00-6A1-3001")
    admin = django_user_model.objects.create_user(
        username="admin-mesa", password="senha-segura", first_name="Bia", last_name="Admin"
    )
    Participacao.objects.create(
        usuario=admin,
        contrato=contrato,
        papel=Usuario.Perfil.ADMIN,
        ativo=True,
    )

    resumo_equipe = carregar_resumo_inicio(usuario, contrato.pk, hoje=HOJE)
    resumo_admin = carregar_resumo_inicio(admin, contrato.pk, hoje=HOJE)

    assert resumo_equipe["mostrar_atividade"] is False
    assert resumo_equipe["atividade_recente"] == []
    assert resumo_admin["mostrar_atividade"] is True
    assert any("3001" in evento["resumo"] for evento in resumo_admin["atividade_recente"])
    assert all("evento=" in evento["url"] for evento in resumo_admin["atividade_recente"])


@pytest.mark.django_db
def test_pagina_minha_mesa_renderiza_os_cards_do_layout(
    contrato, perfil_modelo, client, django_user_model
):
    staff = django_user_model.objects.create_user(
        username="staff-mesa", password="senha-segura", is_staff=True
    )
    client.force_login(staff)

    resposta = client.get(reverse("inicio"), {"contrato": contrato.pk})

    assert resposta.status_code == 200
    html = resposta.content.decode("utf-8")
    for titulo in (
        "Minha mesa",
        "Pendências abertas",
        "Em análise do cliente",
        "Atrasados",
        "Aprovados na semana",
        "Pendências por pacote",
        "Atraso por faixa",
        "Análise do cliente",
        "Pacotes em destaque",
        "Atividade recente",
        "Mensagens / Integrações",
        "Ações rápidas",
    ):
        assert titulo in html
    assert "Importar situação PW" in html
    assert (
        f'href="{reverse("acoes:pendencias")}?contrato={contrato.pk}#janela-titulo-diferente-id">'
        "Título diferente do ID: 0</a>"
    ) in html


@pytest.mark.django_db
def test_inicio_mostra_a_contagem_de_prazos_dentro_da_antecedencia(
    contrato, perfil_modelo, usuario, client
):
    _configurar_prazos_corridos(perfil_modelo, dias=1)
    perfil_modelo.definicao["prazos"]["dias_alerta_vencimento"] = 3
    perfil_modelo.save(update_fields=("definicao",))
    client.force_login(usuario)

    sem_prazos_proximos = client.get(reverse("inicio"), {"contrato": contrato.pk})
    assert "Nenhum prazo vence nos próximos 3 dias." in sem_prazos_proximos.content.decode("utf-8")

    documento = _documento(contrato, "DE-15.25.00.00-6A1-8101")
    _emissao(documento, timezone.localdate())
    com_prazo_proximo = client.get(reverse("inicio"), {"contrato": contrato.pk})
    html = com_prazo_proximo.content.decode("utf-8")

    assert "Vencem nos próximos 3 dias: 1" in html
    assert (
        f'href="{reverse("acoes:pendencias")}?contrato={contrato.pk}#janela-analise-cliente">Ver prazos</a>'
        in html
    )
