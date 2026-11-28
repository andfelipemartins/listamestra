import pytest
from django.urls import reverse

from contas.models import Usuario
from contratos.models import Contrato, Participacao
from documentos.models import Documento


def _contrato(codigo, nome):
    return Contrato.objects.create(
        codigo_interno=codigo,
        nome=nome,
        cliente="Metrô de São Paulo",
    )


def _participar(usuario, contrato, papel=Usuario.Perfil.EQUIPE):
    return Participacao.objects.create(
        usuario=usuario,
        contrato=contrato,
        papel=papel,
        ativo=True,
    )


@pytest.mark.django_db
def test_login_com_dois_contratos_abre_home_e_mostra_papel_e_contagem(client, django_user_model):
    usuario = django_user_model.objects.create_user(
        username="home-dupla", password="senha-segura"
    )
    primeiro = _contrato("CT-083-A", "Contrato Alfa")
    segundo = _contrato("CT-083-B", "Contrato Beta")
    _participar(usuario, primeiro, Usuario.Perfil.ADMIN)
    _participar(usuario, segundo)
    Documento.objects.create(
        contrato=primeiro,
        identificador_base="DE-15.25.00.00-6A1-1001",
        titulo="Desenho de teste",
    )

    resposta = client.post(
        reverse("login"),
        {"username": "home-dupla", "password": "senha-segura"},
        follow=True,
    )

    assert resposta.status_code == 200
    assert resposta.redirect_chain[0][0] == reverse("contratos_escolher")
    html = resposta.content.decode("utf-8")
    assert "CT-083-A" in html and "CT-083-B" in html
    assert "Contrato Alfa" in html and "Contrato Beta" in html
    assert "Administrador do contrato" in html
    assert "1 documento" in html


@pytest.mark.django_db
def test_login_com_um_contrato_vai_direto_ao_inicio(client, django_user_model):
    usuario = django_user_model.objects.create_user(
        username="home-unica", password="senha-segura"
    )
    contrato = _contrato("CT-083-UNICO", "Contrato único")
    _participar(usuario, contrato)

    resposta = client.post(
        reverse("login"),
        {"username": "home-unica", "password": "senha-segura"},
        follow=True,
    )

    assert resposta.status_code == 200
    assert resposta.redirect_chain == [
        (reverse("contratos_escolher"), 302),
        (reverse("inicio"), 302),
    ]
    assert client.session["contrato_ativo_id"] == contrato.pk
    assert "Minha mesa" in resposta.content.decode("utf-8")


@pytest.mark.django_db
def test_cartao_ativa_contrato_e_abre_inicio(client, django_user_model):
    usuario = django_user_model.objects.create_user(username="home-ativar")
    primeiro = _contrato("CT-083-1", "Primeiro")
    segundo = _contrato("CT-083-2", "Segundo")
    _participar(usuario, primeiro)
    _participar(usuario, segundo)
    client.force_login(usuario)

    resposta = client.post(reverse("contrato_ativar"), {"contrato": segundo.pk})

    assert resposta.status_code == 302
    assert resposta["Location"] == reverse("inicio")
    assert client.session["contrato_ativo_id"] == segundo.pk
    inicio = client.get(reverse("inicio"))
    assert inicio.status_code == 200
    assert inicio.context["contrato"].pk == segundo.pk
    html = inicio.content.decode("utf-8")
    assert "Trocar contrato" in html
    assert "CT-083-2" in html


@pytest.mark.django_db
def test_contrato_de_terceiro_nao_aparece_e_nao_pode_ser_ativado(
    client, django_user_model
):
    usuario = django_user_model.objects.create_user(username="home-sem-acesso")
    acessivel = _contrato("CT-083-OK", "Acessível")
    acessivel_2 = _contrato("CT-083-OK-2", "Também acessível")
    restrito = _contrato("CT-083-NAO", "Restrito")
    _participar(usuario, acessivel)
    _participar(usuario, acessivel_2)
    client.force_login(usuario)

    home = client.get(reverse("contratos_escolher"))
    html = home.content.decode("utf-8")
    assert "CT-083-OK" in html
    assert "CT-083-NAO" not in html

    client.raise_request_exception = False
    resposta = client.post(reverse("contrato_ativar"), {"contrato": restrito.pk})
    assert resposta.status_code == 403
    assert client.session.get("contrato_ativo_id") != restrito.pk


@pytest.mark.django_db
def test_modo_grade_ou_lista_fica_salvo_na_sessao(client, django_user_model):
    usuario = django_user_model.objects.create_user(username="home-modo")
    _participar(usuario, _contrato("CT-083-MODO-1", "Modo 1"))
    _participar(usuario, _contrato("CT-083-MODO-2", "Modo 2"))
    client.force_login(usuario)

    client.post(reverse("contratos_escolher"), {"modo": "lista"})
    resposta = client.get(reverse("contratos_escolher"))

    assert client.session["modo_contratos"] == "lista"
    assert 'contratos-lista--lista' in resposta.content.decode("utf-8")


@pytest.mark.django_db
def test_staff_home_mostra_todos_os_ativos_e_omite_inativos(client, django_user_model):
    staff = django_user_model.objects.create_user(username="home-staff", is_staff=True)
    _contrato("CT-083-STAFF-A", "Contrato ativo A")
    _contrato("CT-083-STAFF-B", "Contrato ativo B")
    inativo = _contrato("CT-083-STAFF-X", "Contrato inativo")
    inativo.ativo = False
    inativo.save(update_fields=("ativo",))
    client.force_login(staff)

    resposta = client.get(reverse("contratos_escolher"))
    html = resposta.content.decode("utf-8")

    assert "CT-083-STAFF-A" in html and "CT-083-STAFF-B" in html
    assert "CT-083-STAFF-X" not in html
    assert "Acesso administrativo" in html


@pytest.mark.django_db
def test_parametro_legado_define_sessao_e_home_troca_contrato(client, django_user_model):
    usuario = django_user_model.objects.create_user(username="home-trocar")
    primeiro = _contrato("CT-083-X", "Contrato X")
    segundo = _contrato("CT-083-Y", "Contrato Y")
    _participar(usuario, primeiro)
    _participar(usuario, segundo)
    client.force_login(usuario)

    resposta_inicio = client.get(reverse("inicio"), {"contrato": primeiro.pk})
    assert resposta_inicio.status_code == 200
    assert client.session["contrato_ativo_id"] == primeiro.pk

    home = client.get(reverse("contratos_escolher"))
    assert home.status_code == 200
    client.post(reverse("contrato_ativar"), {"contrato": segundo.pk})
    resposta_pendencias = client.get(reverse("acoes:pendencias"))

    assert resposta_pendencias.status_code == 200
    assert resposta_pendencias.context["contrato"].pk == segundo.pk
    assert client.session["contrato_ativo_id"] == segundo.pk


@pytest.mark.django_db
def test_sem_contrato_na_sessao_inicio_redireciona_para_home(client, django_user_model):
    usuario = django_user_model.objects.create_user(username="home-vazio")
    client.force_login(usuario)

    resposta = client.get(reverse("inicio"))

    assert resposta.status_code == 302
    assert resposta["Location"] == reverse("contratos_escolher")
    home = client.get(reverse("contratos_escolher"))
    assert "Nenhum contrato disponível" in home.content.decode("utf-8")
