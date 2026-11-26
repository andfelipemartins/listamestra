from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.utils import timezone

from contas.models import Usuario
from contratos.models import Contrato, Participacao, PerfilContrato
from core.perfil import perfil_de_dict
from documentos.models import Analise, Documento, Emissao
from documentos.servicos import (
    cancelar_documentos,
    carregar_lista_documentos,
    carregar_pasta_documento,
)
from importacoes.models import ImportacaoSituacao, IndiceDocumentos, ItemPrevisto
from painel.servicos import carregar_painel
from registro.servicos import carregar_eventos


PASTA_EXEMPLOS = Path(__file__).resolve().parents[2] / "core" / "perfil" / "exemplos"


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato de cancelamento",
        codigo_interno="CT-CANCEL",
        cliente="Cliente de teste",
    )


@pytest.fixture
def perfil_modelo(contrato):
    with (PASTA_EXEMPLOS / "metro.yaml").open(encoding="utf-8") as arquivo:
        definicao = _json_compatibility(yaml.safe_load(arquivo))
    inicio = timezone.localdate() - timedelta(days=30)
    definicao["vigencia_inicio"] = inicio.isoformat()
    return PerfilContrato.objects.create(
        contrato=contrato,
        versao=1,
        vigencia_inicio=inicio,
        definicao=definicao,
    )


@pytest.fixture
def admin_contrato(contrato, django_user_model):
    usuario = django_user_model.objects.create_user(
        username="admin-cancelamento",
        password="senha",
        first_name="Ana",
        last_name="Administradora",
    )
    Participacao.objects.create(
        usuario=usuario,
        contrato=contrato,
        papel=Usuario.Perfil.ADMIN,
        ativo=True,
    )
    return usuario


def _json_compatibility(valor):
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {chave: _json_compatibility(item) for chave, item in valor.items()}
    if isinstance(valor, list):
        return [_json_compatibility(item) for item in valor]
    return valor


def _documento(contrato, sequencial, *, situacao=None, indice=None):
    codigo = f"DE-15.25.00.00-6A1-{sequencial:04d}"
    documento = Documento.objects.create(
        contrato=contrato,
        identificador_base=codigo,
        tipo="DE",
        trecho="25",
        disciplina="A1",
        titulo=f"Documento {sequencial}",
        atributos={
            "tipo": "DE",
            "trecho": "25",
            "subtrecho": "00",
            "unidade": "00",
            "etapa": "6",
            "classe": "A1",
            "sequencial": str(sequencial),
        },
    )
    if indice is not None:
        ItemPrevisto.objects.create(indice=indice, documento=documento, titulo=documento.titulo)
    if situacao is not None:
        emissao = Emissao.objects.create(
            documento=documento,
            revisao="1",
            versao=1,
            fase=Emissao.Fase.PRELIMINAR,
            data_emissao=timezone.localdate() - timedelta(days=5),
            origem=Emissao.Origem.CLIENTE,
        )
        Analise.objects.create(
            emissao=emissao,
            etapa="Análise do cliente",
            situacao=situacao,
            origem=Analise.Origem.IMPORTADO_PW,
            data_analise=timezone.localdate() - timedelta(days=4),
        )
    return documento


def _indice(contrato):
    return IndiceDocumentos.objects.create(
        contrato=contrato,
        codigo="ID-CANCELAMENTO",
        revisao="1",
        fonte=IndiceDocumentos.Fonte.EXCEL_ID,
        arquivo_nome="id.xlsx",
        importado_em=timezone.now(),
    )


@pytest.mark.django_db
def test_admin_cancela_varios_documentos_e_grava_historico(
    contrato, perfil_modelo, admin_contrato
):
    documentos = [_documento(contrato, 1001), _documento(contrato, 1002)]

    resultado = cancelar_documentos(
        admin_contrato,
        contrato,
        [documento.pk for documento in documentos],
        "desmembrado",
        "",
    )

    assert resultado["quantidade_cancelada"] == 2
    assert len(resultado["codigos_cancelados"]) == 2
    for documento in documentos:
        documento.refresh_from_db()
        assert documento.cancelado_em is not None
        assert documento.cancelado_por == admin_contrato
        assert documento.motivo_cancelamento == "desmembrado"
        historico = documento.history.latest()
        assert historico.history_user == admin_contrato
        assert historico.history_change_reason.startswith("cancelamento_sistema:")


@pytest.mark.django_db
@pytest.mark.parametrize("papel", [Usuario.Perfil.EQUIPE, Usuario.Perfil.CHEFIA])
def test_equipe_e_visualizador_nao_podem_cancelar(
    papel, contrato, perfil_modelo, django_user_model
):
    usuario = django_user_model.objects.create_user(username=f"{papel}-bloqueado", password="senha")
    Participacao.objects.create(usuario=usuario, contrato=contrato, papel=papel, ativo=True)
    documento = _documento(contrato, 1003)

    with pytest.raises(PermissionDenied):
        cancelar_documentos(usuario, contrato, [documento.pk], "cliente")


@pytest.mark.django_db
def test_cancelamento_recusa_documento_de_outro_contrato(
    contrato, perfil_modelo, admin_contrato
):
    outro_contrato = Contrato.objects.create(
        nome="Outro contrato",
        codigo_interno="CT-OUTRO",
        cliente="Outro cliente",
    )
    documento = _documento(outro_contrato, 1004)

    with pytest.raises(ValueError, match="não pertencem a este contrato"):
        cancelar_documentos(admin_contrato, contrato, [documento.pk], "cliente")

    documento.refresh_from_db()
    assert documento.cancelado_em is None


@pytest.mark.django_db
def test_outro_exige_observacao_e_motivo_deve_ser_da_lista(
    contrato, perfil_modelo, admin_contrato
):
    documento = _documento(contrato, 1005)

    with pytest.raises(ValueError, match="observação"):
        cancelar_documentos(admin_contrato, contrato, [documento.pk], "outro")
    with pytest.raises(ValueError, match="motivo da lista"):
        cancelar_documentos(admin_contrato, contrato, [documento.pk], "motivo-livre")


@pytest.mark.django_db
def test_cancelados_existentes_sao_ignorados_com_aviso_no_retorno(
    client, contrato, perfil_modelo, admin_contrato
):
    cancelado_pw = _documento(contrato, 1006, situacao="Cancelado")
    cancelado_sistema = _documento(contrato, 1007)
    cancelado_sistema.cancelado_em = timezone.now()
    cancelado_sistema.cancelado_por = admin_contrato
    cancelado_sistema.motivo_cancelamento = "cliente"
    cancelado_sistema.save(
        update_fields=("cancelado_em", "cancelado_por", "motivo_cancelamento")
    )
    pendente = _documento(contrato, 1008)

    client.force_login(admin_contrato)
    resposta = client.post(
        reverse("documentos_cancelar", args=(contrato.pk,)),
        {
            "documento": [cancelado_pw.pk, cancelado_sistema.pk, pendente.pk],
            "motivo_cancelamento": "cliente",
            "lista_query": f"contrato={contrato.pk}",
        },
        follow=True,
    )

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "1 documento(s) cancelado(s)." in html
    assert "Documentos ignorados:" in html
    assert "já cancelado pelo PW" in html
    assert "já cancelado pelo sistema" in html
    pendente.refresh_from_db()
    assert pendente.cancelado_em is not None


@pytest.mark.django_db
def test_cancelamento_sai_do_total_do_painel_e_conta_como_cancelado(
    contrato, perfil_modelo, admin_contrato
):
    indice = _indice(contrato)
    aprovado = _documento(contrato, 1009, situacao="Aprovado", indice=indice)
    cancelado = _documento(contrato, 1010, indice=indice)
    cancelar_documentos(admin_contrato, contrato, [cancelado.pk], "fora_escopo")

    dados = carregar_painel(contrato)

    assert dados["resumo"].total_previsto == 1
    assert dados["resumo"].percentual_avanco == pytest.approx(100)
    assert dados["total_documentos_id"] == 2
    contagem_cancelados = next(
        item["quantidade"]
        for item in dados["fora_do_painel"]
        if item["grupo"].id == "cancelado"
    )
    assert contagem_cancelados == 1
    assert aprovado.pk != cancelado.pk


@pytest.mark.django_db
def test_lista_mostra_cancelado_e_controles_somente_para_admin(
    client, contrato, perfil_modelo, admin_contrato, django_user_model
):
    documento = _documento(contrato, 1011)
    cancelar_documentos(admin_contrato, contrato, [documento.pk], "cliente")
    equipe = django_user_model.objects.create_user(username="equipe-lista", password="senha")
    Participacao.objects.create(usuario=equipe, contrato=contrato, papel=Usuario.Perfil.EQUIPE)

    client.force_login(admin_contrato)
    resposta_admin = client.get(reverse("documentos_lista"), {"contrato": contrato.pk})
    assert resposta_admin.status_code == 200
    assert "Cancelar selecionados" in resposta_admin.content.decode()
    assert 'name="documento"' in resposta_admin.content.decode()
    assert "Cancelado" in resposta_admin.content.decode()

    client.force_login(equipe)
    resposta_equipe = client.get(reverse("documentos_lista"), {"contrato": contrato.pk})
    assert resposta_equipe.status_code == 200
    assert "Cancelar selecionados" not in resposta_equipe.content.decode()
    assert 'name="documento"' not in resposta_equipe.content.decode()


@pytest.mark.django_db
def test_pasta_exibe_faixa_e_botao_de_cancelamento(
    client, contrato, perfil_modelo, admin_contrato
):
    documento = _documento(contrato, 1017)
    client.force_login(admin_contrato)
    url = reverse("documento_pasta", args=(contrato.pk, documento.pk))

    antes = client.get(url)
    assert antes.status_code == 200
    assert "Cancelar documento" in antes.content.decode()

    cancelar_documentos(
        admin_contrato,
        contrato,
        [documento.pk],
        "outro",
        "Documento substituído por pacote consolidado",
    )
    depois = client.get(url)
    html = depois.content.decode()

    assert depois.status_code == 200
    assert "Cancelado em" in html
    assert "Ana Administradora" in html
    assert "Outro" in html
    assert "Documento substituído por pacote consolidado" in html


@pytest.mark.django_db
def test_confirmacao_mostra_codigos_e_motivos(
    client, contrato, perfil_modelo, admin_contrato
):
    documentos = [_documento(contrato, 1012), _documento(contrato, 1013)]
    client.force_login(admin_contrato)

    resposta = client.get(
        reverse("documentos_cancelar", args=(contrato.pk,)),
        {
            "documento": [documento.pk for documento in documentos],
            "lista_query": f"contrato={contrato.pk}&q=DE-15.25",
        },
    )

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert all(documento.identificador_base in html for documento in documentos)
    assert "Tem certeza? Estes 2 documentos deixam de contar no 100%." in html
    assert "Desmembrado em outros documentos" in html


@pytest.mark.django_db
def test_cancelamento_agrupa_evento_na_atividade_e_na_pasta(
    contrato, perfil_modelo, admin_contrato
):
    documentos = [_documento(contrato, 1014), _documento(contrato, 1015)]
    cancelar_documentos(
        admin_contrato,
        contrato,
        [documento.pk for documento in documentos],
        "desmembrado",
        "Novo conjunto de desenhos",
    )

    eventos = [evento for evento in carregar_eventos(contrato) if evento["acao"] == "cancelou"]
    assert len(eventos) == 1
    assert eventos[0]["resumo"] == "Cancelado por Ana Administradora · Desmembrado em outros documentos"
    assert all(documento.identificador_base in eventos[0]["codigo"] for documento in documentos)
    assert "Novo conjunto de desenhos" in str(eventos[0]["detalhes"])

    pasta = carregar_pasta_documento(admin_contrato, contrato.pk, documentos[0].pk)
    assert any("Cancelado por Ana Administradora" in item["resumo"] for item in pasta["atividades"])


@pytest.mark.django_db
def test_importacao_pw_registra_codigos_que_trouxe_como_cancelados(
    contrato, perfil_modelo, admin_contrato
):
    documento = _documento(contrato, 1016)
    emissao = Emissao.objects.create(
        documento=documento,
        revisao="1",
        versao=1,
        fase=Emissao.Fase.PRELIMINAR,
        data_emissao=timezone.localdate() - timedelta(days=5),
        origem=Emissao.Origem.CLIENTE,
    )
    importacao = ImportacaoSituacao.objects.create(
        contrato=contrato,
        data_extracao=timezone.localdate(),
        arquivo_nome="pw-cancelados.xlsx",
        importado_por=admin_contrato,
        documentos=1,
    )
    analise = Analise(
        emissao=emissao,
        etapa="Análise do cliente",
        situacao="Cancelado",
        origem=Analise.Origem.IMPORTADO_PW,
        data_analise=timezone.localdate(),
    )
    analise._history_user = admin_contrato
    analise._change_reason = f"importacao_situacao:{importacao.pk}"
    analise.save()

    evento = next(
        item
        for item in carregar_eventos(contrato)
        if item["chave"] == f"importacao-situacao-{importacao.pk}"
    )

    detalhes = " ".join(item["depois"] for item in evento["detalhes"])
    assert "1 documentos cancelados pelo PW" in detalhes
    assert documento.identificador_base in detalhes


def test_perfil_spobras_permanece_valido():
    with (PASTA_EXEMPLOS / "spobras.yaml").open(encoding="utf-8") as arquivo:
        perfil = perfil_de_dict(yaml.safe_load(arquivo))

    assert any(grupo.id == "cancelado" for grupo in perfil.painel.grupos)
