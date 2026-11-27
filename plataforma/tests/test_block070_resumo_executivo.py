from datetime import timedelta
from pathlib import Path

import pytest
import yaml
from django.urls import reverse
from django.utils import timezone

from acoes.services import carregar_resumo_inicio
from contas.models import Usuario
from contratos.models import Contrato, Participacao, PerfilContrato
from documentos.models import Analise, Documento, Emissao
from importacoes.models import ImportacaoID, ImportacaoSituacao, IndiceDocumentos, ItemPrevisto
from painel.servicos import carregar_painel, carregar_resumo_executivo


PERFIL_METRO = Path(__file__).resolve().parents[2] / "core" / "perfil" / "exemplos" / "metro.yaml"


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato de resumo",
        codigo_interno="CT-RESUMO",
        cliente="Cliente de teste",
    )


@pytest.fixture
def perfil_modelo(contrato):
    with PERFIL_METRO.open(encoding="utf-8") as arquivo:
        definicao = yaml.safe_load(arquivo)
    inicio = timezone.localdate() - timedelta(days=30)
    definicao["vigencia_inicio"] = inicio.isoformat()
    return PerfilContrato.objects.create(
        contrato=contrato,
        versao=1,
        vigencia_inicio=inicio,
        definicao=definicao,
    )


@pytest.fixture
def participante(contrato, django_user_model):
    pessoa = django_user_model.objects.create_user(
        username="participante-resumo",
        password="senha-segura",
    )
    Participacao.objects.create(
        usuario=pessoa,
        contrato=contrato,
        papel=Usuario.Perfil.CHEFIA,
        ativo=True,
    )
    return pessoa


def _indice(contrato):
    return IndiceDocumentos.objects.create(
        contrato=contrato,
        codigo="ID-RESUMO",
        arquivo_nome="ID.xlsx",
        importado_em=timezone.now(),
        fonte=IndiceDocumentos.Fonte.EXCEL_ID,
    )


def _documento(
    contrato,
    codigo,
    *,
    indice=None,
    situacao=None,
    revisao="1",
    data_emissao=None,
    data_analise=None,
    com_emissao=False,
    classe="P7",
    trecho="25",
):
    documento = Documento.objects.create(
        contrato=contrato,
        identificador_base=codigo,
        tipo="DE",
        trecho=trecho,
        disciplina=classe,
        titulo=f"Documento {codigo}",
        atributos={
            "tipo": "DE",
            "trecho": trecho,
            "etapa": "6",
            "classe": classe,
            "sequencial": codigo[-4:],
        },
    )
    if indice:
        ItemPrevisto.objects.create(indice=indice, documento=documento, titulo=documento.titulo)
    if situacao is not None or com_emissao:
        data_emissao = data_emissao or timezone.localdate() - timedelta(days=10)
        emissao = Emissao.objects.create(
            documento=documento,
            revisao=revisao,
            versao=1,
            fase=Emissao.Fase.PRELIMINAR,
            data_emissao=data_emissao,
            origem=Emissao.Origem.CLIENTE,
        )
        if situacao is not None:
            Analise.objects.create(
                emissao=emissao,
                etapa="Análise do cliente",
                situacao=situacao,
                origem=Analise.Origem.IMPORTADO_PW,
                data_analise=data_analise or data_emissao + timedelta(days=1),
            )
    return documento


@pytest.mark.django_db
def test_numeros_do_resumo_reutilizam_o_painel_e_as_pendencias(
    contrato, perfil_modelo, participante
):
    indice = _indice(contrato)
    _documento(contrato, "DOC-1001", indice=indice, situacao="Aprovado")
    _documento(contrato, "DOC-1002", indice=indice, situacao="Em Análise")
    _documento(contrato, "DOC-1003", indice=indice)
    _documento(contrato, "DOC-1004", indice=indice, situacao="Não Aprovado")
    _documento(contrato, "DOC-1005", indice=indice, situacao="Cancelado")
    importacao_id = ImportacaoID.objects.create(
        contrato=contrato,
        indice=indice,
        arquivo_nome="ID.xlsx",
    )
    data_id = timezone.localtime(importacao_id.importado_em).date()
    data_situacao = timezone.localdate() - timedelta(days=1)
    ImportacaoSituacao.objects.create(
        contrato=contrato,
        data_extracao=data_situacao,
        arquivo_nome="situacao.xlsx",
    )

    painel = carregar_painel(contrato)
    resumo = carregar_resumo_executivo(contrato, participante)
    pendencias = carregar_resumo_inicio(participante, contrato.pk)
    grupos_sem_emissao = [grupo for grupo in painel["resumo"].grupos if grupo.sem_emissao]
    cancelados = sum(
        item["quantidade"]
        for item in painel["fora_do_painel"]
        if item["grupo"].id == "cancelado"
    )

    assert resumo["avanco_percentual"] == painel["resumo"].percentual_avanco
    assert resumo["previstos"] == painel["total_documentos_previstos"] == 4
    assert resumo["pendentes"] == sum(
        painel["resumo"].contagens[grupo.id] for grupo in grupos_sem_emissao
    ) == 1
    assert resumo["emitidos"] == 3
    assert resumo["aprovados"] == painel["resumo"].contagens["aprovado"] == 1
    assert resumo["em_analise"] == painel["resumo"].contagens["em_analise"] == 1
    assert resumo["cancelados"] == cancelados == 1
    assert resumo["ultima_importacao_id"] == data_id
    assert resumo["ultima_importacao_situacao"] == data_situacao
    assert resumo["pendencias_abertas"] == sum(
        card["quantidade"] for card in pendencias["cards_janelas"]
    )


@pytest.mark.django_db
def test_atrasos_separados_por_lado_e_lista_dos_cinco_mais_antigos(
    contrato, perfil_modelo, participante
):
    hoje = timezone.localdate()
    regras = perfil_modelo.definicao["prazos"]["regras"]
    regras[0].update(dias=1, tipo_dia="corridos")
    regras[1]["dias"] = 1
    perfil_modelo.save(update_fields=("definicao",))

    for indice, dias in enumerate((9, 19, 29), start=1):
        _documento(
            contrato,
            f"DOC-C-{indice:04d}",
            com_emissao=True,
            data_emissao=hoje - timedelta(days=dias + 2),
        )
    for indice, dias in enumerate((12, 22, 32), start=1):
        _documento(
            contrato,
            f"DOC-N-{indice:04d}",
            situacao="Não Aprovado",
            revisao=str(indice),
            data_emissao=hoje - timedelta(days=dias + 3),
            data_analise=hoje - timedelta(days=dias + 2),
        )

    resumo = carregar_resumo_executivo(contrato, participante, hoje=hoje)

    assert resumo["atrasos_cliente"] == 3
    assert resumo["atrasos_nossos"] == 3
    assert len(resumo["atrasos_mais_antigos"]) == 5
    dias_em_ordem = [item["dias"] for item in resumo["atrasos_mais_antigos"]]
    assert dias_em_ordem == sorted(dias_em_ordem, reverse=True)
    assert all({"codigo", "revisao", "dias"} == set(item) for item in resumo["atrasos_mais_antigos"])


@pytest.mark.django_db
def test_usuario_sem_participacao_nao_acessa_o_resumo(
    client, contrato, perfil_modelo, django_user_model
):
    externo = django_user_model.objects.create_user(username="externo-resumo", password="senha")
    client.force_login(externo)

    resposta = client.get(reverse("resumo_executivo", args=(contrato.pk,)))

    assert resposta.status_code == 403


@pytest.mark.django_db
def test_painel_exibe_link_do_resumo_para_participante(
    client, contrato, perfil_modelo, participante
):
    client.force_login(participante)

    resposta = client.get(reverse("painel", args=(contrato.pk,)))

    assert resposta.status_code == 200
    assert reverse("resumo_executivo", args=(contrato.pk,)) in resposta.content.decode()


@pytest.mark.django_db
def test_tabelas_limitam_a_doze_maiores_linhas_e_informam_o_restante(
    client, contrato, perfil_modelo, participante
):
    indice = _indice(contrato)
    for numero in range(14):
        _documento(
            contrato,
            f"DOC-{numero:04d}",
            indice=indice,
            situacao="Aprovado",
            trecho=f"{numero:02d}",
        )
    client.force_login(participante)

    dados = carregar_resumo_executivo(contrato, participante)
    resposta = client.get(reverse("resumo_executivo", args=(contrato.pk,)))

    assert len(dados["por_trecho"]["linhas"]) == 12
    assert dados["por_trecho"]["linhas_omitidas"] == 2
    assert "e mais 2" in resposta.content.decode()
