from datetime import date, datetime
from pathlib import Path

import pytest
import yaml
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from core.perfil import perfil_de_dict
from core.perfil.codigo import interpretar
from contratos.models import Contrato, Participacao, PerfilContrato
from documentos.models import Documento
from importacoes.id_excel import LinhaPrevia, PreviaID
from importacoes.models import ImportacaoID, IndiceDocumentos, InconsistenciaImportacao, ItemPrevisto
from importacoes.services import aplicar_previa
from registro.servicos import carregar_eventos


RAIZ = Path(__file__).resolve().parents[2]
PERFIL_METRO = RAIZ / "core" / "perfil" / "exemplos" / "metro.yaml"


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato de atividade",
        codigo_interno="CT-ATIVIDADE",
        cliente="Cliente de teste",
    )


@pytest.fixture
def usuario(contrato):
    modelo = get_user_model()
    usuario = modelo.objects.create_user(
        username="ana",
        first_name="Ana",
        last_name="Silva",
        password="senha",
    )
    Participacao.objects.create(
        usuario=usuario,
        contrato=contrato,
        papel=modelo.Perfil.EQUIPE,
    )
    return usuario


@pytest.fixture
def perfil_modelo(contrato):
    with PERFIL_METRO.open(encoding="utf-8") as arquivo:
        definicao = _json_compatibility(yaml.safe_load(arquivo))
    return PerfilContrato.objects.create(
        contrato=contrato,
        versao=1,
        vigencia_inicio=date(2026, 1, 1),
        definicao=definicao,
    )


def _json_compatibility(valor):
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {chave: _json_compatibility(item) for chave, item in valor.items()}
    if isinstance(valor, list):
        return [_json_compatibility(item) for item in valor]
    return valor


def _linha_previa(perfil_modelo, numero, codigo, categoria="novos"):
    interpretado = interpretar(perfil_de_dict(perfil_modelo.definicao), codigo)
    return LinhaPrevia(
        numero_linha=numero,
        codigo=codigo,
        titulo="Título importado",
        excluido=False,
        categoria=categoria,
        identificador_base=interpretado.identificador_base if categoria == "novos" else "",
        segmentos=dict(interpretado.segmentos) if categoria == "novos" else None,
        campo_falhou="sequencial" if categoria != "novos" else "",
        mensagem="Código inválido" if categoria != "novos" else "",
        dados_linha={"Name": codigo},
    )


def _previa(contrato, perfil_modelo, codigo, linhas):
    return PreviaID(
        contrato_id=contrato.pk,
        perfil_id=perfil_modelo.pk,
        fonte="excel_id",
        codigo_indice="ID-REGISTRO",
        revisao="1",
        arquivo_nome="ID-registro.xlsx",
        formato="excel_id",
        linhas=tuple(linhas),
    )


def _documento(contrato, codigo, titulo, usuario=None):
    documento = Documento(
        contrato=contrato,
        identificador_base=codigo,
        titulo=titulo,
    )
    documento._history_user = usuario
    documento.save()
    return documento


@pytest.mark.django_db
def test_alteracao_de_titulo_gera_evento_com_diff(contrato, usuario):
    documento = _documento(contrato, "DE-15.25.00.00-6A1-1001", "Título anterior", usuario)
    documento.titulo = "Título novo"
    documento._history_user = usuario
    documento.save(update_fields=("titulo",))

    evento = next(
        item
        for item in carregar_eventos(contrato)
        if item["acao"] == "alterou" and item["codigo"] == documento.identificador_base
    )

    assert evento["usuario_nome"] == "Ana Silva"
    assert evento["resumo"] == f"Ana Silva alterou o título de {documento.identificador_base}"
    assert evento["detalhes"] == [
        {"campo": "título", "antes": "Título anterior", "depois": "Título novo"}
    ]


@pytest.mark.django_db
def test_importacao_id_aparece_como_um_evento_para_o_lote(contrato, usuario):
    indice = IndiceDocumentos.objects.create(
        contrato=contrato,
        codigo="ID-ATIVIDADE",
        revisao="1",
        fonte=IndiceDocumentos.Fonte.EXCEL_ID,
        arquivo_nome="ID-atividade.xlsx",
        importado_em=timezone.now(),
        importado_por=usuario,
    )
    for numero in range(3):
        documento = _documento(contrato, f"DE-15.25.00.00-6A1-10{numero:02}", f"Doc {numero}")
        ItemPrevisto.objects.create(indice=indice, documento=documento, titulo=documento.titulo)
    ImportacaoID.objects.create(
        contrato=contrato,
        indice=indice,
        arquivo_nome="ID-atividade.xlsx",
        importado_por=usuario,
        linhas_validas=3,
        linhas_invalidas=2,
    )

    importacoes = [evento for evento in carregar_eventos(contrato) if evento["acao"] == "importou"]

    assert len(importacoes) == 1
    assert importacoes[0]["resumo"] == "Ana Silva importou ID ID-atividade.xlsx: 3 válidas, 2 recusadas"
    assert importacoes[0]["link_recusadas"] is True


@pytest.mark.django_db
def test_importacao_id_agrupa_historicos_no_detalhe_com_codigos(contrato, usuario, perfil_modelo):
    codigo = "DE-15.25.00.00-6A1-1001"
    previa = _previa(contrato, perfil_modelo, codigo, [_linha_previa(perfil_modelo, 2, codigo)])

    aplicar_previa(previa, contrato=contrato, perfil_modelo=perfil_modelo, usuario=usuario)

    eventos = carregar_eventos(contrato)
    eventos_do_codigo = [evento for evento in eventos if codigo in evento["codigo"]]

    assert len(eventos_do_codigo) == 1
    evento = eventos_do_codigo[0]
    assert evento["acao"] == "importou"
    detalhes = {item["campo"]: item["depois"] for item in evento["detalhes"]}
    assert "criou 1 documento" in detalhes["Alterações agrupadas"]
    assert "criou 1 código" in detalhes["Alterações agrupadas"]
    assert "criou 1 item previsto" in detalhes["Alterações agrupadas"]
    assert detalhes["Códigos"] == codigo


@pytest.mark.django_db
def test_reprocessamento_id_gera_evento_com_usuario_e_codigo(contrato, usuario, perfil_modelo):
    codigo = "DE-15.25.00.00-6A1-1002"
    previa_invalida = _previa(
        contrato,
        perfil_modelo,
        codigo,
        [_linha_previa(perfil_modelo, 2, "CÓDIGO-INVÁLIDO", categoria="codigos_invalidos")],
    )
    aplicar_previa(previa_invalida, contrato=contrato, perfil_modelo=perfil_modelo, usuario=usuario)
    inconsistencia = InconsistenciaImportacao.objects.get(importacao_id__contrato=contrato)
    previa_corrigida = _previa(
        contrato,
        perfil_modelo,
        codigo,
        [_linha_previa(perfil_modelo, 2, codigo)],
    )

    aplicar_previa(
        previa_corrigida,
        contrato=contrato,
        perfil_modelo=perfil_modelo,
        usuario=usuario,
        inconsistencias_existentes=[inconsistencia],
    )

    evento = next(evento for evento in carregar_eventos(contrato) if evento["acao"] == "reprocessou")
    assert evento["usuario_nome"] == "Ana Silva"
    assert evento["validas"] == 1
    assert codigo in evento["codigo"]
    inconsistencia.refresh_from_db()
    assert inconsistencia.resolvida_por == usuario


@pytest.mark.django_db
def test_filtros_por_pessoa_acao_periodo_e_codigo(client, contrato, usuario):
    documento = _documento(contrato, "DE-15.25.00.00-6A1-1001", "Título inicial", usuario)
    documento.titulo = "Título atualizado"
    documento._history_user = usuario
    documento.save(update_fields=("titulo",))
    outro = _documento(contrato, "MC-15.25.00.00-6A1-1002", "Outro documento", usuario)
    outro.titulo = "Outro título atualizado"
    outro._history_user = usuario
    outro.save(update_fields=("titulo",))

    client.force_login(usuario)
    resposta = client.get(
        reverse("atividade"),
        {
            "contrato": contrato.pk,
            "pessoa": usuario.pk,
            "acao": "alterou",
            "de": timezone.localdate().isoformat(),
            "ate": timezone.localdate().isoformat(),
            "codigo": "1001",
        },
    )

    html = resposta.content.decode()
    assert resposta.status_code == 200
    pasta_documento = reverse("documento_pasta", args=(contrato.pk, documento.pk))
    assert "alterou o título de " in html
    assert f'href="{pasta_documento}">DE-15.25.00.00-6A1-1001</a>' in html
    assert "MC-15.25.00.00-6A1-1002" not in html


@pytest.mark.django_db
def test_evento_de_documento_linka_codigo_a_pasta_na_lista_e_no_detalhe(
    client, contrato, usuario
):
    codigo = "DE-15.25.00.00-6A1-1001"
    documento = _documento(contrato, codigo, "Título inicial", usuario)
    documento.titulo = "Título atualizado"
    documento._history_user = usuario
    documento.save(update_fields=("titulo",))
    evento = next(
        item
        for item in carregar_eventos(contrato)
        if item["acao"] == "alterou" and item["codigo"] == codigo
    )
    client.force_login(usuario)
    pasta = reverse("documento_pasta", args=(contrato.pk, documento.pk))
    link = f'href="{pasta}">{codigo}</a>'

    lista = client.get(reverse("atividade"), {"contrato": contrato.pk})
    detalhe = client.get(
        reverse("atividade"), {"contrato": contrato.pk, "evento": evento["chave"]}
    )

    assert evento["documento_id"] == documento.pk
    assert lista.status_code == 200
    assert detalhe.status_code == 200
    assert link in lista.content.decode()
    assert link in detalhe.content.decode()


@pytest.mark.django_db
def test_acesso_exige_participacao_e_staff_pode_ver_outros_contratos(client, contrato):
    modelo = get_user_model()
    sem_participacao = modelo.objects.create_user(username="externo", password="senha")
    client.force_login(sem_participacao)
    assert client.get(reverse("atividade"), {"contrato": contrato.pk}).status_code == 403

    staff = modelo.objects.create_user(username="staff", password="senha", is_staff=True)
    client.force_login(staff)
    resposta = client.get(reverse("atividade"), {"contrato": contrato.pk})
    assert resposta.status_code == 200
