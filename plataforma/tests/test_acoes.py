from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from django.urls import reverse
from django.utils import timezone

from acoes.models import AcaoPendencia
from acoes.services import carregar_janela, carregar_minha_mesa, carregar_resumo_inicio
from contas.models import Usuario
from contratos.models import Contrato, Participacao, PerfilContrato
from documentos.models import Analise, Documento, Emissao
from importacoes.models import (
    ImportacaoCronograma,
    ImportacaoID,
    ImportacaoSituacao,
    InconsistenciaImportacao,
    IndiceDocumentos,
    PrevisaoEmissao,
)


RAIZ = Path(__file__).resolve().parents[2]
PERFIL_METRO = RAIZ / "core" / "perfil" / "exemplos" / "metro.yaml"
HOJE = date(2026, 11, 23)


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato de ações",
        codigo_interno="CT-ACOES",
        cliente="Cliente de teste",
    )


@pytest.fixture
def perfil_modelo(contrato):
    with PERFIL_METRO.open(encoding="utf-8") as arquivo:
        definicao = yaml.safe_load(arquivo)
    definicao["vigencia_inicio"] = "2020-01-01"
    return PerfilContrato.objects.create(
        contrato=contrato,
        versao=1,
        vigencia_inicio=date(2020, 1, 1),
        definicao=definicao,
    )


@pytest.fixture
def usuario(contrato, django_user_model):
    pessoa = django_user_model.objects.create_user(
        username="equipe-acoes", password="senha-segura", first_name="Ana", last_name="Equipe"
    )
    Participacao.objects.create(
        usuario=pessoa,
        contrato=contrato,
        papel=Usuario.Perfil.EQUIPE,
        ativo=True,
    )
    return pessoa


def _documento(contrato, identificador, *, titulo="Documento", tipo="DE"):
    return Documento.objects.create(
        contrato=contrato,
        identificador_base=identificador,
        titulo=titulo,
        tipo=tipo,
        atributos={"tipo": tipo},
    )


def _emissao(documento, data, *, revisao="1", situacao=None, data_analise=None, usuario=None):
    emissao = Emissao.objects.create(
        documento=documento,
        revisao=revisao,
        versao=1,
        fase=Emissao.Fase.PRELIMINAR,
        data_emissao=data,
        origem=Emissao.Origem.CLIENTE,
    )
    if situacao is not None:
        Analise.objects.create(
            emissao=emissao,
            etapa="Análise do cliente",
            situacao=situacao,
            origem=Analise.Origem.IMPORTADO_PW,
            data_analise=data_analise,
            registrado_por=usuario,
        )
    return emissao


def _janela(dados, identificador):
    return next(item for item in dados["janelas"] if item["id"] == identificador)


@pytest.mark.django_db
def test_janela_erros_usa_grupo_oculto_e_mostra_quem_lancou(contrato, perfil_modelo, usuario):
    documento = _documento(contrato, "DOC-ERRO-1001", titulo="Desenho de teste")
    _emissao(documento, date(2026, 11, 10), situacao="Erro de Assinatura", data_analise=date(2026, 11, 12), usuario=usuario)

    dados = carregar_minha_mesa(usuario, contrato.pk, hoje=HOJE)
    erros = _janela(dados, "erros")

    assert erros["quantidade"] == 1
    assert erros["itens"][0]["codigo"] == "DOC-ERRO-1001"
    assert erros["itens"][0]["situacao"] == "Erro de Assinatura"
    assert erros["itens"][0]["data_desde"] == date(2026, 11, 12)
    assert erros["itens"][0]["quem_lancou"] == "Ana Equipe"


@pytest.mark.django_db
def test_codigo_da_mesa_e_do_ver_todos_abre_a_pasta_do_documento(
    contrato, perfil_modelo, usuario, client
):
    documento = _documento(contrato, "DOC-ERRO-PASTA-1001")
    _emissao(
        documento,
        date(2026, 11, 10),
        situacao="Erro de Assinatura",
        data_analise=date(2026, 11, 12),
        usuario=usuario,
    )
    client.force_login(usuario)
    pasta = reverse("documento_pasta", args=(contrato.pk, documento.pk))
    link = f'href="{pasta}"><strong>{documento.identificador_base}</strong></a>'

    mesa = client.get(reverse("inicio"), {"contrato": contrato.pk})
    pendencias = client.get(reverse("acoes:pendencias"), {"contrato": contrato.pk})
    ver_todos = client.get(reverse("acoes:janela", args=("erros",)), {"contrato": contrato.pk})

    assert mesa.status_code == 200
    assert pendencias.status_code == 200
    assert ver_todos.status_code == 200
    assert link not in mesa.content.decode()
    assert link in pendencias.content.decode()
    assert link in ver_todos.content.decode()


@pytest.mark.django_db
def test_janela_analise_usa_dias_uteis_e_ordena_atrasados_primeiro(contrato, perfil_modelo, usuario):
    perfil_modelo.definicao["prazos"]["regras"][0]["dias"] = 3
    perfil_modelo.save(update_fields=("definicao",))
    vencido = _documento(contrato, "DOC-ANALISE-1001")
    proximo = _documento(contrato, "DOC-ANALISE-1002")
    _emissao(vencido, date(2026, 11, 12))
    _emissao(proximo, date(2026, 11, 20))

    janela = _janela(carregar_minha_mesa(usuario, contrato.pk, hoje=HOJE), "analise-cliente")

    assert janela["quantidade"] == 2
    assert janela["itens"][0]["codigo"] == "DOC-ANALISE-1001"
    assert janela["itens"][0]["atrasado"] is True
    assert janela["itens"][0]["vencimento"] == date(2026, 11, 17)
    assert janela["itens"][1]["codigo"] == "DOC-ANALISE-1002"
    assert janela["itens"][1]["vencimento"] == date(2026, 11, 25)
    assert janela["itens"][1]["dias"] == 2


@pytest.mark.django_db
def test_janela_devolucao_usa_dias_corridos(contrato, perfil_modelo, usuario):
    perfil_modelo.definicao["prazos"]["regras"][1]["dias"] = 2
    perfil_modelo.save(update_fields=("definicao",))
    documento = _documento(contrato, "DOC-DEVOLUCAO-1001")
    _emissao(
        documento,
        date(2026, 11, 10),
        situacao="Não Aprovado",
        data_analise=date(2026, 11, 22),
        usuario=usuario,
    )

    janela = _janela(carregar_minha_mesa(usuario, contrato.pk, hoje=HOJE), "devolucao")

    assert janela["quantidade"] == 1
    assert janela["itens"][0]["vencimento"] == date(2026, 11, 24)
    assert janela["itens"][0]["dias"] == 1
    assert janela["itens"][0]["texto_prazo"] == "Vence em 1 dia"


@pytest.mark.django_db
def test_janela_cronograma_mostra_vencidos_e_proximos_sete_dias(contrato, perfil_modelo, usuario):
    atrasado = _documento(contrato, "DOC-CRONO-1001")
    proximo = _documento(contrato, "DOC-CRONO-1002")
    fora_da_janela = _documento(contrato, "DOC-CRONO-1003")
    importacao = ImportacaoCronograma.objects.create(contrato=contrato, arquivo_nome="cronograma.xlsx")
    for documento, prevista in (
        (atrasado, HOJE - timedelta(days=1)),
        (proximo, HOJE + timedelta(days=7)),
        (fora_da_janela, HOJE + timedelta(days=8)),
    ):
        PrevisaoEmissao.objects.create(
            contrato=contrato,
            documento=documento,
            data_prevista=prevista,
            importacao=importacao,
        )

    janela = _janela(carregar_minha_mesa(usuario, contrato.pk, hoje=HOJE), "cronograma")

    assert janela["quantidade"] == 2
    assert [item["codigo"] for item in janela["itens"]] == ["DOC-CRONO-1001", "DOC-CRONO-1002"]
    assert janela["itens"][0]["vencido"] is True
    assert janela["itens"][1]["data_prevista"] == HOJE + timedelta(days=7)


@pytest.mark.django_db
def test_janela_recusadas_agrupa_por_importacao(contrato, perfil_modelo, usuario):
    importacao_pw = ImportacaoSituacao.objects.create(
        contrato=contrato,
        data_extracao=HOJE,
        arquivo_nome="pw.xlsx",
        importado_por=usuario,
    )
    importacao_pw_2 = ImportacaoSituacao.objects.create(
        contrato=contrato,
        data_extracao=HOJE - timedelta(days=1),
        arquivo_nome="pw-corrigido.xlsx",
        importado_por=usuario,
    )
    for importacao, numeros in ((importacao_pw, (3, 4)), (importacao_pw_2, (7,))):
        for numero in numeros:
            InconsistenciaImportacao.objects.create(
                importacao_situacao=importacao,
                numero_linha=numero,
                mensagem="Linha recusada",
            )

    janela = _janela(carregar_minha_mesa(usuario, contrato.pk, hoje=HOJE), "recusadas")

    assert janela["quantidade"] == 2
    assert sum(item["quantidade"] for item in janela["itens"]) == 3
    assert {item["tipo"] for item in janela["itens"]} == {"Situação PW"}
    assert all(item["link_recusadas"] for item in janela["itens"])


@pytest.mark.django_db
def test_ignorar_e_reativar_registra_historico_e_mantem_item_disponivel(contrato, perfil_modelo, usuario, client):
    documento = _documento(contrato, "DOC-ERRO-1002")
    _emissao(documento, date(2026, 11, 10), situacao="Em Desenvolvimento", data_analise=date(2026, 11, 12), usuario=usuario)
    client.force_login(usuario)

    resposta = client.post(
        reverse("acoes:registrar_acao"),
        {
            "contrato": contrato.pk,
            "documento": documento.pk,
            "tipo_pendencia": "erro",
            "acao": "ignorar",
            "motivo": "Aguardando retorno do cliente",
        },
    )

    assert resposta.status_code == 302
    acao = AcaoPendencia.objects.get(documento=documento)
    assert acao.usuario == usuario
    assert acao.resolvida_em is None
    assert acao.history.count() == 1
    assert _janela(carregar_minha_mesa(usuario, contrato.pk, hoje=HOJE), "erros")["quantidade"] == 0
    ignorados = carregar_janela(usuario, contrato.pk, "erros", hoje=HOJE)
    assert ignorados["janela"]["quantidade"] == 0
    assert carregar_janela(usuario, contrato.pk, "erros", hoje=HOJE)["janela"]["titulo"] == "Erros a corrigir"

    from acoes.services import carregar_ignorados, reativar_ignorado

    lista_ignorados = carregar_ignorados(usuario, contrato.pk, hoje=HOJE)
    assert lista_ignorados["janela"]["quantidade"] == 1
    reativar_ignorado(usuario, contrato.pk, documento.pk, "erro")

    acao.refresh_from_db()
    assert acao.resolvida_em is not None
    assert acao.history.count() == 2
    assert _janela(carregar_minha_mesa(usuario, contrato.pk, hoje=HOJE), "erros")["quantidade"] == 1


@pytest.mark.django_db
def test_pedir_correcao_gera_email_pronto_para_copiar(contrato, perfil_modelo, usuario, client):
    documento = _documento(contrato, "DOC-ERRO-1003")
    _emissao(documento, date(2026, 11, 10), revisao="2", situacao="Erro de Assinatura", data_analise=date(2026, 11, 12), usuario=usuario)
    client.force_login(usuario)

    resposta = client.post(
        reverse("acoes:registrar_acao"),
        {
            "contrato": contrato.pk,
            "documento": documento.pk,
            "tipo_pendencia": "erro",
            "acao": "pedir_correcao",
        },
    )
    acao = AcaoPendencia.objects.get(documento=documento)

    assert resposta.status_code == 302
    assert "email=" in resposta.url
    assert "DOC-ERRO-1003" in acao.texto_email
    assert "revisão 2 versão 1" in acao.texto_email
    assert "Erro de Assinatura" in acao.texto_email
    assert "12/11/2026" in acao.texto_email
    pagina = client.get(resposta.url)
    assert "Copiar texto" in pagina.content.decode()
    assert "Agradecemos a verificação" in pagina.content.decode()


@pytest.mark.django_db
def test_ja_corrigi_fica_na_janela_ate_que_a_situacao_mude(contrato, perfil_modelo, usuario, client):
    documento = _documento(contrato, "DOC-ERRO-1004")
    emissao = _emissao(documento, date(2026, 11, 10), situacao="Em Desenvolvimento", data_analise=date(2026, 11, 12), usuario=usuario)
    client.force_login(usuario)
    client.post(
        reverse("acoes:registrar_acao"),
        {"contrato": contrato.pk, "documento": documento.pk, "tipo_pendencia": "erro", "acao": "ja_corrigi"},
    )

    erros = _janela(carregar_minha_mesa(usuario, contrato.pk, hoje=HOJE), "erros")
    assert erros["quantidade"] == 1
    assert erros["itens"][0]["ultima_acao"].acao == AcaoPendencia.Acao.JA_CORRIGI

    Analise.objects.create(
        emissao=emissao,
        etapa="Análise do cliente",
        situacao="Em Análise",
        origem=Analise.Origem.IMPORTADO_PW,
        data_analise=HOJE,
        registrado_por=usuario,
    )
    assert _janela(carregar_minha_mesa(usuario, contrato.pk, hoje=HOJE), "erros")["quantidade"] == 0


@pytest.mark.django_db
def test_perfil_sem_prazos_nao_cria_janelas_de_prazo(contrato, perfil_modelo, usuario):
    perfil_modelo.definicao.pop("prazos")
    perfil_modelo.save(update_fields=("definicao",))

    ids = {item["id"] for item in carregar_minha_mesa(usuario, contrato.pk, hoje=HOJE)["janelas"]}

    assert "analise-cliente" not in ids
    assert "devolucao" not in ids
    assert {"erros", "cronograma", "recusadas"}.issubset(ids)


@pytest.mark.django_db
def test_usuario_sem_participacao_nao_acessa_contrato(contrato, perfil_modelo, client, django_user_model):
    usuario = django_user_model.objects.create_user(username="sem-contrato", password="senha-segura")
    client.force_login(usuario)

    resposta = client.get(reverse("inicio"), {"contrato": contrato.pk})

    assert resposta.status_code == 403


@pytest.mark.django_db
def test_staff_pode_selecionar_contratos_sem_participacao_inclusive_inativos(client, django_user_model):
    contrato = Contrato.objects.create(
        nome="Contrato inativo",
        codigo_interno="CT-INATIVO",
        cliente="Cliente de teste",
        ativo=False,
    )
    staff = django_user_model.objects.create_user(
        username="staff-acoes", password="senha-segura", is_staff=True
    )
    client.force_login(staff)

    resposta = client.get(reverse("inicio"), {"contrato": contrato.pk})

    assert resposta.status_code == 200
    assert resposta.context["contrato"] == contrato


@pytest.mark.django_db
def test_pendencias_concentra_acoes_inicio_so_mostra_resumos_e_menu_aponta_para_pendencias(
    contrato, perfil_modelo, usuario, client
):
    documento = _documento(contrato, "DOC-ERRO-INICIO-1001")
    _emissao(documento, date(2026, 11, 10), situacao="Erro de Assinatura", data_analise=date(2026, 11, 12))
    client.force_login(usuario)

    inicio = client.get(reverse("inicio"), {"contrato": contrato.pk})
    pendencias = client.get(reverse("acoes:pendencias"), {"contrato": contrato.pk})

    assert inicio.status_code == 200
    assert pendencias.status_code == 200
    assert 'name="acao"' not in inicio.content.decode()
    assert "Ignorar" in pendencias.content.decode()
    assert "Pedir correção ao cliente" in pendencias.content.decode()
    assert "Já corrigi" in pendencias.content.decode()
    assert f'href="{reverse("acoes:pendencias")}"' in pendencias.content.decode()
    assert 'class="nav-item active"' in pendencias.content.decode()


@pytest.mark.django_db
def test_inicio_resume_contagens_de_janelas_incluindo_linhas_recusadas(
    contrato, perfil_modelo, usuario
):
    perfil_modelo.definicao["prazos"]["regras"][0]["dias"] = 1
    perfil_modelo.definicao["prazos"]["regras"][1]["dias"] = 1
    perfil_modelo.save(update_fields=("definicao",))

    erro = _documento(contrato, "DOC-ERRO-RESUMO-1001")
    _emissao(erro, HOJE, situacao="Erro de Assinatura", data_analise=HOJE)
    for sequencial in (1001, 1002):
        documento = _documento(contrato, f"DE-15.25.00.00-6B3-{sequencial}")
        _emissao(documento, HOJE)
    devolucao = _documento(contrato, "DE-15.25.00.00-6B3-1003")
    _emissao(devolucao, HOJE, situacao="Não Aprovado", data_analise=HOJE)

    cronograma_documento = _documento(contrato, "DOC-CRONO-RESUMO-1001")
    importacao_cronograma = ImportacaoCronograma.objects.create(
        contrato=contrato, arquivo_nome="cronograma.xlsx"
    )
    PrevisaoEmissao.objects.create(
        contrato=contrato,
        documento=cronograma_documento,
        data_prevista=HOJE - timedelta(days=1),
        importacao=importacao_cronograma,
    )

    importacao_pw = ImportacaoSituacao.objects.create(
        contrato=contrato,
        data_extracao=HOJE,
        arquivo_nome="pw.xlsx",
        importado_por=usuario,
    )
    for numero in (3, 4, 5):
        InconsistenciaImportacao.objects.create(
            importacao_situacao=importacao_pw,
            numero_linha=numero,
            mensagem="Linha recusada",
        )

    resumo = carregar_resumo_inicio(usuario, contrato.pk, hoje=HOJE)
    contagens = {card["id"]: card["quantidade"] for card in resumo["cards_janelas"]}

    assert contagens == {
        "erros": 1,
        "analise-cliente": 2,
        "devolucao": 1,
        "cronograma": 1,
        "recusadas": 3,
    }


@pytest.mark.django_db
def test_inicio_agrupa_pacotes_pelo_perfil_apenas_com_dois_ou_mais_e_limita_a_seis(
    contrato, perfil_modelo, usuario
):
    perfil_modelo.definicao["painel"].pop("pacote")
    perfil_modelo.definicao["prazos"]["regras"][0]["dias"] = 1
    perfil_modelo.definicao["painel"]["categorias"] = [
        {
            "id": f"pacote_{classe.lower()}",
            "rotulo": f"Pacote {classe}",
            "regras": [{"classe": [classe]}],
        }
        for classe in ("A1", "A2", "A3", "A4", "A6", "A7", "A8", "A9")
    ]
    perfil_modelo.save(update_fields=("definicao",))

    for classe, quantidade in (("A1", 4), ("A2", 3), ("A3", 2), ("A4", 2), ("A6", 2), ("A7", 2), ("A8", 2), ("A9", 1)):
        for indice in range(quantidade):
            sequencial = 1001 + indice
            documento = _documento(
                contrato,
                f"DE-15.25.00.00-6{classe}-{sequencial}",
            )
            _emissao(documento, HOJE)

    resumo = carregar_resumo_inicio(usuario, contrato.pk, hoje=HOJE)

    assert [card["rotulo"] for card in resumo["cards_pacotes"]] == [
        "Pacote A1",
        "Pacote A2",
        "Pacote A3",
        "Pacote A4",
        "Pacote A6",
        "Pacote A7",
    ]
    assert [card["quantidade"] for card in resumo["cards_pacotes"]] == [4, 3, 2, 2, 2, 2]


@pytest.mark.django_db
def test_inicio_agrupa_pelo_perfil_sem_exigir_caixa_literal_disciplina(
    contrato, perfil_modelo, usuario
):
    perfil = perfil_modelo.definicao["codigo"]["segmentos"]
    assert "disciplina" not in {segmento.get("nome") for segmento in perfil}
    perfil_modelo.definicao["painel"].pop("pacote")
    perfil_modelo.definicao["prazos"]["regras"][0]["dias"] = 1
    perfil_modelo.save(update_fields=("definicao",))
    for sequencial in (1001, 1002):
        documento = _documento(contrato, f"DE-15.25.00.00-6B3-{sequencial}")
        _emissao(documento, HOJE)
    categoria_unitaria = _documento(contrato, "DE-15.25.00.00-6A1-1003")
    _emissao(categoria_unitaria, HOJE)

    resumo = carregar_resumo_inicio(usuario, contrato.pk, hoje=HOJE)

    assert resumo["cards_pacotes"] == [
        {"id": "arquitetura", "rotulo": "ARQUITETURA", "quantidade": 2}
    ]


@pytest.mark.django_db
def test_inicio_agrupa_por_pacote_configurado_e_exibe_nome_da_classe(
    contrato, perfil_modelo, usuario
):
    perfil_modelo.definicao["prazos"]["regras"][0]["dias"] = 1
    perfil_modelo.save(update_fields=("definicao",))
    for sequencial in (1001, 1002):
        documento = _documento(contrato, f"DE-15.25.00.00-6G6-{sequencial}")
        _emissao(documento, HOJE)

    resumo = carregar_resumo_inicio(usuario, contrato.pk, hoje=HOJE)

    assert resumo["cards_pacotes"] == [
        {"id": "6G6", "rotulo": "6G6 · Terraplenagem", "quantidade": 2}
    ]


@pytest.mark.django_db
def test_pacote_sem_nome_cadastrado_mostra_apenas_o_codigo(contrato, perfil_modelo, usuario):
    perfil_modelo.definicao["prazos"]["regras"][0]["dias"] = 1
    classe = next(
        segmento for segmento in perfil_modelo.definicao["codigo"]["segmentos"]
        if segmento.get("nome") == "classe"
    )
    classe.pop("valores")
    perfil_modelo.save(update_fields=("definicao",))
    for sequencial in (1001, 1002):
        documento = _documento(contrato, f"DE-15.25.00.00-6A1-{sequencial}")
        _emissao(documento, HOJE)

    resumo = carregar_resumo_inicio(usuario, contrato.pk, hoje=HOJE)

    assert resumo["cards_pacotes"] == [
        {"id": "6A1", "rotulo": "6A1", "quantidade": 2}
    ]


@pytest.mark.django_db
def test_itens_atrasados_recebem_faixa_e_inicio_resume_documentos_por_faixa(
    contrato, perfil_modelo, usuario, client
):
    hoje = timezone.localdate()
    regra = perfil_modelo.definicao["prazos"]["regras"][0]
    regra.update(dias=1, tipo_dia="corridos")
    perfil_modelo.save(update_fields=("definicao",))
    atrasos = ((3, "Leve", 1), (20, "Moderado", 2), (45, "Grave", 3), (90, "Crítico", 4))
    for indice, (dias, _, _) in enumerate(atrasos, start=1):
        codigo = f"DE-15.25.00.00-6B3-{1000 + indice}"
        documento = _documento(contrato, codigo)
        _emissao(documento, hoje - timedelta(days=dias + 1))

    mesa = carregar_minha_mesa(usuario, contrato.pk, hoje=hoje)
    itens = _janela(mesa, "analise-cliente")["itens"]
    por_dias = {item["dias"]: item for item in itens}
    assert {dias: por_dias[dias]["faixa_atraso"] for dias, _, _ in atrasos} == {
        dias: rotulo for dias, rotulo, _ in atrasos
    }
    assert {dias: por_dias[dias]["faixa_atraso_tom"] for dias, _, _ in atrasos} == {
        dias: tom for dias, _, tom in atrasos
    }

    resumo = carregar_resumo_inicio(usuario, contrato.pk, hoje=hoje)
    assert resumo["resumo_atrasos"] == {
        "quantidade": 4,
        "faixas": [
            {"rotulo": rotulo, "quantidade": 1, "tom": tom}
            for _, rotulo, tom in atrasos
        ],
    }

    client.force_login(usuario)
    pendencias = client.get(reverse("acoes:pendencias"), {"contrato": contrato.pk})
    ver_todos = client.get(
        reverse("acoes:janela", args=("analise-cliente",)), {"contrato": contrato.pk}
    )
    inicio = client.get(reverse("inicio"), {"contrato": contrato.pk})
    for _, rotulo, tom in atrasos:
        etiqueta = f'mesa-selo mesa-selo-faixa-{tom}">{rotulo}'
        html_pendencias = pendencias.content.decode()
        assert etiqueta in html_pendencias
        assert etiqueta in ver_todos.content.decode()
        assert f'<li class="mesa-faixa mesa-faixa--{tom}"><span>{rotulo}</span><strong>1</strong></li>' in inicio.content.decode()


@pytest.mark.django_db
def test_perfil_sem_faixas_mantem_atraso_sem_etiqueta_ou_chips(
    contrato, perfil_modelo, usuario, client
):
    perfil_modelo.definicao["prazos"].pop("faixas_atraso")
    regra = perfil_modelo.definicao["prazos"]["regras"][0]
    regra.update(dias=1, tipo_dia="corridos")
    perfil_modelo.save(update_fields=("definicao",))
    documento = _documento(contrato, "DE-15.25.00.00-6B3-1001")
    _emissao(documento, HOJE - timedelta(days=4))

    mesa = carregar_minha_mesa(usuario, contrato.pk, hoje=HOJE)
    item = _janela(mesa, "analise-cliente")["itens"][0]
    resumo = carregar_resumo_inicio(usuario, contrato.pk, hoje=HOJE)["resumo_atrasos"]
    client.force_login(usuario)
    pendencias = client.get(reverse("acoes:pendencias"), {"contrato": contrato.pk})

    assert item["atrasado"] is True
    assert item["faixa_atraso"] is None
    assert resumo == {"quantidade": 1, "faixas": []}
    assert 'class="mesa-selo mesa-selo-faixa-' not in pendencias.content.decode()
