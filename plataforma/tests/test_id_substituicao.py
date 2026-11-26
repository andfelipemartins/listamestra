from datetime import date
from io import BytesIO
from pathlib import Path

import pytest
import yaml
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook

from core.perfil import perfil_de_dict
from contratos.models import Contrato, PerfilContrato
from documentos.models import Documento, Emissao
from importacoes.id_excel import FORMATOS_ID, gerar_previa_id
from importacoes.models import IndiceDocumentos, ItemPrevisto
from importacoes.services import aplicar_previa, previstos_vigentes, resumir_substituicao


METRO = Path(__file__).resolve().parents[2] / "core" / "perfil" / "exemplos" / "metro.yaml"


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato para substituição",
        codigo_interno="CT-SUB",
        cliente="Cliente de teste",
    )


@pytest.fixture
def perfil_modelo(contrato):
    with METRO.open(encoding="utf-8") as arquivo:
        definicao = yaml.safe_load(arquivo)
    definicao["vigencia_inicio"] = date(2026, 1, 1).isoformat()
    return PerfilContrato.objects.create(
        contrato=contrato,
        versao=1,
        vigencia_inicio=date(2026, 1, 1),
        definicao=definicao,
    )


def _excel(linhas):
    formato = FORMATOS_ID["excel_id"]
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = formato["planilha"]
    worksheet.append([
        formato["cabecalho_titulo"],
        *formato["cabecalhos_segmentos"].values(),
        formato["cabecalho_codigo"],
        formato["cabecalho_excluido"],
    ])
    for linha in linhas:
        worksheet.append([
            linha.get("titulo", "Título de teste"),
            linha.get("tipo", "DE"),
            linha.get("linha", "15"),
            linha.get("trecho", "25"),
            linha.get("subtrecho", "00"),
            linha.get("unidade", "00"),
            linha.get("etapa", "6"),
            linha.get("classe", "A1"),
            linha["sequencial"],
            linha.get("codigo"),
            linha.get("excluido", False),
        ])
    conteudo = BytesIO()
    workbook.save(conteudo)
    conteudo.seek(0)
    return conteudo


def _previa(arquivo, contrato, perfil_modelo, *, codigo, nome=None):
    return gerar_previa_id(
        arquivo,
        nome_arquivo=nome or f"{codigo}.xlsx",
        contrato_id=contrato.pk,
        perfil_id=perfil_modelo.pk,
        perfil=perfil_de_dict(perfil_modelo.definicao),
        documentos_existentes=list(
            Documento.objects.filter(contrato=contrato).values_list("identificador_base", "titulo")
        ),
        codigo_indice=codigo,
        revisao="1",
        data_importacao=timezone.localdate(),
    )


def _importar(contrato, perfil_modelo, codigo, sequenciais, **kwargs):
    previa = _previa(
        _excel([{"sequencial": sequencial} for sequencial in sequenciais]),
        contrato,
        perfil_modelo,
        codigo=codigo,
    )
    return aplicar_previa(
        previa,
        contrato=contrato,
        perfil_modelo=perfil_modelo,
        **kwargs,
    )


@pytest.mark.django_db
def test_substituicao_atualiza_vigencia_historico_previsto_e_movimentacao(
    contrato, perfil_modelo, django_user_model
):
    usuario = django_user_model.objects.create_user(
        username="admin-substituicao",
        email="admin-substituicao@example.com",
        password="senha-segura",
        is_staff=True,
    )
    antigo = _importar(contrato, perfil_modelo, "ID-ANTIGO", ["1001", "1501", "1502"])
    documento_com_movimentacao = ItemPrevisto.objects.get(
        indice=antigo,
        documento__identificador_base__endswith="1501",
    ).documento
    Emissao.objects.create(
        documento=documento_com_movimentacao,
        revisao="1",
        versao=1,
        fase=Emissao.Fase.PRELIMINAR,
        data_emissao=date(2026, 11, 20),
        origem=Emissao.Origem.CLIENTE,
    )
    previa_nova = _previa(
        _excel([{"sequencial": codigo} for codigo in ("1001", "2001", "2002")]),
        contrato,
        perfil_modelo,
        codigo="ID-NOVO",
    )

    resumo = resumir_substituicao(previa_nova, [antigo])
    novo = aplicar_previa(
        previa_nova,
        contrato=contrato,
        perfil_modelo=perfil_modelo,
        usuario=usuario,
        substituir_ids=[antigo.pk],
    )
    antigo.refresh_from_db()

    assert (resumo["continuam"], resumo["entram"], resumo["saem"]) == (1, 2, 2)
    assert len(resumo["codigos_que_saem"]) == 2
    assert resumo["codigos_com_movimentacao"] == [documento_com_movimentacao.identificador_base]
    assert not antigo.vigente
    assert antigo.substituido_por_id == novo.pk
    historico = antigo.history.filter(vigente=False, substituido_por_id=novo.pk).first()
    assert historico.history_user == usuario
    assert historico.history_date is not None
    assert f"substituido_por:{novo.pk}" in historico.history_change_reason
    assert {item.documento.identificador_base for item in previstos_vigentes(contrato)} == {
        linha.identificador_base for linha in previa_nova.linhas
    }


@pytest.mark.django_db
def test_importacao_sem_substituicao_mantem_os_ids_vigentes(contrato, perfil_modelo):
    antigo = _importar(contrato, perfil_modelo, "ID-ANTIGO", ["1001", "1501"])
    novo = _importar(contrato, perfil_modelo, "ID-NOVO", ["1001", "2001"])

    antigo.refresh_from_db()
    assert antigo.vigente
    assert novo.vigente
    assert antigo.substituido_por_id is None
    assert {item.documento.identificador_base for item in previstos_vigentes(contrato)} == {
        "DE-15.25.00.00-6A1-1001",
        "DE-15.25.00.00-6A1-1501",
        "DE-15.25.00.00-6A1-2001",
    }


@pytest.mark.django_db
def test_previa_e_confirmacao_mostram_substituicao_e_aviso_de_movimentacao(
    client, contrato, perfil_modelo, django_user_model
):
    administrador = django_user_model.objects.create_superuser(
        username="admin-tela-substituicao",
        email="admin-tela-substituicao@example.com",
        password="senha-segura",
    )
    client.force_login(administrador)
    antigo = _importar(contrato, perfil_modelo, "ID-ANTIGO", ["1001", "1501"])
    documento = ItemPrevisto.objects.get(
        indice=antigo,
        documento__identificador_base__endswith="1501",
    ).documento
    Emissao.objects.create(
        documento=documento,
        revisao="1",
        versao=1,
        fase=Emissao.Fase.PRELIMINAR,
        data_emissao=date(2026, 11, 20),
        origem=Emissao.Origem.CLIENTE,
    )
    arquivo = _excel([{"sequencial": "1001"}, {"sequencial": "2001"}])
    resposta = client.post(
        reverse("importar_id"),
        {
            "acao": "prever",
            "contrato": str(contrato.pk),
            "codigo_id": "ID-NOVO",
            "revisao": "1",
            "substituidos": [str(antigo.pk)],
            "arquivo": SimpleUploadedFile(
                "ID-NOVO.xlsx",
                arquivo.read(),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        },
        HTTP_HX_REQUEST="true",
    )

    assert resposta.status_code == 200
    assert "1 documentos continuam, 1 entram e 1 saem" in resposta.content.decode()
    assert documento.identificador_base in resposta.content.decode()
    resposta_confirmacao = client.post(
        reverse("importar_id"), {"acao": "confirmar"}, follow=True
    )

    antigo.refresh_from_db()
    assert not antigo.vigente
    html_confirmacao = resposta_confirmacao.content.decode()
    assert "Aviso: código saiu do ID vigente e possui movimentação" in html_confirmacao
    assert documento.identificador_base in html_confirmacao
    resposta_lista = client.get(reverse("importar_id"), {"contrato": str(contrato.pk)})
    html = resposta_lista.content.decode()
    assert "Histórico — substituído pelo ID-NOVO" in html
    assert "admin-tela-substituicao" in html


@pytest.mark.django_db
def test_permissao_da_substituicao_e_a_mesma_da_importacao_id(
    client, django_user_model
):
    usuario = django_user_model.objects.create_user(
        username="participante-substituicao",
        email="participante-substituicao@example.com",
        password="senha-segura",
    )
    client.force_login(usuario)

    assert client.get(reverse("importar_id")).status_code == 403
