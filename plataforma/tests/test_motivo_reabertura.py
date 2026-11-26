from datetime import date
from pathlib import Path

import pytest
import yaml
from django.urls import reverse

from contas.models import Usuario
from contratos.models import Contrato, Participacao, PerfilContrato
from documentos.models import Documento, Emissao
from documentos.servicos import (
    atualizar_motivo_reabertura,
    carregar_pasta_documento,
    listar_reaberturas_do_contrato,
)


PERFIL_METRO = Path(__file__).resolve().parents[2] / "core" / "perfil" / "exemplos" / "metro.yaml"


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato de teste",
        codigo_interno="CT-REAB",
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
def equipe(contrato, django_user_model):
    usuario = django_user_model.objects.create_user(username="equipe-reabertura", password="senha")
    Participacao.objects.create(
        usuario=usuario,
        contrato=contrato,
        papel=Usuario.Perfil.EQUIPE,
        ativo=True,
    )
    return usuario


@pytest.fixture
def emissoes_reabertura(contrato, perfil_modelo):
    documento = Documento.objects.create(
        contrato=contrato,
        identificador_base="DE-15.25.00.00-6P7-1200",
        titulo="Documento aprovado e reaberto",
        tipo="DE",
        disciplina="P7",
        atributos={"tipo": "DE", "classe": "P7"},
    )
    emissoes = []
    for revisao, fase, data_emissao in (
        ("0", Emissao.Fase.ORIGINAL, date(2026, 1, 1)),
        ("A1", Emissao.Fase.PRELIMINAR, date(2026, 2, 1)),
        ("A2", Emissao.Fase.PRELIMINAR, date(2026, 2, 10)),
    ):
        emissoes.append(
            Emissao.objects.create(
                documento=documento,
                revisao=revisao,
                versao=1,
                fase=fase,
                data_emissao=data_emissao,
                origem=Emissao.Origem.CLIENTE,
            )
        )
    return documento, emissoes


@pytest.mark.django_db
def test_motivo_fica_gravado_apenas_na_primeira_emissao_da_reabertura(
    contrato, emissoes_reabertura, equipe
):
    documento, (original, a1, a2) = emissoes_reabertura

    atualizar_motivo_reabertura(
        equipe, contrato.pk, documento.pk, a1.pk, Emissao.MotivoReabertura.CAMPO
    )

    a1.refresh_from_db()
    a2.refresh_from_db()
    assert a1.motivo_reabertura == Emissao.MotivoReabertura.CAMPO
    assert a2.motivo_reabertura == ""


@pytest.mark.django_db
def test_a2_exibe_o_motivo_gravado_em_a1(contrato, emissoes_reabertura, equipe):
    documento, (original, a1, a2) = emissoes_reabertura
    atualizar_motivo_reabertura(
        equipe, contrato.pk, documento.pk, a1.pk, Emissao.MotivoReabertura.PROJETO
    )

    pasta = carregar_pasta_documento(equipe, contrato.pk, documento.pk, hoje=date(2026, 2, 11))
    item_a2 = next(item for item in pasta["linha_tempo"] if item["emissao"].pk == a2.pk)

    assert item_a2["motivo"] == Emissao.MotivoReabertura.PROJETO
    assert item_a2["motivo_rotulo"] == "Erro de projeto"
    assert item_a2["motivo_editavel"] is False


@pytest.mark.django_db
def test_visualizador_ve_motivo_sem_seletor(
    client, contrato, emissoes_reabertura, django_user_model, perfil_modelo
):
    documento, (original, a1, a2) = emissoes_reabertura
    visualizador = django_user_model.objects.create_user(username="chefia-reabertura", password="senha")
    Participacao.objects.create(
        usuario=visualizador,
        contrato=contrato,
        papel=Usuario.Perfil.CHEFIA,
        ativo=True,
    )
    equipe = django_user_model.objects.create_user(username="equipe-edita", password="senha")
    Participacao.objects.create(
        usuario=equipe,
        contrato=contrato,
        papel=Usuario.Perfil.EQUIPE,
        ativo=True,
    )
    atualizar_motivo_reabertura(
        equipe, contrato.pk, documento.pk, a1.pk, Emissao.MotivoReabertura.CLIENTE
    )
    client.force_login(visualizador)

    resposta = client.get(reverse("documento_pasta", args=(contrato.pk, documento.pk)))

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Pedido do cliente" in html
    assert 'name="motivo_reabertura"' not in html
    assert "Salvar motivo" not in html


@pytest.mark.django_db
def test_valor_fora_da_lista_e_recusado(contrato, emissoes_reabertura, equipe):
    documento, (original, a1, a2) = emissoes_reabertura

    with pytest.raises(ValueError, match="lista"):
        atualizar_motivo_reabertura(
            equipe, contrato.pk, documento.pk, a1.pk, "motivo-inventado"
        )


@pytest.mark.django_db
def test_emissao_que_nao_e_reabertura_nao_aceita_motivo(
    contrato, emissoes_reabertura, equipe
):
    documento, (original, a1, a2) = emissoes_reabertura

    with pytest.raises(ValueError, match="primeira emissão de uma reabertura"):
        atualizar_motivo_reabertura(
            equipe, contrato.pk, documento.pk, original.pk, Emissao.MotivoReabertura.CAMPO
        )


@pytest.mark.django_db
def test_listar_reaberturas_do_contrato_eh_somente_leitura_e_retorna_motivo(
    contrato, emissoes_reabertura, equipe
):
    documento, (original, a1, a2) = emissoes_reabertura
    atualizar_motivo_reabertura(
        equipe,
        contrato.pk,
        documento.pk,
        a1.pk,
        Emissao.MotivoReabertura.OUTRO,
        "Interferência com rede existente",
    )
    historico_antes = a1.history.count()

    reaberturas = listar_reaberturas_do_contrato(contrato, hoje=date(2026, 2, 11))

    assert len(reaberturas) == 1
    assert reaberturas[0]["documento"] == documento
    assert reaberturas[0]["serie"] == "A"
    assert reaberturas[0]["revisoes"] == ("A1", "A2")
    assert reaberturas[0]["motivo"] == Emissao.MotivoReabertura.OUTRO
    assert reaberturas[0]["motivo_rotulo"] == "Outro"
    assert reaberturas[0]["motivo_obs"] == "Interferência com rede existente"
    assert a1.history.count() == historico_antes


@pytest.mark.django_db
def test_post_atualiza_motivo_e_registra_historico_e_confirmacao(
    client, contrato, emissoes_reabertura, equipe
):
    documento, (original, a1, a2) = emissoes_reabertura
    client.force_login(equipe)

    resposta = client.post(
        reverse("documento_pasta", args=(contrato.pk, documento.pk)),
        {
            "emissao": a1.pk,
            "motivo_reabertura": Emissao.MotivoReabertura.CAMPO,
            "motivo_reabertura_obs": "",
        },
    )

    assert resposta.status_code == 302
    a1.refresh_from_db()
    assert a1.motivo_reabertura == Emissao.MotivoReabertura.CAMPO
    assert a1.history.count() == 2
    pagina = client.get(resposta.url)
    assert "Motivo da reabertura atualizado." in pagina.content.decode()
