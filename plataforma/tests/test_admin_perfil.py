from datetime import date, datetime
from io import StringIO
from pathlib import Path
import tempfile

import pytest
import yaml
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from contratos.admin import PerfilContratoAdmin
from contratos.models import Contrato, PerfilContrato
from documentos.models import CodigoDocumento, Documento
from core.perfil import perfil_de_dict
from core.perfil.codigo import montar


RAIZ_REPOSITORIO = Path(__file__).resolve().parents[2]
EXEMPLOS = RAIZ_REPOSITORIO / "core" / "perfil" / "exemplos"


def definicao_exemplo(nome):
    with (EXEMPLOS / nome).open(encoding="utf-8") as arquivo:
        return json_compatibility(yaml.safe_load(arquivo))


def json_compatibility(valor):
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {chave: json_compatibility(item) for chave, item in valor.items()}
    if isinstance(valor, list):
        return [json_compatibility(item) for item in valor]
    return valor


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato do perfil",
        codigo_interno="CT-PERFIL",
        cliente="Cliente de teste",
    )


def criar_perfil(contrato, nome="metro.yaml", versao=1):
    definicao = definicao_exemplo(nome)
    return PerfilContrato.objects.create(
        contrato=contrato,
        versao=versao,
        vigencia_inicio=date.fromisoformat(str(definicao["vigencia_inicio"])),
        definicao=definicao,
    )


@pytest.mark.django_db
def test_perfil_valido_salva_e_invalido_falha_em_full_clean(contrato):
    definicao = definicao_exemplo("metro.yaml")
    perfil = PerfilContrato(
        contrato=contrato,
        versao=1,
        vigencia_inicio=date(2026, 11, 18),
        definicao=definicao,
    )
    perfil.full_clean()
    perfil.save()

    perfil_invalido = PerfilContrato(
        contrato=contrato,
        versao=2,
        vigencia_inicio=date(2026, 11, 18),
        definicao={
            "nome": "Inválido",
            "versao": "1",
            "vigencia_inicio": "2026-11-18",
            "codigo": {"segmentos": []},
        },
    )
    with pytest.raises(ValidationError) as erro:
        perfil_invalido.full_clean()

    assert "definicao" in erro.value.message_dict
    assert "codigo.segmentos" in erro.value.message_dict["definicao"][0]


@pytest.mark.django_db
def test_edicao_do_perfil_exibe_caixas_e_botao_de_teste(client, django_user_model, contrato):
    perfil = criar_perfil(contrato)
    administrador = django_user_model.objects.create_superuser(
        username="admin-perfil", email="admin@example.com", password="senha-segura"
    )
    client.force_login(administrador)

    response = client.get(reverse("admin:contratos_perfilcontrato_change", args=(perfil.pk,)))

    assert response.status_code == 200
    assert "Caixas do código" in response.content.decode()
    assert "tipo documental" in response.content.decode()
    assert "sequencial" in response.content.decode()
    assert "Testar códigos" in response.content.decode()
    assert "Feriados" in response.content.decode()
    perfil_definido = perfil_de_dict(perfil.definicao)
    codigo_exemplo = montar(
        perfil_definido,
        {
            segmento.nome: PerfilContratoAdmin._valor_de_exemplo(segmento)
            for segmento in perfil_definido.codigo.campos
        },
    )
    assert codigo_exemplo in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("arquivo_perfil", "codigo_valido", "codigo_invalido", "rotulo_caixa"),
    [
        (
            "metro.yaml",
            "DE-15.25.00.00-6B7-1501",
            "DE-15.25.00.00-6X7-1501",
            "classe e subclasse",
        ),
        (
            "spobras.yaml",
            "DE-CC-EE-WW-5E-001-A",
            "DE-CC-EE-WW-5E-001-?",
            "revisão",
        ),
    ],
)
def test_view_testa_codigos_validos_e_invalidos(
    client, django_user_model, contrato, arquivo_perfil, codigo_valido, codigo_invalido, rotulo_caixa
):
    perfil = criar_perfil(contrato, arquivo_perfil)
    administrador = django_user_model.objects.create_superuser(
        username=f"admin-{arquivo_perfil}",
        email=f"{arquivo_perfil}@example.com",
        password="senha-segura",
    )
    client.force_login(administrador)

    response = client.post(
        reverse("admin:contratos_perfilcontrato_testar_codigos", args=(perfil.pk,)),
        {"codigos": f"{codigo_valido}\n{codigo_invalido}"},
    )

    assert response.status_code == 200
    resultados = response.context["resultados"]
    assert [resultado["valido"] for resultado in resultados] == [True, False]
    assert resultados[0]["caixas"]
    assert resultados[1]["segmento"] == rotulo_caixa
    assert resultados[1]["mensagem"]
    conteudo = response.content.decode()
    assert "Válido" in conteudo
    assert "Inválido" in conteudo
    assert codigo_valido in conteudo


@pytest.mark.django_db
def test_view_de_teste_redireciona_usuario_sem_acesso_admin(client, contrato):
    perfil = criar_perfil(contrato)

    response = client.get(
        reverse("admin:contratos_perfilcontrato_testar_codigos", args=(perfil.pk,))
    )

    assert response.status_code == 302
    assert response["Location"].startswith(reverse("admin:login"))


@pytest.mark.django_db
def test_view_de_teste_retorna_403_para_staff_sem_permissao(client, django_user_model, contrato):
    perfil = criar_perfil(contrato)
    usuario = django_user_model.objects.create_user(
        username="staff-sem-permissao",
        password="senha-segura",
        is_staff=True,
    )
    client.force_login(usuario)

    response = client.get(
        reverse("admin:contratos_perfilcontrato_testar_codigos", args=(perfil.pk,))
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_comando_cria_proxima_versao_e_falha_com_yaml_invalido(contrato):
    criar_perfil(contrato, versao=1)
    yaml_valido = EXEMPLOS / "spobras.yaml"
    saida = StringIO()

    call_command(
        "carregar_perfil_exemplo",
        contrato.pk,
        str(yaml_valido),
        stdout=saida,
    )

    novo_perfil = PerfilContrato.objects.get(contrato=contrato, versao=2)
    assert novo_perfil.definicao["nome"] == "SPObras"
    assert "Perfil v2 criado" in saida.getvalue()

    arquivo_temporario = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".yaml",
        dir=Path(__file__).parent,
        delete=False,
    )
    yaml_invalido = Path(arquivo_temporario.name)
    try:
        arquivo_temporario.write("codigo: [")
        arquivo_temporario.close()
        with pytest.raises(CommandError, match="YAML de perfil inválido"):
            call_command("carregar_perfil_exemplo", contrato.pk, str(yaml_invalido))
    finally:
        if not arquivo_temporario.closed:
            arquivo_temporario.close()
        yaml_invalido.unlink(missing_ok=True)


@pytest.mark.django_db
def test_comando_informa_quando_contrato_nao_existe():
    with pytest.raises(CommandError, match="Contrato com ID 9999 não existe"):
        call_command("carregar_perfil_exemplo", 9999, str(EXEMPLOS / "metro.yaml"))


@pytest.mark.django_db
def test_documento_so_pode_ter_um_codigo_por_perfil(contrato):
    perfil = criar_perfil(contrato)
    documento = Documento.objects.create(contrato=contrato, identificador_base="DOC-PERFIL-1")
    CodigoDocumento.objects.create(documento=documento, perfil=perfil, codigo="COD-1")

    with pytest.raises(IntegrityError), transaction.atomic():
        CodigoDocumento.objects.create(documento=documento, perfil=perfil, codigo="COD-2")


def _url_feriados(perfil):
    return reverse("admin:contratos_perfilcontrato_importar_feriados", args=(perfil.pk,))


def _arquivo_csv(conteudo):
    return SimpleUploadedFile("feriados.csv", conteudo.encode("utf-8"), content_type="text/csv")


def _adicionar_extra(perfil, data, nome):
    definicao = json_compatibility(perfil.definicao)
    definicao["prazos"]["feriados"]["extras"].append({"data": data, "nome": nome})
    perfil.definicao = definicao
    perfil.save(update_fields=("definicao",))


@pytest.mark.django_db
def test_pagina_feriados_mostra_nacionais_calculados_e_extras(client, django_user_model, contrato):
    perfil = criar_perfil(contrato)
    ano = timezone.localdate().year
    data_extra = date(ano, 6, 10)
    _adicionar_extra(perfil, data_extra.isoformat(), "Aniversário municipal")
    administrador = django_user_model.objects.create_superuser(
        username="admin-feriados", email="feriados@example.com", password="senha-segura"
    )
    client.force_login(administrador)

    response = client.get(
        reverse("admin:contratos_perfilcontrato_feriados", args=(perfil.pk,))
    )

    assert response.status_code == 200
    itens = response.context["itens"]
    assert any(item["data"] == date(ano, 1, 1) and item["origem"] == "Nacional (calculado)" for item in itens)
    assert any(
        item["data"] == data_extra
        and item["nome"] == "Aniversário municipal"
        and item["origem"] == "Extra do perfil"
        for item in itens
    )
    assert any(item["data"].year == ano + 1 for item in itens)


@pytest.mark.django_db
def test_perfil_sem_prazos_orienta_configurar_antes_da_importacao(
    client, django_user_model, contrato
):
    perfil = criar_perfil(contrato)
    definicao = json_compatibility(perfil.definicao)
    definicao.pop("prazos")
    perfil.definicao = definicao
    perfil.save(update_fields=("definicao",))
    administrador = django_user_model.objects.create_superuser(
        username="admin-sem-prazos", email="sem-prazos@example.com", password="senha-segura"
    )
    client.force_login(administrador)

    resposta_feriados = client.get(
        reverse("admin:contratos_perfilcontrato_feriados", args=(perfil.pk,))
    )
    resposta_importacao = client.get(_url_feriados(perfil))

    assert "configure os prazos" in resposta_feriados.content.decode().lower()
    assert "É preciso configurar a seção de prazos" in resposta_importacao.content.decode()
    assert "<input type=\"file\"" not in resposta_importacao.content.decode()


@pytest.mark.django_db
def test_importacao_de_feriados_mostra_previa_e_linhas_recusadas(
    client, django_user_model, contrato
):
    perfil = criar_perfil(contrato)
    administrador = django_user_model.objects.create_superuser(
        username="admin-previa-feriados", email="previa@example.com", password="senha-segura"
    )
    client.force_login(administrador)

    response = client.post(
        _url_feriados(perfil),
        {"arquivo": _arquivo_csv("data,nome\n10/06/2027,Aniversário\n99/99/2027,Data impossível\n")},
    )

    assert response.status_code == 200
    previa = response.context["previa"]
    assert previa["validos"] == [{"data": "2027-06-10", "nome": "Aniversário"}]
    assert len(previa["erros"]) == 1
    assert previa["erros"][0]["linha"] == 3
    assert "data inválida" in previa["erros"][0]["mensagem"]
    assert "Confirmar importação" in response.content.decode()


@pytest.mark.django_db
def test_linha_com_nome_vazio_e_recusada_com_motivo(client, django_user_model, contrato):
    perfil = criar_perfil(contrato)
    administrador = django_user_model.objects.create_superuser(
        username="admin-linha-invalida", email="linha-invalida@example.com", password="senha-segura"
    )
    client.force_login(administrador)

    response = client.post(
        _url_feriados(perfil),
        {"arquivo": _arquivo_csv("data,nome\n10/06/2027,\n")},
    )

    assert response.status_code == 200
    assert response.context["previa"]["validos"] == []
    erro = response.context["previa"]["erros"][0]
    assert erro["linha"] == 2
    assert erro["mensagem"] == "nome vazio"
    assert "Confirmar importação" not in response.content.decode()


@pytest.mark.django_db
def test_confirmacao_cria_nova_versao_sem_editar_a_vigente(client, django_user_model, contrato):
    perfil = criar_perfil(contrato)
    definicao_original = json_compatibility(perfil.definicao)
    administrador = django_user_model.objects.create_superuser(
        username="admin-versao-feriados", email="versao@example.com", password="senha-segura"
    )
    client.force_login(administrador)
    url = _url_feriados(perfil)

    previa = client.post(
        url,
        {"arquivo": _arquivo_csv("data,nome\n10/06/2027,Aniversário\n")},
    )
    assert previa.status_code == 200
    resposta = client.post(url, {"confirmar": "1"})

    novo_perfil = PerfilContrato.objects.get(contrato=contrato, versao=2)
    assert resposta.status_code == 302
    assert PerfilContrato.objects.get(pk=perfil.pk).definicao == definicao_original
    assert novo_perfil.definicao["prazos"]["feriados"]["extras"][-1] == {
        "data": "2027-06-10",
        "nome": "Aniversário",
    }


@pytest.mark.django_db
def test_duplicatas_sao_ignoradas_ao_atualizar_extras(client, django_user_model, contrato):
    perfil = criar_perfil(contrato)
    _adicionar_extra(perfil, "2027-06-10", "Aniversário existente")
    _adicionar_extra(perfil, "2027-06-10", "Duplicata antiga")
    administrador = django_user_model.objects.create_superuser(
        username="admin-duplicata-feriados", email="duplicata@example.com", password="senha-segura"
    )
    client.force_login(administrador)
    url = _url_feriados(perfil)

    previa = client.post(
        url,
        {
            "arquivo": _arquivo_csv(
                "data,nome\n10/06/2027,Outro nome\n11/06/2027,Novo feriado\n11/06/2027,Repetido\n"
            )
        },
    )
    assert previa.status_code == 200
    assert len(previa.context["previa"]["duplicatas"]) == 2
    client.post(url, {"confirmar": "1"})

    novo_perfil = PerfilContrato.objects.get(contrato=contrato, versao=2)
    extras = novo_perfil.definicao["prazos"]["feriados"]["extras"]
    assert extras == [
        {"data": "2027-06-10", "nome": "Aniversário existente"},
        {"data": "2027-06-11", "nome": "Novo feriado"},
    ]
