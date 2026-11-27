from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from contas.models import Usuario
from contratos.models import Contrato, Participacao, PerfilContrato
from documentos.models import Documento
from contratos.servicos import listar_contratos


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato Beta",
        codigo_interno="CT-BETA",
        cliente="Cliente Beta",
    )


@pytest.fixture
def staff(django_user_model):
    return django_user_model.objects.create_user(
        username="staff-b072",
        password="senha-segura",
        is_staff=True,
    )


@pytest.fixture
def pessoa(django_user_model):
    return django_user_model.objects.create_user(
        username="pessoa-b072",
        password="senha-segura",
        first_name="Paula",
        last_name="Silva",
    )


@pytest.mark.django_db
def test_staff_ve_contratos_contagens_perfil_links_e_inativo(client, staff, contrato):
    inativo = Contrato.objects.create(
        nome="Contrato Alfa",
        codigo_interno="CT-ALFA",
        cliente="Cliente Alfa",
        ativo=False,
    )
    PerfilContrato.objects.create(
        contrato=contrato,
        versao=1,
        vigencia_inicio=timezone.localdate() - timedelta(days=10),
        definicao={"nome": "Perfil Beta"},
    )
    PerfilContrato.objects.create(
        contrato=contrato,
        versao=2,
        vigencia_inicio=timezone.localdate() + timedelta(days=10),
        definicao={"nome": "Perfil futuro"},
    )
    admin = Usuario.objects.create_user(username="admin-b072", password="senha-segura")
    equipe_1 = Usuario.objects.create_user(username="equipe-1-b072", password="senha-segura")
    equipe_2 = Usuario.objects.create_user(username="equipe-2-b072", password="senha-segura")
    chefia_inativa = Usuario.objects.create_user(
        username="chefia-inativa-b072", password="senha-segura"
    )
    Participacao.objects.create(
        usuario=admin, contrato=contrato, papel=Usuario.Perfil.ADMIN, ativo=True
    )
    for usuario in (equipe_1, equipe_2):
        Participacao.objects.create(
            usuario=usuario, contrato=contrato, papel=Usuario.Perfil.EQUIPE, ativo=True
        )
    Participacao.objects.create(
        usuario=chefia_inativa,
        contrato=contrato,
        papel=Usuario.Perfil.CHEFIA,
        ativo=False,
    )
    Participacao.objects.create(
        usuario=admin, contrato=inativo, papel=Usuario.Perfil.ADMIN, ativo=False
    )
    Documento.objects.create(
        contrato=contrato,
        identificador_base="DOC-ATIVO-1",
        ativo=True,
    )
    Documento.objects.create(
        contrato=contrato,
        identificador_base="DOC-ATIVO-2",
        ativo=False,
    )
    Documento.objects.create(
        contrato=contrato,
        identificador_base="DOC-CANCELADO",
        cancelado_em=timezone.now(),
    )

    client.force_login(staff)
    resposta = client.get(reverse("contratos_lista"))

    assert resposta.status_code == 200
    itens = resposta.context["contratos"]
    assert [item["contrato"].pk for item in itens] == [contrato.pk, inativo.pk]
    resumo = itens[0]
    assert resumo["codigo_interno"] == "CT-BETA"
    assert resumo["cliente"] == "Cliente Beta"
    assert resumo["nome_perfil"] == "Perfil Beta"
    assert resumo["total_documentos_em_conta"] == 2
    assert {
        papel["papel"]: papel["quantidade"]
        for papel in resumo["participacoes_por_papel"]
    } == {
        Usuario.Perfil.ADMIN: 1,
        Usuario.Perfil.EQUIPE: 2,
        Usuario.Perfil.PROJETISTA: 0,
        Usuario.Perfil.CHEFIA: 0,
    }
    assert all(
        papel["rotulo"] == Participacao(papel=papel["papel"]).get_papel_display()
        for papel in resumo["participacoes_por_papel"]
    )
    assert 'class="contrato-linha contrato-inativo"' in resposta.content.decode()
    assert "Inativo" in resposta.content.decode()
    assert reverse("painel", args=(contrato.pk,)) in resposta.content.decode()
    assert f"{reverse('lista_mestra')}?contrato={contrato.pk}" in resposta.content.decode()
    assert reverse("admin:contratos_contrato_change", args=(contrato.pk,)) in resposta.content.decode()
    assert reverse("contrato_detalhe", args=(contrato.pk,)) in resposta.content.decode()
    assert "Contratos" in resposta.content.decode()


@pytest.mark.django_db
def test_nao_staff_recebe_403_na_lista_e_no_detalhe(client, pessoa, contrato):
    client.force_login(pessoa)

    assert client.get(reverse("contratos_lista")).status_code == 403
    assert client.get(reverse("contrato_detalhe", args=(contrato.pk,))).status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("nome_url", ("contratos_lista", "contrato_detalhe"))
def test_anonimo_e_redirecionado_para_login(client, contrato, nome_url):
    url = (
        reverse(nome_url, args=(contrato.pk,))
        if nome_url == "contrato_detalhe"
        else reverse(nome_url)
    )

    resposta = client.get(url)

    assert resposta.status_code == 302
    assert resposta.url.startswith(reverse("login"))
    assert f"next={url}" in resposta.url


@pytest.mark.django_db
def test_detalhe_lista_participantes_com_ativos_primeiro(client, staff, contrato, pessoa):
    pessoa.first_name = "Paula"
    pessoa.last_name = "Silva"
    pessoa.save(update_fields=("first_name", "last_name"))
    Participacao.objects.create(
        usuario=pessoa,
        contrato=contrato,
        papel=Usuario.Perfil.EQUIPE,
        ativo=False,
    )
    ativa = Usuario.objects.create_user(
        username="ativa-b072",
        password="senha-segura",
        first_name="Ana",
        last_name="Lima",
    )
    Participacao.objects.create(
        usuario=ativa,
        contrato=contrato,
        papel=Usuario.Perfil.CHEFIA,
        ativo=True,
    )
    client.force_login(staff)

    resposta = client.get(reverse("contrato_detalhe", args=(contrato.pk,)))

    assert resposta.status_code == 200
    participantes = resposta.context["resumo"]["participantes"]
    assert [item["usuario"] for item in participantes] == ["ativa-b072", "pessoa-b072"]
    assert participantes[0] == {
        "nome": "Ana Lima",
        "usuario": "ativa-b072",
        "papel": "Chefia / coordenação",
        "ativo": True,
    }
    assert "Paula Silva" in resposta.content.decode()
    assert "pessoa-b072" in resposta.content.decode()
    assert "Equipe técnica" in resposta.content.decode()
    assert "Inativo" in resposta.content.decode()


@pytest.mark.django_db
def test_menu_contratos_so_aparece_para_staff(client, staff, pessoa, contrato):
    Participacao.objects.create(
        usuario=pessoa,
        contrato=contrato,
        papel=Usuario.Perfil.EQUIPE,
        ativo=True,
    )
    client.force_login(staff)
    resposta_staff = client.get(reverse("contratos_lista"))

    client.force_login(pessoa)
    resposta_pessoa = client.get(
        reverse("documentos_lista"), {"contrato": contrato.pk}
    )

    assert "Contratos" in resposta_staff.content.decode()
    assert resposta_pessoa.status_code == 200
    assert "Contratos" not in resposta_pessoa.content.decode()


@pytest.mark.django_db
def test_lista_nao_mostra_perfil_sem_nome_e_estado_vazio(client, staff):
    Contrato.objects.create(
        nome="Sem perfil",
        codigo_interno="CT-SEM-PERFIL",
        cliente="Cliente",
    )
    client.force_login(staff)

    resposta = client.get(reverse("contratos_lista"))

    assert resposta.status_code == 200
    assert "Nenhum contrato cadastrado." not in resposta.content.decode()
    assert "Sem perfil" in resposta.content.decode()
    assert "Perfil vigente" in resposta.content.decode()


@pytest.mark.django_db
def test_lista_vazia_mostra_mensagem_exigida(client, staff):
    client.force_login(staff)

    resposta = client.get(reverse("contratos_lista"))

    assert resposta.status_code == 200
    assert "Nenhum contrato cadastrado." in resposta.content.decode()


@pytest.mark.django_db
def test_consultas_da_lista_nao_crescem_com_contratos(db):
    Contrato.objects.create(nome="Inicial", codigo_interno="CT-0", cliente="Cliente")
    with CaptureQueriesContext(connection) as consultas_iniciais:
        listar_contratos()

    Contrato.objects.bulk_create(
        [
            Contrato(nome=f"Contrato {numero}", codigo_interno=f"CT-{numero}", cliente="Cliente")
            for numero in range(1, 9)
        ]
    )
    with CaptureQueriesContext(connection) as consultas_com_mais_contratos:
        listar_contratos()

    assert len(consultas_iniciais) == len(consultas_com_mais_contratos)
