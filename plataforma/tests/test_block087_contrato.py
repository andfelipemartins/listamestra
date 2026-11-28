from datetime import timedelta
import json
from pathlib import Path

import pytest
import yaml
from django.urls import reverse
from django.utils import timezone

from contas.models import Usuario
from contratos.models import (
    Contrato,
    DiaNaoUtilContrato,
    EscopoContrato,
    Participacao,
    PerfilContrato,
)
from core.perfil import escopo_do_documento, perfil_de_dict
from documentos.models import Documento


RAIZ = Path(__file__).resolve().parents[2]
PERFIL_METRO = RAIZ / "core" / "perfil" / "exemplos" / "metro.yaml"


def _definicao_metro():
    return json.loads(
        json.dumps(
            yaml.safe_load(PERFIL_METRO.read_text(encoding="utf-8")),
            default=lambda valor: valor.isoformat(),
        )
    )


@pytest.fixture
def contrato_configuravel(db):
    contrato = Contrato.objects.create(
        nome="Contrato Block 087",
        codigo_interno="CT-B087",
        cliente="Cliente de teste",
        regiao_uf="SP",
        regiao_municipio="São Paulo",
    )
    PerfilContrato.objects.create(
        contrato=contrato,
        versao=1,
        vigencia_inicio=timezone.localdate() - timedelta(days=30),
        definicao=_definicao_metro(),
    )
    return contrato


@pytest.fixture
def staff_b087(django_user_model):
    return django_user_model.objects.create_user(
        username="staff-b087",
        password="senha-segura",
        is_staff=True,
    )


@pytest.fixture
def participante_b087(django_user_model):
    return django_user_model.objects.create_user(
        username="participante-b087",
        password="senha-segura",
        first_name="Paula",
        last_name="Silva",
    )


@pytest.mark.django_db
def test_detalhe_apresenta_quatro_secoes_e_respeita_participacao(
    client, staff_b087, participante_b087, contrato_configuravel
):
    contrato = contrato_configuravel
    Participacao.objects.create(
        contrato=contrato,
        usuario=participante_b087,
        papel=Usuario.Perfil.EQUIPE,
        funcao="Engenheira",
    )
    client.force_login(staff_b087)

    resposta_staff = client.get(reverse("contrato_detalhe", args=(contrato.pk,)))

    assert resposta_staff.status_code == 200
    conteudo = resposta_staff.content.decode("utf-8")
    assert all(texto in conteudo for texto in ("Dados", "Participantes", "Calendário", "Escopos e classes"))
    assert resposta_staff.context["pode_editar"] is True
    assert "Adicionar participante" in conteudo

    client.force_login(participante_b087)
    resposta_participante = client.get(reverse("contrato_detalhe", args=(contrato.pk,)))

    assert resposta_participante.status_code == 200
    assert resposta_participante.context["pode_editar"] is False
    assert "Engenheira" in resposta_participante.content.decode("utf-8")
    assert "Adicionar participante" not in resposta_participante.content.decode("utf-8")

    outro = Usuario.objects.create_user(username="fora-b087", password="senha-segura")
    client.force_login(outro)
    assert client.get(reverse("contrato_detalhe", args=(contrato.pk,))).status_code == 403


@pytest.mark.django_db
def test_lista_abre_contrato_e_admin_do_contrato_edita_regiao(
    client, staff_b087, django_user_model, contrato_configuravel
):
    contrato = contrato_configuravel
    admin_contrato = django_user_model.objects.create_user(
        username="admin-contrato-b087",
        password="senha-segura",
    )
    Participacao.objects.create(
        contrato=contrato,
        usuario=admin_contrato,
        papel=Usuario.Perfil.ADMIN,
    )

    client.force_login(staff_b087)
    resposta_lista = client.get(reverse("contratos_lista"))
    assert resposta_lista.status_code == 200
    assert "Abrir" in resposta_lista.content.decode("utf-8")
    assert reverse("contrato_detalhe", args=(contrato.pk,)) in resposta_lista.content.decode("utf-8")

    client.force_login(admin_contrato)
    resposta_detalhe = client.get(reverse("contrato_detalhe", args=(contrato.pk,)))
    assert resposta_detalhe.status_code == 200
    assert resposta_detalhe.context["pode_editar"] is True
    resposta_salvar = client.post(
        reverse("contrato_detalhe", args=(contrato.pk,)),
        {
            "acao": "dados",
            "codigo_interno": "CT-B087-ATUALIZADO",
            "nome": "Contrato revisado",
            "cliente": "Cliente revisado",
            "regiao_uf": "SP",
            "regiao_municipio": "São Paulo",
            "ativo": "on",
        },
    )

    assert resposta_salvar.status_code == 302
    contrato.refresh_from_db()
    perfil = PerfilContrato.objects.get(contrato=contrato, versao=1)
    assert (contrato.codigo_interno, contrato.nome, contrato.cliente) == (
        "CT-B087-ATUALIZADO",
        "Contrato revisado",
        "Cliente revisado",
    )
    assert (contrato.regiao_uf, contrato.regiao_municipio) == ("SP", "São Paulo")
    assert perfil.definicao["prazos"]["feriados"]["regiao"] == {
        "uf": "SP",
        "municipio": "São Paulo",
    }


@pytest.mark.django_db
def test_staff_adiciona_altera_e_desativa_participante(
    client, staff_b087, participante_b087, contrato_configuravel
):
    contrato = contrato_configuravel
    client.force_login(staff_b087)

    resposta = client.post(
        reverse("contrato_detalhe", args=(contrato.pk,)),
        {
            "acao": "adicionar_participante",
            "usuario": participante_b087.pk,
            "papel": Usuario.Perfil.EQUIPE,
            "funcao": "Engenheira de projeto",
        },
    )
    assert resposta.status_code == 302
    participacao = Participacao.objects.get(contrato=contrato, usuario=participante_b087)
    assert (participacao.papel, participacao.funcao, participacao.ativo) == (
        Usuario.Perfil.EQUIPE,
        "Engenheira de projeto",
        True,
    )

    resposta = client.post(
        reverse("contrato_detalhe", args=(contrato.pk,)),
        {
            "acao": "editar_participante",
            "participacao_id": participacao.pk,
            "papel": Usuario.Perfil.CHEFIA,
            "funcao": "Coordenação",
        },
    )
    assert resposta.status_code == 302
    participacao.refresh_from_db()
    assert (participacao.papel, participacao.funcao) == (Usuario.Perfil.CHEFIA, "Coordenação")

    resposta = client.post(
        reverse("contrato_detalhe", args=(contrato.pk,)),
        {"acao": "desativar_participante", "participacao_id": participacao.pk},
    )
    assert resposta.status_code == 302
    participacao.refresh_from_db()
    assert participacao.ativo is False


@pytest.mark.django_db
def test_calendario_mostra_feriado_regional_e_salva_dia_manual(
    client, staff_b087, contrato_configuravel
):
    contrato = contrato_configuravel
    client.force_login(staff_b087)
    url = reverse("contrato_detalhe", args=(contrato.pk,))

    resposta = client.get(url, {"ano": 2026, "mes": 1})

    assert resposta.status_code == 200
    assert "Aniversário de São Paulo" in resposta.content.decode("utf-8")
    data_manual = "2026-01-27"
    resposta = client.post(
        url,
        {"acao": "salvar_dia", "data": data_manual, "descricao": "Parada da obra"},
    )

    assert resposta.status_code == 302
    assert DiaNaoUtilContrato.objects.get(contrato=contrato).descricao == "Parada da obra"
    resposta = client.get(url, {"ano": 2026, "mes": 1})
    assert "Parada da obra" in resposta.content.decode("utf-8")


@pytest.mark.django_db
def test_escopo_por_classe_atualiza_classificacao_do_documento(
    client, staff_b087, contrato_configuravel
):
    contrato = contrato_configuravel
    client.force_login(staff_b087)
    url = reverse("contrato_detalhe", args=(contrato.pk,))
    resposta = client.post(
        url,
        {"acao": "adicionar_escopo", "nome": "Instalações", "classes": "U1"},
    )

    assert resposta.status_code == 302
    escopo = EscopoContrato.objects.get(contrato=contrato, nome="Instalações")
    documento = Documento.objects.create(
        contrato=contrato,
        identificador_base="DOC-U1-B087",
        tipo="DE",
        disciplina="U1",
        atributos={"classe": "U1", "tipo": "DE"},
    )
    perfil_db = PerfilContrato.objects.get(contrato=contrato, versao=1)

    assert escopo_do_documento(
        perfil_de_dict(perfil_db.definicao),
        documento.atributos["classe"],
        documento.atributos["tipo"],
    ) == "Instalações"
    perfil_classificado = perfil_de_dict(perfil_db.definicao)
    assert escopo_do_documento(perfil_classificado, "A9", "MQ") == "Qualidade"
    assert escopo_do_documento(perfil_classificado, "A9", "DE") == "Arquitetura e Civil"

    resposta = client.post(
        url,
        {
            "acao": "editar_escopo",
            "escopo_id": escopo.pk,
            "nome": "Instalações",
            "classes": "",
        },
    )

    assert resposta.status_code == 302
    escopo.refresh_from_db()
    perfil_db.refresh_from_db()
    assert escopo.classes == []
    assert escopo_do_documento(
        perfil_de_dict(perfil_db.definicao),
        documento.atributos["classe"],
        documento.atributos["tipo"],
    ) is None
