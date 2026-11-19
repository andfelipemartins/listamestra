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
    ImportacaoID,
    ImportacaoSituacao,
    IndiceDocumentos,
    ItemPrevisto,
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


def _indice(contrato, codigo, *, fonte=IndiceDocumentos.Fonte.EXCEL_ID, revisao="1"):
    return IndiceDocumentos.objects.create(
        contrato=contrato,
        codigo=codigo,
        revisao=revisao,
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


def _emissao_com_status(documento, revisao, situacao, *, fase=Emissao.Fase.PRELIMINAR):
    data = timezone.localdate() - timedelta(days=10)
    emissao = Emissao.objects.create(
        documento=documento,
        revisao=str(revisao),
        versao=1,
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
def test_grupo_erro_tem_cartao_e_fatia_separados_de_inconsistente(
    contrato, perfil_modelo, client, django_user_model
):
    usuario = django_user_model.objects.create_user(username="chefia-erros", password="senha")
    Participacao.objects.create(usuario=usuario, contrato=contrato, papel="chefia")
    indice = _indice(contrato, "ID-ERROS")
    _documento(contrato, indice, 3501, situacao="Em Desenvolvimento")
    _documento(contrato, indice, 3502, situacao="Erro de Assinatura")
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
    assert cards["erro"] == 2
    assert cards["inconsistente"] == 2
    assert 'painel-grupo-label">ERRO</span>' in html
    assert 'painel-grupo-label">INCONSISTENTE</span>' in html
    assert "ERRO" in pizza["labels"]
    assert "INCONSISTENTE" in pizza["labels"]
    assert "ERRO" in [dataset["label"] for dataset in barras["datasets"]]
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
def test_indicador_aparece_com_numero_geral_barras_por_recorte_e_linha_de_meta(
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
    _emissao_com_status(fora, "0", "Aprovado", fase=Emissao.Fase.ORIGINAL)
    client.force_login(usuario)

    dados = carregar_painel(contrato, por="trecho")
    resposta = client.get(reverse("painel", args=(contrato.pk,)), {"por": "trecho"})
    html = resposta.content.decode()
    indicador = dados["indicadores_aprovacao"][0]
    grafico = json.loads(
        re.search(
            r'<script id="dados-indicador-1" type="application/json">(.*?)</script>', html
        ).group(1)
    )

    assert indicador["tem_dados"] is True
    assert indicador["percentual"] == pytest.approx(50)
    assert {item["rotulo"]: item["percentual"] for item in indicador["recortes"]} == {
        "Ragueb Chohfi": 100,
        "São Mateus": 0,
    }
    assert "<strong>50%</strong> aprovados em até 3 revisões · meta 80%" in re.sub(
        r"\s+", " ", html
    )
    assert grafico["labels"] == ["Ragueb Chohfi", "São Mateus"]
    assert grafico["datasets"][0]["data"] == [100, 0]
    assert grafico["metaPercentual"] == 80
    assert "linha-meta-indicador" in html
    assert "setLineDash([6, 5])" in html
    assert "rotulos-indicador" in html
    assert "Dentro do limite: 1" in html
    assert "Fora do limite: 1" in html


@pytest.mark.django_db
def test_perfil_sem_indicador_nao_mostra_bloco_no_painel(
    contrato, perfil_modelo, client, django_user_model
):
    perfil_modelo.definicao["painel"].pop("indicadores", None)
    perfil_modelo.save(update_fields=("definicao",))
    usuario = django_user_model.objects.create_user(username="chefia-sem-indicador", password="senha")
    Participacao.objects.create(usuario=usuario, contrato=contrato, papel="chefia")
    client.force_login(usuario)

    resposta = client.get(reverse("painel", args=(contrato.pk,)))

    assert resposta.status_code == 200
    assert "painel-indicador" not in resposta.content.decode()


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
    assert "Filtros ativos:" in html
    assert "tipo documental: MC – Memorial de cálculo" in html
    assert "trecho: 25 – Ragueb Chohfi" in html
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
