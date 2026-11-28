import pytest
from django.urls import reverse

from contratos.models import Contrato, Participacao


@pytest.mark.django_db
def test_usuario_edita_apenas_o_proprio_perfil(client, django_user_model):
    usuario = django_user_model.objects.create_user(username="perfil-proprio", password="senha")
    outro = django_user_model.objects.create_user(
        username="perfil-outro", password="senha", first_name="Nome", last_name="Original"
    )
    client.force_login(usuario)

    resposta = client.post(
        reverse("meu_perfil"),
        {
            "first_name": "Ana",
            "last_name": "Silva",
            "email": "ana@example.com",
            "id": outro.pk,
            "user_id": outro.pk,
            "perfil": "admin",
        },
    )

    assert resposta.status_code == 302
    usuario.refresh_from_db()
    outro.refresh_from_db()
    assert (usuario.first_name, usuario.last_name, usuario.email) == (
        "Ana",
        "Silva",
        "ana@example.com",
    )
    assert usuario.perfil == "equipe"
    assert (outro.first_name, outro.last_name) == ("Nome", "Original")


@pytest.mark.django_db
@pytest.mark.parametrize("campo", ["first_name", "last_name"])
def test_nome_e_sobrenome_sao_obrigatorios(client, django_user_model, campo):
    usuario = django_user_model.objects.create_user(
        username=f"perfil-vazio-{campo}", password="senha", first_name="Nome", last_name="Sobrenome"
    )
    client.force_login(usuario)
    dados = {"first_name": "Ana", "last_name": "Silva", "email": ""}
    dados[campo] = "   "

    resposta = client.post(reverse("meu_perfil"), dados)

    assert resposta.status_code == 200
    assert resposta.context["form"].errors[campo]
    usuario.refresh_from_db()
    assert (usuario.first_name, usuario.last_name) == ("Nome", "Sobrenome")


@pytest.mark.django_db
def test_aviso_de_nome_vazio_aparece_e_some_apos_completar(client, django_user_model):
    usuario = django_user_model.objects.create_user(username="perfil-aviso", password="senha")
    client.force_login(usuario)

    aviso = client.get(reverse("contratos_escolher"))
    assert "Complete seu nome em" in aviso.content.decode("utf-8")
    assert reverse("meu_perfil") in aviso.content.decode("utf-8")

    usuario.first_name = "Ana"
    usuario.last_name = "Silva"
    usuario.save(update_fields=("first_name", "last_name"))
    completo = client.get(reverse("contratos_escolher"))
    assert "Complete seu nome em" not in completo.content.decode("utf-8")


@pytest.mark.django_db
def test_perfil_mostra_dados_de_leitura_e_lista_apenas_contratos_do_usuario(client, django_user_model):
    usuario = django_user_model.objects.create_user(
        username="perfil-leitura", password="senha", first_name="Ana", last_name="Silva", perfil="chefia"
    )
    contrato = Contrato.objects.create(codigo_interno="CT-095-A", nome="Contrato A", cliente="Metrô")
    restrito = Contrato.objects.create(codigo_interno="CT-095-B", nome="Contrato B", cliente="Metrô")
    Participacao.objects.create(usuario=usuario, contrato=contrato, papel="equipe", ativo=True)
    client.force_login(usuario)

    resposta = client.get(reverse("meu_perfil"))
    html = resposta.content.decode("utf-8")

    assert resposta.status_code == 200
    assert "Chefia / coordenação" in html
    assert "CT-095-A" in html
    assert "CT-095-B" not in html


@pytest.mark.django_db
def test_tela_de_troca_de_senha_abre(client, django_user_model):
    usuario = django_user_model.objects.create_user(username="perfil-senha", password="senha-segura")
    client.force_login(usuario)

    resposta = client.get(reverse("senha_alterar"))

    assert resposta.status_code == 200
    assert "Trocar senha" in resposta.content.decode("utf-8")
    assert "old_password" in resposta.content.decode("utf-8")
