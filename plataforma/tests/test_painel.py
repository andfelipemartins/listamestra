from datetime import date, timedelta
from pathlib import Path
import json
import re

import pytest
import yaml
from django.contrib.auth.hashers import check_password
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse
from django.utils import timezone

from contratos.admin import ContratoAdminForm
from contratos.models import Contrato, Participacao, PerfilContrato
from documentos.models import Analise, Documento, Emissao
from importacoes.models import (
    InconsistenciaImportacao,
    ImportacaoCronograma,
    ImportacaoID,
    ImportacaoSituacao,
    IndiceDocumentos,
    ItemPrevisto,
    PrevisaoEmissao,
)
from painel.servicos import carregar_painel


METRO = Path(__file__).resolve().parents[2] / "core" / "perfil" / "exemplos" / "metro.yaml"


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato de painel",
        codigo_interno="CT-PAINEL",
        cliente="Cliente de teste",
    )


@pytest.fixture
def perfil_modelo(contrato):
    with METRO.open(encoding="utf-8") as arquivo:
        definicao = yaml.safe_load(arquivo)
    definicao["vigencia_inicio"] = (timezone.localdate() - timedelta(days=30)).isoformat()
    return PerfilContrato.objects.create(
        contrato=contrato,
        versao=1,
        vigencia_inicio=timezone.localdate() - timedelta(days=30),
        definicao=definicao,
    )


def _indice(
    contrato,
    codigo,
    *,
    fonte=IndiceDocumentos.Fonte.EXCEL_ID,
    revisao="1",
    fase="",
    escopo="",
    conta_no_previsto=True,
):
    return IndiceDocumentos.objects.create(
        contrato=contrato,
        codigo=codigo,
        revisao=revisao,
        fase=fase,
        escopo=escopo,
        conta_no_previsto=conta_no_previsto,
        fonte=fonte,
        arquivo_nome=f"{codigo}.xlsx",
        importado_em=timezone.now(),
    )


def _documento(
    contrato,
    indice,
    sequencial,
    classe="P7",
    situacao=None,
    *,
    tipo="DE",
    trecho="25",
    etapa="6",
    data=None,
):
    data = data or timezone.localdate() - timedelta(days=10)
    identificador = f"DOC-{sequencial}"
    documento = Documento.objects.create(
        contrato=contrato,
        identificador_base=identificador,
        tipo=tipo,
        trecho=trecho,
        disciplina=classe,
        titulo=f"Documento {sequencial}",
        atributos={
            "tipo": tipo,
            "trecho": trecho,
            "etapa": etapa,
            "classe": classe,
            "sequencial": str(sequencial),
        },
    )
    ItemPrevisto.objects.create(indice=indice, documento=documento, titulo=documento.titulo)
    if situacao is not None:
        emissao = Emissao.objects.create(
            documento=documento,
            revisao="1",
            versao=1,
            fase=Emissao.Fase.PRELIMINAR,
            data_emissao=data,
            origem=Emissao.Origem.CLIENTE,
        )
        Analise.objects.create(
            emissao=emissao,
            etapa="Análise do cliente",
            situacao=situacao,
            origem=Analise.Origem.IMPORTADO_PW,
            data_analise=data + timedelta(days=1),
        )
    return documento


def _emissao_com_status(
    documento, revisao, situacao, *, fase=Emissao.Fase.PRELIMINAR, versao=1
):
    data = timezone.localdate() - timedelta(days=10)
    emissao = Emissao.objects.create(
        documento=documento,
        revisao=str(revisao),
        versao=versao,
        fase=fase,
        data_emissao=data,
        origem=Emissao.Origem.CLIENTE,
    )
    Analise.objects.create(
        emissao=emissao,
        etapa="Análise do cliente",
        situacao=situacao,
        origem=Analise.Origem.IMPORTADO_PW,
        data_analise=data + timedelta(days=1),
    )
    return emissao


def _previsoes_cronograma(contrato, previsoes):
    importacao = ImportacaoCronograma.objects.create(
        contrato=contrato,
        arquivo_nome="cronograma.xlsx",
        linhas_validas=len(previsoes),
    )
    return [
        PrevisaoEmissao.objects.create(
            contrato=contrato,
            documento=documento,
            data_prevista=data_prevista,
            importacao=importacao,
        )
        for documento, data_prevista in previsoes
    ]


@pytest.mark.django_db
def test_servico_resume_uniao_status_recorte_fonte_e_fora_do_id(contrato, perfil_modelo):
    primeira = _indice(contrato, "ID-A")
    segunda = _indice(contrato, "ID-B")
    _documento(contrato, primeira, 1001, classe="A1")
    _documento(contrato, primeira, 1002, classe="A1", situacao="Em Análise")
    aprovado = _documento(contrato, primeira, 1003, situacao="Aprovado")
    _documento(contrato, primeira, 1004, situacao="Não Aprovado")
    desconhecido = _documento(contrato, primeira, 1005, situacao="Estado Novo do PW")
    ItemPrevisto.objects.create(indice=segunda, documento=aprovado, titulo=aprovado.titulo)
    _documento(contrato, segunda, 1006, classe="P7", situacao="Aprovado")
    fora_id = Documento.objects.create(
        contrato=contrato,
        identificador_base="DOC-FORA-ID",
        atributos={"tipo": "DE", "trecho": "25", "classe": "P7"},
    )
    emissao = Emissao.objects.create(
        documento=fora_id,
        revisao="1",
        versao=1,
        fase=Emissao.Fase.PRELIMINAR,
        data_emissao=timezone.localdate() - timedelta(days=2),
        origem=Emissao.Origem.CLIENTE,
    )
    Analise.objects.create(emissao=emissao, etapa="Análise", situacao="Em Análise")

    data_pw = timezone.localdate() - timedelta(days=1)
    ImportacaoSituacao.objects.create(
        contrato=contrato,
        data_extracao=data_pw,
        arquivo_nome="PW.xlsx",
    )
    importacao_id = ImportacaoID.objects.create(
        contrato=contrato,
        indice=primeira,
        arquivo_nome="ID.xlsx",
    )
    data_id = timezone.localtime(importacao_id.importado_em).date()

    dados = carregar_painel(contrato, "classe")
    resumo = dados["resumo"]

    assert dados["total_documentos_previstos"] == 6
    assert resumo.total_previsto == 6
    assert resumo.contagens["a_emitir"] == 1
    assert resumo.contagens["em_analise"] == 1
    assert resumo.contagens["aprovado"] == 2
    assert resumo.contagens["nao_aprovado"] == 1
    assert resumo.contagens["nao_mapeado"] == 1
    assert resumo.percentual_avanco == pytest.approx(100 / 3)
    assert dados["fora_do_id"] == 1
    assert dados["ultima_situacao_pw"] == data_pw
    assert dados["ultima_importacao_id"] == data_id
    assert dados["por"] == "classe"
    assert any(item["rotulo"] == "Iluminação" for item in dados["recortes"])
    assert any(estado.situacao == "Estado Novo do PW" and estado.contagem == 1 for estado in resumo.estados_nao_mapeados)


@pytest.mark.django_db
def test_id_que_nao_conta_sai_do_total_sem_virar_fora_do_id(contrato, perfil_modelo):
    previsto = _indice(contrato, "ID-CONTA", fase="Fase 1")
    consulta = _indice(
        contrato,
        "ID-CONSULTA",
        fase="Fase 2",
        conta_no_previsto=False,
    )
    _documento(contrato, previsto, 9101, situacao="Aprovado")
    _documento(contrato, consulta, 9102, situacao="Aprovado")
    fora_dos_ids = Documento.objects.create(
        contrato=contrato,
        identificador_base="DOC-9103",
        tipo="DE",
        trecho="25",
        disciplina="P7",
        atributos={"tipo": "DE", "trecho": "25", "classe": "P7"},
    )
    _emissao_com_status(fora_dos_ids, 1, "Em Análise")

    dados = carregar_painel(contrato)

    assert dados["total_documentos_previstos"] == 1
    assert dados["total_documentos_id"] == 1
    assert dados["fora_do_id"] == 1


@pytest.mark.django_db
def test_fase_filtra_o_previsto_e_documento_compartilhado_entra_em_ambas(contrato, perfil_modelo):
    fase_1 = _indice(contrato, "ID-FASE-1", fase="Fase 1")
    fase_2 = _indice(contrato, "ID-FASE-2", fase="Fase 2")
    compartilhado = _documento(contrato, fase_1, 9201, situacao="Aprovado")
    ItemPrevisto.objects.create(
        indice=fase_2,
        documento=compartilhado,
        titulo=compartilhado.titulo,
    )
    _documento(contrato, fase_1, 9202, situacao="Em Análise")
    _documento(contrato, fase_2, 9203, situacao="Em Análise")

    geral = carregar_painel(contrato)
    por_fase = carregar_painel(contrato, por="fase")
    recortes = {item["rotulo"]: item["total"] for item in por_fase["recortes"]}
    filtro_fase = carregar_painel(contrato, filtros={"fase": "Fase 1"})

    assert geral["total_documentos_previstos"] == 3
    assert filtro_fase["total_documentos_previstos"] == 2
    assert filtro_fase["total_documentos_id"] == 2
    assert filtro_fase["filtros_ativos"] == [{"rotulo": "Fase", "valores": ["Fase 1"]}]
    assert recortes == {"Fase 1": 2, "Fase 2": 2}
    assert any(filtro["nome"] == "fase" for filtro in por_fase["filtros"])
    assert any(caixa.nome == "fase" and caixa.rotulo == "Fase" for caixa in por_fase["caixas"])


@pytest.mark.django_db
def test_sem_fases_configuradas_preserva_o_previsto_padrao(contrato, perfil_modelo):
    indice = _indice(contrato, "ID-SEM-FASE")
    _documento(contrato, indice, 9301)
    _documento(contrato, indice, 9302)

    dados = carregar_painel(contrato)

    assert dados["total_documentos_previstos"] == 2
    assert all(filtro["nome"] != "fase" for filtro in dados["filtros"])
    assert all(caixa.nome != "fase" for caixa in dados["caixas"])


@pytest.mark.django_db
def test_escopo_filtra_previsto_e_documento_compartilhado_entra_nos_dois(contrato, perfil_modelo):
    civil = _indice(contrato, "ID-CIVIL", fase="Fase 1", escopo="Arquitetura e civil")
    sistemas = _indice(contrato, "ID-SISTEMAS", fase="Fase 1", escopo="Sistemas")
    qualidade = _indice(contrato, "ID-QUALIDADE", fase="Fase 2", escopo="Qualidade")
    sem_escopo = _indice(contrato, "ID-SEM-ESCOPO", fase="Fase 1")
    compartilhado = _documento(contrato, civil, 9401, situacao="Aprovado")
    ItemPrevisto.objects.create(
        indice=sistemas,
        documento=compartilhado,
        titulo=compartilhado.titulo,
    )
    _documento(contrato, civil, 9402, situacao="Em Análise")
    _documento(contrato, sistemas, 9403, situacao="Em Análise")
    _documento(contrato, qualidade, 9404, situacao="Em Análise")
    _documento(contrato, sem_escopo, 9405, situacao="Em Análise")

    geral = carregar_painel(contrato)
    por_escopo = carregar_painel(contrato, por="escopo")
    recortes = {item["rotulo"]: item["total"] for item in por_escopo["recortes"]}
    filtrado = carregar_painel(contrato, filtros={"escopo": "Sistemas"})
    combinado = carregar_painel(
        contrato,
        filtros={"fase": "Fase 1", "escopo": "Sistemas"},
    )
    sem_escopo_filtrado = carregar_painel(
        contrato,
        filtros={"escopo": "__sem_escopo__"},
    )
    opcoes_escopo = next(filtro for filtro in geral["filtros"] if filtro["nome"] == "escopo")["opcoes"]

    assert geral["total_documentos_previstos"] == 5
    assert recortes == {
        "Arquitetura e civil": 2,
        "Qualidade": 1,
        "Sem escopo": 1,
        "Sistemas": 2,
    }
    assert filtrado["total_documentos_previstos"] == 2
    assert filtrado["filtros_ativos"] == [
        {"rotulo": "Escopo do ID", "valores": ["Sistemas"]}
    ]
    assert combinado["total_documentos_previstos"] == 2
    assert sem_escopo_filtrado["total_documentos_previstos"] == 1
    assert any(opcao["rotulo"] == "Sem escopo" for opcao in opcoes_escopo)
    assert any(caixa.nome == "escopo" and caixa.rotulo == "Escopo do ID" for caixa in por_escopo["caixas"])


@pytest.mark.django_db
def test_um_escopo_unico_nao_mostra_filtro_e_painel_abre_no_total(contrato, perfil_modelo):
    indice = _indice(contrato, "ID-ESCOPO-UNICO", fase="Fase 1", escopo="Civil")
    _documento(contrato, indice, 9501)
    _documento(contrato, indice, 9502)

    dados = carregar_painel(contrato)

    assert dados["total_documentos_previstos"] == 2
    assert all(filtro["nome"] != "escopo" for filtro in dados["filtros"])
    assert all(caixa.nome != "escopo" for caixa in dados["caixas"])
    assert dados["filtros_ativos"] == []


@pytest.mark.django_db
def test_servico_usa_analise_mais_recente_da_emissao_mais_recente(contrato, perfil_modelo):
    indice = _indice(contrato, "ID-REVISOES")
    documento = _documento(contrato, indice, 2001)
    emissao_antiga = Emissao.objects.create(
        documento=documento,
        revisao="1",
        versao=1,
        fase=Emissao.Fase.PRELIMINAR,
        data_emissao=timezone.localdate() - timedelta(days=20),
        origem=Emissao.Origem.CLIENTE,
    )
    Analise.objects.create(
        emissao=emissao_antiga,
        etapa="Análise do cliente",
        situacao="Aprovado",
        data_analise=timezone.localdate() - timedelta(days=1),
    )
    emissao_nova = Emissao.objects.create(
        documento=documento,
        revisao="2",
        versao=1,
        fase=Emissao.Fase.PRELIMINAR,
        data_emissao=timezone.localdate() - timedelta(days=5),
        origem=Emissao.Origem.CLIENTE,
    )
    Analise.objects.create(
        emissao=emissao_nova,
        etapa="Análise do cliente",
        situacao="Em Análise",
        data_analise=timezone.localdate() - timedelta(days=4),
    )
    Analise.objects.create(
        emissao=emissao_nova,
        etapa="Análise do cliente",
        situacao="Não Aprovado",
        data_analise=timezone.localdate() - timedelta(days=3),
    )

    resumo = carregar_painel(contrato)["resumo"]

    assert resumo.contagens["nao_aprovado"] == 1
    assert resumo.contagens["aprovado"] == 0


@pytest.mark.django_db
def test_cancelado_fica_fora_da_conta_dos_graficos_e_cartoes(contrato, perfil_modelo, client, django_user_model):
    usuario = django_user_model.objects.create_user(username="chefia-cancelados", password="senha")
    Participacao.objects.create(usuario=usuario, contrato=contrato, papel="chefia")
    indice = _indice(contrato, "ID-CANCELADOS")
    _documento(contrato, indice, 3001)
    _documento(contrato, indice, 3002, situacao="Aprovado")
    _documento(contrato, indice, 3003, situacao="Cancelado")
    client.force_login(usuario)

    dados = carregar_painel(contrato)
    resposta = client.get(reverse("painel", args=(contrato.pk,)))
    html = resposta.content.decode()
    pizza = json.loads(re.search(r'<script id="dados-grafico-pizza" type="application/json">(.*?)</script>', html).group(1))
    barras = json.loads(re.search(r'<script id="dados-grafico-recortes" type="application/json">(.*?)</script>', html).group(1))

    assert dados["resumo"].total_previsto == 2
    assert dados["total_documentos_previstos"] == 2
    assert dados["total_documentos_id"] == 3
    assert dados["resumo"].percentual_avanco == pytest.approx(50)
    assert [(item["grupo"].rotulo, item["quantidade"]) for item in dados["fora_do_painel"]] == [("CANCELADO", 1)]
    assert "CANCELADO" not in pizza["labels"]
    assert "CANCELADO" not in [dataset["label"] for dataset in barras["datasets"]]
    assert "Cancelados: 1" in html
    assert "CANCELADO" not in [item["grupo"].rotulo for item in resposta.context["grupo_cards"]]
    assert {item["percentual"] for item in resposta.context["grupo_cards"] if item["quantidade"]} == {50.0}


@pytest.mark.django_db
def test_grupo_erro_fica_oculto_e_documentos_contam_na_situacao_anterior(
    contrato, perfil_modelo, client, django_user_model
):
    usuario = django_user_model.objects.create_user(username="chefia-erros", password="senha")
    Participacao.objects.create(usuario=usuario, contrato=contrato, papel="chefia")
    indice = _indice(contrato, "ID-ERROS")
    doc_nao_aprovado = _documento(contrato, indice, 3501, situacao="Não Aprovado")
    _emissao_com_status(doc_nao_aprovado, "2", "Erro de Assinatura")
    doc_aprovado = _documento(contrato, indice, 3502, situacao="Aprovado")
    _emissao_com_status(doc_aprovado, "2", "Em Desenvolvimento")
    _documento(contrato, indice, 3503, situacao="Inconsistente")
    _documento(contrato, indice, 3504, situacao="Não Conforme")
    client.force_login(usuario)

    resposta = client.get(reverse("painel", args=(contrato.pk,)))
    html = resposta.content.decode()
    pizza = json.loads(
        re.search(
            r'<script id="dados-grafico-pizza" type="application/json">(.*?)</script>',
            html,
        ).group(1)
    )
    barras = json.loads(
        re.search(
            r'<script id="dados-grafico-recortes" type="application/json">(.*?)</script>',
            html,
        ).group(1)
    )
    cards = {
        item["grupo"].id: item["quantidade"] for item in resposta.context["grupo_cards"]
    }

    assert resposta.status_code == 200
    assert "erro" not in cards
    assert cards["nao_aprovado"] == 1
    assert cards["aprovado"] == 1
    assert cards["inconsistente"] == 2
    assert resposta.context["total_documentos_previstos"] == 4
    assert "ERRO" not in pizza["labels"]
    assert "ERRO" not in [dataset["label"] for dataset in barras["datasets"]]
    assert "ERRO" not in html
    assert 'painel-grupo-label">INCONSISTENTE</span>' in html
    assert "INCONSISTENTE" in pizza["labels"]
    assert "INCONSISTENTE" in [dataset["label"] for dataset in barras["datasets"]]


@pytest.mark.django_db
def test_filtros_combinam_ou_na_mesma_caixa_e_e_entre_caixas(contrato, perfil_modelo):
    indice = _indice(contrato, "ID-FILTROS")
    _documento(contrato, indice, 4001, tipo="DE", trecho="25", classe="P7", etapa="6")
    _documento(contrato, indice, 4002, tipo="DE", trecho="23", classe="A1", etapa="5")
    _documento(contrato, indice, 4003, tipo="MC", trecho="25", classe="P7", etapa="5")
    _documento(contrato, indice, 4004, tipo="MC", trecho="23", classe="A1", etapa="6")

    simples = carregar_painel(contrato, filtros={"tipo": "MC"})
    multiplo = carregar_painel(contrato, filtros={"tipo": ["DE", "MC"]})
    combinado = carregar_painel(contrato, filtros={"tipo": "DE", "trecho": "23"})

    assert simples["total_documentos_previstos"] == 2
    assert multiplo["total_documentos_previstos"] == 4
    assert combinado["total_documentos_previstos"] == 1
    tipo = next(filtro for filtro in multiplo["filtros"] if filtro["nome"] == "tipo")
    assert {opcao["rotulo"] for opcao in tipo["opcoes"] if opcao["valor"] in {"DE", "MC"}} == {
        "DE – Desenho",
        "MC – Memorial de cálculo",
    }


@pytest.mark.django_db
def test_filtro_combina_com_recorte_de_barras(contrato, perfil_modelo):
    indice = _indice(contrato, "ID-FILTRO-RECORTE")
    _documento(contrato, indice, 5001, tipo="MC", trecho="25")
    _documento(contrato, indice, 5002, tipo="MC", trecho="23")
    _documento(contrato, indice, 5003, tipo="DE", trecho="25")

    dados = carregar_painel(contrato, por="trecho", filtros={"tipo": "MC"})

    assert dados["por"] == "trecho"
    assert {item["rotulo"]: item["total"] for item in dados["recortes"]} == {
        "São Mateus": 1,
        "Ragueb Chohfi": 1,
    }


@pytest.mark.django_db
def test_categorias_do_perfil_aparecem_em_cartoes_recortes_e_filtros(
    contrato, perfil_modelo, client, django_user_model
):
    usuario = django_user_model.objects.create_user(username="chefia-categorias", password="senha")
    Participacao.objects.create(usuario=usuario, contrato=contrato, papel="chefia")
    indice = _indice(contrato, "ID-CATEGORIAS")
    _documento(contrato, indice, 6101, tipo="PE", classe="B3")
    _documento(contrato, indice, 6102, tipo="DE", classe="A7", situacao="Em Análise")
    _documento(contrato, indice, 6103, tipo="DE", classe="B3", situacao="Aprovado")
    _documento(contrato, indice, 6104, tipo="DE", classe="P7")
    _documento(contrato, indice, 6105, tipo="DE", classe="C1")
    client.force_login(usuario)

    dados = carregar_painel(contrato, por="categoria")
    resposta = client.get(reverse("painel", args=(contrato.pk,)), {"por": "categoria"})
    cartoes = {item["rotulo"]: item for item in dados["categoria_cards"]}
    qualidade = {item["rotulo"]: item["quantidade"] for item in cartoes["QUALIDADE"]["grupos"]}
    filtro = next(item for item in dados["filtros"] if item["nome"] == "categoria")
    filtrado = carregar_painel(contrato, por="categoria", filtros={"categoria": "sistemas"})

    assert dados["por"] == "categoria"
    assert {nome: item["total"] for nome, item in cartoes.items()} == {
        "QUALIDADE": 2,
        "ARQUITETURA": 1,
        "SISTEMAS": 1,
        "CIVIL": 1,
    }
    assert qualidade["A EMITIR"] == 1
    assert qualidade["EM ANÁLISE"] == 1
    assert qualidade["APROVADO"] == 0
    assert {opcao["valor"] for opcao in filtro["opcoes"]} == {
        "qualidade",
        "arquitetura",
        "sistemas",
        "civil",
    }
    assert filtrado["total_documentos_previstos"] == 1
    assert {item["rotulo"]: item["total"] for item in filtrado["recortes"]} == {"SISTEMAS": 1}
    assert {item["rotulo"]: item["total"] for item in filtrado["categoria_cards"]}[
        "SISTEMAS"
    ] == 1
    html = resposta.content.decode()
    assert "Categoria" in html
    assert "QUALIDADE" in html


@pytest.mark.django_db
def test_categoria_sem_regra_e_sem_padrao_vai_para_outros(contrato, perfil_modelo):
    definicao = perfil_modelo.definicao
    definicao["painel"]["categorias"] = definicao["painel"]["categorias"][:-1]
    perfil_modelo.definicao = definicao
    perfil_modelo.save(update_fields=("definicao",))
    indice = _indice(contrato, "ID-CATEGORIA-OUTROS")
    _documento(contrato, indice, 6201, classe="C1")

    dados = carregar_painel(contrato, por="categoria")

    assert {item["rotulo"]: item["total"] for item in dados["categoria_cards"]}["Outros"] == 1
    assert {item["rotulo"]: item["total"] for item in dados["recortes"]} == {"Outros": 1}
    filtro = next(item for item in dados["filtros"] if item["nome"] == "categoria")
    assert {opcao["valor"] for opcao in filtro["opcoes"]} == {"__outros__"}


@pytest.mark.django_db
def test_indicador_mostra_distribuicao_vertical_e_linha_meta_no_limite(
    contrato, perfil_modelo, client, django_user_model
):
    usuario = django_user_model.objects.create_user(username="chefia-indicador", password="senha")
    Participacao.objects.create(usuario=usuario, contrato=contrato, papel="chefia")
    indice = _indice(contrato, "ID-INDICADOR")

    dentro = _documento(contrato, indice, 5101, trecho="25", situacao="Não Aprovado")
    _emissao_com_status(dentro, "2", "Não Aprovado")
    _emissao_com_status(dentro, "3", "Não Aprovado")
    _emissao_com_status(dentro, "0", "Aprovado", fase=Emissao.Fase.ORIGINAL)

    fora = _documento(contrato, indice, 5102, trecho="23", situacao="Não Aprovado")
    _emissao_com_status(fora, "2", "Não Aprovado")
    _emissao_com_status(fora, "3", "Não Aprovado")
    _emissao_com_status(fora, "4", "Não Aprovado")
    _emissao_com_status(fora, "5", "Não Aprovado")
    _emissao_com_status(fora, "0", "Aprovado", fase=Emissao.Fase.ORIGINAL)
    client.force_login(usuario)

    dados = carregar_painel(contrato, por="trecho")
    resposta = client.get(reverse("painel", args=(contrato.pk,)), {"por": "trecho"})
    html = resposta.content.decode()
    indicador = dados["indicadores_aprovacao"][0]
    assert indicador["tem_dados"] is True
    assert indicador["percentual"] == pytest.approx(50)
    assert {item["rotulo"]: item["percentual"] for item in indicador["recortes"]} == {
        "Ragueb Chohfi": 100,
        "São Mateus": 0,
    }
    assert "<strong>1 de 2</strong> aprovados até a Revisão 3 (50%)" in re.sub(
        r"\s+", " ", html
    )
    assert [faixa["rotulo"] for faixa in indicador["distribuicao"]] == [
        "Emissão Inicial", "Rev. 1", "Rev. 2", "Rev. 3", "Rev. 4", "Rev. 5+"
    ]
    assert [faixa["quantidade"] for faixa in indicador["distribuicao"]] == [
        0, 0, 1, 0, 1, 0
    ]
    assert indicador["configuracao"].meta_percentual is None
    assert '<svg role="img"' in html
    grafico_html = re.search(
        r'<svg role="img" aria-labelledby="painel-indicador-grafico-titulo-1.*?</svg>',
        html,
        re.S,
    ).group(0)
    assert 'stroke-dasharray="6 5"' in grafico_html
    grafico_svg = indicador["grafico_distribuicao"]
    assert grafico_svg["x_meta"] == pytest.approx(
        grafico_svg["esquerda"]
        + (grafico_svg["direita"] - grafico_svg["esquerda"]) * 4 / 6
    )
    linha_meta = re.search(
        r'<line x1="(?P<x1>[\d.,]+)" y1="[\d.,]+" x2="(?P<x2>[\d.,]+)" y2="[\d.,]+" '
        r'stroke="var\(--indicador-meta\)" stroke-width="2" stroke-dasharray="6 5" />',
        grafico_html,
    )
    assert linha_meta is not None
    assert float(linha_meta["x1"].replace(",", ".")) == pytest.approx(
        grafico_svg["x_meta"]
    )
    assert float(linha_meta["x2"].replace(",", ".")) == pytest.approx(
        grafico_svg["x_meta"]
    )
    rotulo_meta = re.search(
        r'<text x="(?P<x>[\d.,]+)" y="[\d.,]+" fill="var\(--indicador-meta\)" '
        r'font-size="11" font-weight="700">Meta</text>',
        grafico_html,
    )
    assert rotulo_meta is not None
    assert float(rotulo_meta["x"].replace(",", ".")) == pytest.approx(
        grafico_svg["x_meta"] + 5
    )
    assert "var(--blue)" in html
    assert "var(--indicador-alerta)" in html
    assert "Meta</th>" not in html
    assert "Dentro do limite: 1" in html
    assert "Fora do limite: 1" in html

    prazo_cliente = next(
        item
        for item in dados["indicadores_prazo"]
        if item["regra"].id == "analise_cliente"
    )
    assert prazo_cliente["tem_dados"] is True
    assert prazo_cliente["meta_percentual"] is None
    artigos_prazo = re.findall(
        r'<article class="painel-indicador" style="margin-top:0" '
        r'aria-labelledby="painel-prazo-titulo-\d+">(.*?)</article>',
        html,
        re.S,
    )
    artigo_cliente = next(
        artigo for artigo in artigos_prazo if "Análise do cliente</h3>" in artigo
    )
    assert "Linha tracejada: Meta" not in artigo_cliente
    assert "border-left:2px dashed var(--indicador-meta)" not in artigo_cliente


@pytest.mark.django_db
def test_indicador_conta_emissoes_de_versoes_diferentes_na_mesma_revisao(
    contrato, perfil_modelo
):
    indice = _indice(contrato, "ID-INDICADOR-VERSOES")
    documento = _documento(contrato, indice, 5151, situacao="Não Aprovado")
    _emissao_com_status(documento, "1", "Não Aprovado", versao=2)
    _emissao_com_status(documento, "2", "Não Aprovado", versao=1)
    _emissao_com_status(documento, "2", "Não Aprovado", versao=2)
    _emissao_com_status(documento, "3", "Aprovado", versao=1)

    dados = carregar_painel(contrato)
    indicador = dados["indicadores_aprovacao"][0]

    assert Emissao.objects.filter(documento=documento).count() == 5
    assert (indicador["dentro_limite"], indicador["fora_limite"]) == (0, 1)
    assert indicador["distribuicao"][4]["quantidade"] == 1


@pytest.mark.django_db
def test_indicador_mantem_distribuicao_e_tabela_por_recorte(
    contrato, perfil_modelo, client, django_user_model
):
    usuario = django_user_model.objects.create_user(
        username="chefia-indicador-recortes", password="senha"
    )
    Participacao.objects.create(usuario=usuario, contrato=contrato, papel="chefia")
    indice = _indice(contrato, "ID-INDICADOR-RECORTES")

    para_revisao = _documento(
        contrato, indice, 5201, tipo="DE", situacao="Não Aprovado"
    )
    _emissao_com_status(para_revisao, "2", "Não Aprovado")
    _emissao_com_status(para_revisao, "3", "Não Aprovado")
    _emissao_com_status(para_revisao, "4", "Não Aprovado")

    em_analise = _documento(
        contrato, indice, 5202, tipo="DG", situacao="Não Aprovado"
    )
    _emissao_com_status(em_analise, "2", "Não Aprovado")
    _emissao_com_status(em_analise, "3", "Não Aprovado")
    _emissao_com_status(em_analise, "4", "Não Aprovado")

    _documento(contrato, indice, 5203, tipo="RT", situacao="Aprovado")
    _documento(contrato, indice, 5204, tipo="MC")
    client.force_login(usuario)

    resposta = client.get(reverse("painel", args=(contrato.pk,)), {"por": "tipo"})
    html = resposta.content.decode()
    dados = carregar_painel(contrato, por="tipo")
    indicador = dados["indicadores_aprovacao"][0]
    por_recorte = {item["rotulo"]: item for item in indicador["recortes"]}

    assert por_recorte["Relatório técnico"]["distribuicao"][0]["quantidade"] == 1
    assert por_recorte["Desenho"]["base"] == 0
    assert sum(faixa["quantidade"] for faixa in por_recorte["Desenho"]["distribuicao"]) == 0
    texto = re.sub(r"\s+", " ", html)
    assert "Números do indicador por recorte" in texto
    assert "Emissão Inicial" in texto
    assert "Rev. 5+" in texto
    assert "Meta</th>" not in texto


@pytest.mark.django_db
def test_indicador_sem_recortes_com_base_mostra_sem_dados_no_grafico(
    contrato, perfil_modelo, client, django_user_model
):
    usuario = django_user_model.objects.create_user(
        username="chefia-indicador-sem-base", password="senha"
    )
    Participacao.objects.create(usuario=usuario, contrato=contrato, papel="chefia")
    indice = _indice(contrato, "ID-INDICADOR-SEM-BASE")
    _documento(contrato, indice, 5301, tipo="MC")
    client.force_login(usuario)

    resposta = client.get(reverse("painel", args=(contrato.pk,)), {"por": "tipo"})
    html = resposta.content.decode()

    assert resposta.status_code == 200
    assert '<svg role="img"' in html
    assert "<strong>Sem dados</strong>" in html
    assert "Memorial de cálculo" in html


@pytest.mark.django_db
def test_perfil_sem_indicador_nao_mostra_bloco_no_painel(
    contrato, perfil_modelo, client, django_user_model
):
    perfil_modelo.definicao["painel"].pop("indicadores", None)
    perfil_modelo.definicao.pop("prazos", None)
    perfil_modelo.save(update_fields=("definicao",))
    usuario = django_user_model.objects.create_user(username="chefia-sem-indicador", password="senha")
    Participacao.objects.create(usuario=usuario, contrato=contrato, papel="chefia")
    client.force_login(usuario)

    resposta = client.get(reverse("painel", args=(contrato.pk,)))

    assert resposta.status_code == 200
    assert "painel-indicador" not in resposta.content.decode()
    assert "Prazos" not in resposta.content.decode()


@pytest.mark.django_db
def test_indicador_prazos_cliente_usa_dias_uteis_feriados_e_filtros(
    contrato, perfil_modelo, monkeypatch
):
    hoje = date(2026, 12, 30)
    monkeypatch.setattr("painel.servicos.timezone.localdate", lambda: hoje)
    perfil_modelo.definicao["prazos"]["feriados"]["extras"] = [
        {"data": "2026-11-23", "nome": "Feriado municipal"}
    ]
    perfil_modelo.save(update_fields=("definicao",))
    indice = _indice(contrato, "ID-PRAZOS-CLIENTE")
    documentos = [
        _documento(contrato, indice, 5401, tipo="DE"),
        _documento(contrato, indice, 5402, tipo="DE"),
        _documento(contrato, indice, 5403, tipo="MC"),
    ]
    for documento, fim in zip(
        documentos,
        (date(2026, 12, 14), date(2026, 12, 15), date(2026, 12, 15)),
    ):
        emissao = Emissao.objects.create(
            documento=documento,
            revisao="1",
            versao=1,
            fase=Emissao.Fase.PRELIMINAR,
            data_emissao=date(2026, 11, 19),
            origem=Emissao.Origem.CLIENTE,
        )
        Analise.objects.create(
            emissao=emissao,
            etapa="Análise do cliente",
            situacao="Não Aprovado",
            origem=Analise.Origem.IMPORTADO_PW,
            data_analise=fim,
        )

    dados = carregar_painel(contrato, por="tipo", filtros={"tipo": "DE"})
    indicador = next(
        item for item in dados["indicadores_prazo"] if item["regra"].id == "analise_cliente"
    )

    assert indicador["dentro"] == 1
    assert indicador["fora"] == 1
    assert indicador["base"] == 2
    assert indicador["percentual"] == 50
    assert {item["rotulo"]: item["base"] for item in indicador["recortes"]} == {
        "Desenho": 2
    }
    assert dados["analises_deduzidas_sem_data"] == 0


@pytest.mark.django_db
def test_indicador_prazos_devolucao_usa_analise_proxima_emissao_e_abertos(
    contrato, perfil_modelo, monkeypatch, client, django_user_model
):
    hoje = date(2026, 12, 10)
    monkeypatch.setattr("painel.servicos.timezone.localdate", lambda: hoje)
    indice = _indice(contrato, "ID-PRAZOS-DEVOLUCAO")
    concluido = _documento(contrato, indice, 5501, tipo="DE")
    analise = Emissao.objects.create(
        documento=concluido,
        revisao="1",
        versao=1,
        fase=Emissao.Fase.PRELIMINAR,
        data_emissao=date(2026, 11, 1),
        origem=Emissao.Origem.CLIENTE,
    )
    Analise.objects.create(
        emissao=analise,
        etapa="Análise do cliente",
        situacao="Não Aprovado",
        origem=Analise.Origem.IMPORTADO_PW,
        data_analise=date(2026, 11, 19),
    )
    Emissao.objects.create(
        documento=concluido,
        revisao="2",
        versao=1,
        fase=Emissao.Fase.PRELIMINAR,
        data_emissao=date(2026, 12, 5),
        origem=Emissao.Origem.CLIENTE,
    )

    aberto = _documento(contrato, indice, 5502, tipo="MC")
    emissao_aberta = Emissao.objects.create(
        documento=aberto,
        revisao="1",
        versao=1,
        fase=Emissao.Fase.PRELIMINAR,
        data_emissao=date(2026, 11, 1),
        origem=Emissao.Origem.CLIENTE,
    )
    Analise.objects.create(
        emissao=emissao_aberta,
        etapa="Análise do cliente",
        situacao="Não Aprovado",
        origem=Analise.Origem.IMPORTADO_PW,
        data_analise=date(2026, 11, 20),
    )

    sem_data = _documento(contrato, indice, 5503, tipo="DE")
    emissao_sem_data = Emissao.objects.create(
        documento=sem_data,
        revisao="1",
        versao=1,
        fase=Emissao.Fase.PRELIMINAR,
        data_emissao=date(2026, 11, 1),
        origem=Emissao.Origem.CLIENTE,
    )
    Analise.objects.create(
        emissao=emissao_sem_data,
        etapa="Análise do cliente",
        situacao="Não Aprovado",
        origem=Analise.Origem.DEDUZIDO_PW,
        data_analise=None,
    )

    dados = carregar_painel(contrato, por="tipo")
    indicador = next(
        item for item in dados["indicadores_prazo"] if item["regra"].id == "devolucao_nossa"
    )
    usuario = django_user_model.objects.create_user(username="chefia-prazos", password="senha")
    Participacao.objects.create(usuario=usuario, contrato=contrato, papel="chefia")
    client.force_login(usuario)
    resposta = client.get(reverse("painel", args=(contrato.pk,)), {"por": "tipo"})

    assert indicador["dentro"] == 0
    assert indicador["fora"] == 2
    assert indicador["base"] == 2
    assert indicador["atrasos_abertos"] == 1
    assert {item["rotulo"]: item["base"] for item in indicador["recortes"]} == {
        "Desenho": 1,
        "Memorial de cálculo": 1,
    }
    assert dados["analises_deduzidas_sem_data"] == 1
    assert "Análises deduzidas sem data excluídas dos prazos: 1" in resposta.content.decode()
    assert "Nossa devolução" in resposta.content.decode()


@pytest.mark.django_db
def test_indicador_cronograma_classifica_situacoes_e_exclui_futuros_da_base(
    contrato, perfil_modelo, monkeypatch, client, django_user_model
):
    hoje = date(2026, 12, 10)
    monkeypatch.setattr("painel.servicos.timezone.localdate", lambda: hoje)
    indice = _indice(contrato, "ID-CRONOGRAMA-PAINEL")
    no_prazo = _documento(contrato, indice, 8101)
    atrasado = _documento(contrato, indice, 8102)
    vencido = _documento(contrato, indice, 8103)
    futuro = _documento(contrato, indice, 8104)
    _previsoes_cronograma(
        contrato,
        [
            (no_prazo, date(2026, 12, 9)),
            (atrasado, date(2026, 12, 8)),
            (vencido, date(2026, 12, 9)),
            (futuro, hoje),
        ],
    )
    Emissao.objects.create(
        documento=no_prazo,
        revisao="1",
        versao=1,
        fase=Emissao.Fase.PRELIMINAR,
        data_emissao=date(2026, 12, 9),
        origem=Emissao.Origem.CLIENTE,
    )
    Emissao.objects.create(
        documento=atrasado,
        revisao="1",
        versao=1,
        fase=Emissao.Fase.PRELIMINAR,
        data_emissao=date(2026, 12, 9),
        origem=Emissao.Origem.CLIENTE,
    )

    dados = carregar_painel(contrato)
    indicador = dados["indicador_cronograma"]
    usuario = django_user_model.objects.create_user(
        username="chefia-cronograma", password="senha"
    )
    Participacao.objects.create(usuario=usuario, contrato=contrato, papel="chefia")
    client.force_login(usuario)
    html = client.get(reverse("painel", args=(contrato.pk,))).content.decode()

    assert indicador["no_prazo"] == 1
    assert indicador["atrasados"] == 1
    assert indicador["vencidos_sem_emissao"] == 1
    assert indicador["futuros"] == 1
    assert indicador["previstos"] == 4
    assert indicador["base"] == 3
    assert indicador["percentual"] == pytest.approx(100 / 3)
    assert indicador["meta_percentual"] == 80
    texto = re.sub(r"\s+", " ", html)
    assert "Cronograma de emissão" in texto
    trecho_cronograma = texto[texto.index("Cronograma de emissão"):][:1200]
    assert "emitidos no prazo" in trecho_cronograma, trecho_cronograma
    assert "Futuros (fora da base): 1" in texto
    assert "Base: 3" in texto
    assert "Linha tracejada: Meta 80%" in texto
    assert re.search(r"left:80(?:\.0)?%", html), re.findall(r"left.{0,40}", html)


@pytest.mark.django_db
def test_indicador_cronograma_respeita_filtros_e_recorte_selecionado(
    contrato, perfil_modelo, monkeypatch
):
    hoje = date(2026, 12, 10)
    monkeypatch.setattr("painel.servicos.timezone.localdate", lambda: hoje)
    indice = _indice(contrato, "ID-CRONOGRAMA-FILTROS")
    ragueb = _documento(contrato, indice, 8201, tipo="DE", trecho="25")
    sao_mateus = _documento(contrato, indice, 8202, tipo="DE", trecho="23")
    outro_tipo = _documento(contrato, indice, 8203, tipo="MC", trecho="25")
    _previsoes_cronograma(
        contrato,
        [
            (ragueb, date(2026, 12, 9)),
            (sao_mateus, date(2026, 12, 9)),
            (outro_tipo, date(2026, 12, 20)),
        ],
    )
    Emissao.objects.create(
        documento=ragueb,
        revisao="1",
        versao=1,
        fase=Emissao.Fase.PRELIMINAR,
        data_emissao=date(2026, 12, 9),
        origem=Emissao.Origem.CLIENTE,
    )

    dados = carregar_painel(
        contrato, por="trecho", filtros={"tipo": "DE"}
    )
    indicador = dados["indicador_cronograma"]

    assert indicador["previstos"] == 2
    assert indicador["no_prazo"] == 1
    assert indicador["vencidos_sem_emissao"] == 1
    assert indicador["futuros"] == 0
    assert indicador["base"] == 2
    assert indicador["percentual"] == 50
    assert {item["rotulo"]: item["previstos"] for item in indicador["recortes"]} == {
        "Ragueb Chohfi": 1,
        "São Mateus": 1,
    }


@pytest.mark.django_db
def test_cronograma_sem_previsoes_so_mostra_link_de_importacao_para_staff(
    contrato, perfil_modelo, client, django_user_model
):
    assert carregar_painel(contrato)["indicador_cronograma"] is None
    url = reverse("painel", args=(contrato.pk,))
    staff = django_user_model.objects.create_user(
        username="staff-sem-cronograma", password="senha", is_staff=True
    )
    Participacao.objects.create(usuario=staff, contrato=contrato, papel="chefia")
    client.force_login(staff)
    resposta_staff = client.get(url)
    assert resposta_staff.status_code == 200
    assert "Nenhum cronograma importado" in resposta_staff.content.decode()
    assert reverse("importar_cronograma") in resposta_staff.content.decode()
    assert "Importar cronograma" in resposta_staff.content.decode()

    chefia = django_user_model.objects.create_user(
        username="chefia-sem-cronograma", password="senha"
    )
    Participacao.objects.create(usuario=chefia, contrato=contrato, papel="chefia")
    client.force_login(chefia)
    resposta_chefia = client.get(url)
    assert resposta_chefia.status_code == 200
    assert "Cronograma de emissão" not in resposta_chefia.content.decode()
    assert "Nenhum cronograma importado" not in resposta_chefia.content.decode()


@pytest.mark.django_db
def test_indicador_cronograma_funciona_sem_configuracao_de_prazos_no_perfil(
    contrato, perfil_modelo
):
    perfil_modelo.definicao.pop("prazos", None)
    perfil_modelo.save(update_fields=("definicao",))
    indice = _indice(contrato, "ID-CRONOGRAMA-SEM-META")
    documento = _documento(contrato, indice, 8301)
    _previsoes_cronograma(contrato, [(documento, timezone.localdate())])

    indicador = carregar_painel(contrato)["indicador_cronograma"]

    assert indicador["futuros"] == 1
    assert indicador["base"] == 0
    assert indicador["percentual"] is None
    assert indicador["meta_percentual"] is None


@pytest.mark.django_db
def test_filtro_htmx_atualiza_tela_inteira_e_preserva_valores_na_querystring(
    client, contrato, perfil_modelo, django_user_model
):
    usuario = django_user_model.objects.create_user(username="ana-filtros", password="senha")
    Participacao.objects.create(usuario=usuario, contrato=contrato, papel="chefia")
    indice = _indice(contrato, "ID-HTMX-FILTROS")
    _documento(contrato, indice, 6001, tipo="DE", trecho="25")
    _documento(contrato, indice, 6002, tipo="MC", trecho="25")
    _documento(contrato, indice, 6003, tipo="MC", trecho="23")
    client.force_login(usuario)

    resposta = client.get(
        reverse("painel", args=(contrato.pk,)),
        {"tipo": ["MC"], "trecho": ["25"]},
        HTTP_HX_REQUEST="true",
    )
    html = resposta.content.decode()

    assert resposta.status_code == 200
    barra_filtros = re.search(
        r'<nav class="painel-filtros-ativos" aria-label="Filtros ativos">(.*?)</nav>',
        html,
        re.S,
    )
    assert barra_filtros is not None
    filtros_ativos = barra_filtros.group(1)
    assert "tipo documental: MC – Memorial de cálculo" in filtros_ativos
    assert "trecho: 25 – Ragueb Chohfi" in filtros_ativos
    assert 'aria-label="Remover filtro tipo documental: MC – Memorial de cálculo"' in filtros_ativos
    assert 'aria-label="Remover filtro trecho: 25 – Ragueb Chohfi"' in filtros_ativos
    assert filtros_ativos.count('class="painel-filtro-remover"') == 2
    assert "×</a>" in filtros_ativos
    assert "Limpar todos" in filtros_ativos
    por = resposta.context["por"]
    links_remocao = re.findall(
        r'<a class="painel-filtro-remover"[^>]*href="([^"]+)"', filtros_ativos
    )
    assert any(
        link.endswith(f"?por={por}&amp;trecho=25&amp;manter_filtros_abertos=1")
        for link in links_remocao
    )
    assert any(
        link.endswith(f"?por={por}&amp;tipo=MC&amp;manter_filtros_abertos=1")
        for link in links_remocao
    )
    assert "Documentos previstos em conta" in html
    assert "Distribuição por situação" in html
    assert "dados-grafico-pizza" in html
    assert "dados-grafico-recortes" in html
    assert "Fora do ID" in html
    assert 'hx-push-url="true"' in html
    assert "<html" not in html


@pytest.mark.django_db
def test_valor_de_filtro_invalido_e_ignorado(contrato, perfil_modelo):
    indice = _indice(contrato, "ID-FILTRO-INVALIDO")
    _documento(contrato, indice, 7001, tipo="DE", trecho="25")
    _documento(contrato, indice, 7002, tipo="MC", trecho="23")

    sem_filtro = carregar_painel(contrato)
    com_valor_invalido = carregar_painel(
        contrato,
        filtros={"tipo": "TIPO-QUE-NAO-EXISTE", "caixa-desconhecida": "valor"},
    )

    assert com_valor_invalido["total_documentos_previstos"] == sem_filtro["total_documentos_previstos"] == 2
    assert com_valor_invalido["filtros_ativos"] == []


@pytest.mark.django_db
def test_pin_correto_libera_painel_e_pin_errado_nao_libera(client, contrato, perfil_modelo):
    contrato.definir_pin_painel("5724")
    contrato.save(update_fields=("pin_painel",))

    url = reverse("painel", args=(contrato.pk,))
    resposta = client.get(url)
    assert resposta.status_code == 200
    assert "Informe o PIN" in resposta.content.decode()

    resposta = client.post(url, {"pin": "1111"})
    assert resposta.status_code == 200
    assert "PIN incorreto" in resposta.content.decode()
    assert f"painel_liberado_{contrato.pk}" not in client.session

    resposta = client.post(url, {"pin": "5724"})
    assert resposta.status_code == 302
    assert client.session[f"painel_liberado_{contrato.pk}"] is True
    assert client.get(url).status_code == 200


@pytest.mark.django_db
def test_bloqueia_por_cinco_minutos_apos_cinco_pins_errados(client, contrato, perfil_modelo):
    contrato.definir_pin_painel("5724")
    contrato.save(update_fields=("pin_painel",))
    url = reverse("painel", args=(contrato.pk,))

    for tentativa in range(5):
        resposta = client.post(url, {"pin": "0000"})
    assert "bloqueado por 5 minutos" in resposta.content.decode()
    resposta = client.post(url, {"pin": "5724"})
    assert "Muitas tentativas" in resposta.content.decode()
    assert f"painel_liberado_{contrato.pk}" not in client.session


@pytest.mark.django_db
def test_participante_logado_entra_sem_pin(client, contrato, perfil_modelo, django_user_model):
    usuario = django_user_model.objects.create_user(username="chefia", password="senha")
    Participacao.objects.create(usuario=usuario, contrato=contrato, papel="chefia")
    client.force_login(usuario)

    resposta = client.get(reverse("painel", args=(contrato.pk,)))

    assert resposta.status_code == 200
    assert "Documentos previstos" in resposta.content.decode()
    assert f"painel_liberado_{contrato.pk}" not in client.session


@pytest.mark.django_db
def test_painel_avisa_recusas_somente_a_quem_pode_abri_las(
    client, contrato, perfil_modelo, django_user_model
):
    indice = _indice(contrato, "ID-RECUSAS")
    importacao = ImportacaoID.objects.create(
        contrato=contrato,
        indice=indice,
        arquivo_nome="ID-RECUSAS.xlsx",
        linhas_invalidas=1,
    )
    InconsistenciaImportacao.objects.create(
        importacao_id=importacao,
        numero_linha=2,
        codigo_lido="DE-15.25.00.00-6A7-1001",
        mensagem="Classe desconhecida.",
    )
    administrador = django_user_model.objects.create_user(username="admin-aviso", password="senha")
    Participacao.objects.create(
        usuario=administrador,
        contrato=contrato,
        papel="admin",
    )
    client.force_login(administrador)
    resposta = client.get(reverse("painel", args=(contrato.pk,)))
    assert resposta.status_code == 200
    assert "1 linha recusada nas importações" in resposta.content.decode()
    assert reverse("linhas_recusadas", args=(contrato.pk,)) in resposta.content.decode()

    equipe = django_user_model.objects.create_user(username="equipe-aviso", password="senha")
    Participacao.objects.create(usuario=equipe, contrato=contrato, papel="equipe")
    client.force_login(equipe)
    resposta = client.get(reverse("painel", args=(contrato.pk,)))
    assert resposta.status_code == 200
    assert "linha recusada nas importações" not in resposta.content.decode()


@pytest.mark.django_db
def test_troca_recorte_htmx_retorna_somente_fragmento(client, contrato, perfil_modelo, django_user_model):
    usuario = django_user_model.objects.create_user(username="ana", password="senha")
    Participacao.objects.create(usuario=usuario, contrato=contrato, papel="chefia")
    indice = _indice(contrato, "ID-HTMX")
    _documento(contrato, indice, 1001, classe="P7", situacao="Aprovado")
    client.force_login(usuario)

    resposta = client.get(
        reverse("painel_recorte", args=(contrato.pk,)),
        {"por": "classe"},
        HTTP_HX_REQUEST="true",
    )

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Iluminação" in html
    assert "dados-grafico-recortes" in html
    assert "<html" not in html
    assert "Lista Mestra" not in html


@pytest.mark.django_db
def test_admin_grava_pin_em_hash_e_nao_mostra_o_existente(contrato):
    form = ContratoAdminForm(
        data={
            "nome": contrato.nome,
            "codigo_interno": contrato.codigo_interno,
            "cliente": contrato.cliente,
            "descricao": "",
            "ativo": "on",
            "pin_painel": "123456",
        },
        instance=contrato,
    )
    assert form.is_valid(), form.errors
    salvo = form.save()
    assert salvo.pin_painel != "123456"
    assert check_password("123456", salvo.pin_painel)

    form_sem_alteracao = ContratoAdminForm(instance=salvo)
    assert form_sem_alteracao["pin_painel"].value() == ""


@pytest.mark.django_db
def test_comando_demo_recusa_contrato_com_documentos(contrato, perfil_modelo):
    Documento.objects.create(contrato=contrato, identificador_base="EXISTENTE")

    with pytest.raises(CommandError, match="já tenha documentos"):
        call_command("popular_painel_demo", contrato.pk)


@pytest.mark.django_db
def test_comando_demo_cria_somente_dados_sinteticos(contrato, perfil_modelo):
    call_command("popular_painel_demo", contrato.pk)

    assert Documento.objects.filter(contrato=contrato).count() == 63
    assert ItemPrevisto.objects.filter(indice__contrato=contrato, indice__vigente=True).count() == 60
    assert Emissao.objects.filter(documento__contrato=contrato).count() > 0
    assert ImportacaoSituacao.objects.filter(contrato=contrato).exists()
