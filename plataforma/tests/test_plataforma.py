import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from contas.models import Usuario


@pytest.mark.django_db
def test_login_exige_credenciais(client):
    response = client.post(reverse("login"), {"username": "", "password": ""})

    assert response.status_code == 200
    assert "Acesse sua conta" in response.content.decode()
    assert "Usuário ou senha incorretos" in response.content.decode()
    assert not response.wsgi_request.user.is_authenticated


@pytest.mark.django_db
def test_inicio_redireciona_usuario_anonimo(client):
    response = client.get(reverse("inicio"))

    assert response.status_code == 302
    assert response.url == f"{reverse('login')}?next={reverse('inicio')}"


@pytest.mark.django_db
def test_usuario_logado_ve_nome_e_perfil(client, django_user_model):
    usuario = django_user_model.objects.create_user(
        username="ana", password="senha-segura", first_name="Ana", last_name="Silva", perfil="chefia"
    )
    client.force_login(usuario)

    response = client.get(reverse("inicio"))

    assert response.status_code == 200
    html = response.content.decode()
    assert "Minha mesa" in html
    assert "Visão geral do contrato, alertas e próximos acompanhamentos." in html
    assert "Chefia / coordenação" in response.content.decode()


def test_import_core_parsers_na_plataforma():
    import core.parsers

    assert core.parsers is not None


@pytest.mark.django_db
def test_perfil_invalido_rejeitado_pelo_model():
    usuario = Usuario(username="perfil-invalido", perfil="invalido")

    with pytest.raises(ValidationError):
        usuario.full_clean()
