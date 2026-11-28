from datetime import date, datetime
from pathlib import Path

import pytest
import yaml
from django.urls import reverse

from contas.models import Usuario
from contratos.models import Contrato, Participacao, PerfilContrato
from documentos.models import (
    ColunaPersonalizada,
    Documento,
    Emissao,
    ValorColunaPersonalizada,
)
from documentos.servicos import (
    criar_coluna_personalizada,
    desativar_coluna_personalizada,
    salvar_valor_coluna_personalizada,
)

PERFIL_METRO = Path(__file__).resolve().parents[2] / "core" / "perfil" / "exemplos" / "metro.yaml"


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato do block-096",
        codigo_interno="CT-B096",
        cliente="Cliente de teste",
    )


@pytest.fixture
def perfil_modelo(contrato):
    with PERFIL_METRO.open(encoding="utf-8") as arquivo:
        definicao = _json_compatibilidade(yaml.safe_load(arquivo))
    definicao["vigencia_inicio"] = "2020-01-01"
    return PerfilContrato.objects.create(
        contrato=contrato,
        versao=1,
        vigencia_inicio=date(2020, 1, 1),
        definicao=definicao,
    )


@pytest.fixture
def administrador(contrato, django_user_model):
    usuario = django_user_model.objects.create_user(
        username="admin-block096",
        password="senha-segura",
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


def _json_compatibilidade(valor):
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {chave: _json_compatibilidade(item) for chave, item in valor.items()}
    if isinstance(valor, list):
        return [_json_compatibilidade(item) for item in valor]
    return valor


def _documento(contrato, sequencial):
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
            "linha": "15",
            "trecho": "25",
            "subtrecho": "00",
            "unidade": "00",
            "etapa": "6",
            "classe": "A1",
            "sequencial": f"{sequencial:04d}",
        },
    )
    Emissao.objects.create(
        documento=documento,
        revisao="1",
        versao=None,
        fase=Emissao.Fase.ORIGINAL,
        data_emissao=date(2026, 1, 1),
        origem=Emissao.Origem.CLIENTE,
    )
    return documento


def _criar_coluna(admin, contrato, nome="Documento de retorno", tipo="texto", nivel="documento", opcoes=None):
    return criar_coluna_personalizada(
        admin,
        contrato.pk,
        nome=nome,
        tipo=tipo,
        nivel=nivel,
        opcoes=opcoes or [],
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("tipo", "opcoes"),
    [
        (ColunaPersonalizada.Tipo.TEXTO, []),
        (ColunaPersonalizada.Tipo.DATA, []),
        (ColunaPersonalizada.Tipo.LISTA, ["Pendente", "Respondido"]),
    ],
)
def test_cria_coluna_de_cada_tipo(contrato, administrador, tipo, opcoes):
    coluna = _criar_coluna(administrador, contrato, f"Campo {tipo}", tipo, opcoes=opcoes)
    assert coluna.pk and coluna.ativa
    assert coluna.tipo == tipo
    assert coluna.opcoes == opcoes


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("tipo", "opcoes", "valor"),
    [
        (ColunaPersonalizada.Tipo.DATA, [], "31/12/2026"),
        (ColunaPersonalizada.Tipo.LISTA, ["Pendente", "Respondido"], "Em aberto"),
    ],
)
def test_recusa_valor_invalido(contrato, administrador, tipo, opcoes, valor):
    documento = _documento(contrato, 1001)
    coluna = _criar_coluna(administrador, contrato, f"Campo {tipo}", tipo, opcoes=opcoes)
    with pytest.raises(ValueError):
        salvar_valor_coluna_personalizada(
            administrador,
            contrato.pk,
            documento.pk,
            coluna.pk,
            valor=valor,
            motivo="Dados recebidos do cliente",
        )
    assert not ValorColunaPersonalizada.objects.filter(coluna=coluna).exists()


@pytest.mark.django_db
def test_desativar_oculta_coluna_e_preserva_valor(
    client, contrato, perfil_modelo, administrador
):
    documento = _documento(contrato, 1001)
    coluna = _criar_coluna(administrador, contrato, "MR de retorno")
    salvar_valor_coluna_personalizada(
        administrador,
        contrato.pk,
        documento.pk,
        coluna.pk,
        valor="ANA-MR-25-2026",
        motivo="Vínculo confirmado",
    )
    client.force_login(administrador)
    assert coluna.nome in client.get(
        reverse("lista_mestra"), {"contrato": contrato.pk}
    ).content.decode("utf-8")
    desativar_coluna_personalizada(administrador, contrato.pk, coluna.pk)
    coluna.refresh_from_db()
    assert not coluna.ativa
    assert ValorColunaPersonalizada.objects.get(coluna=coluna, documento=documento).valor == "ANA-MR-25-2026"
    html = client.get(
        reverse("lista_mestra"), {"contrato": contrato.pk}
    ).content.decode("utf-8")
    assert coluna.nome not in html


@pytest.mark.django_db
def test_valor_data_e_salvo_em_iso(contrato, administrador):
    documento = _documento(contrato, 1001)
    coluna = _criar_coluna(administrador, contrato, "Data de resposta", tipo="data")
    valor, mudou = salvar_valor_coluna_personalizada(
        administrador,
        contrato.pk,
        documento.pk,
        coluna.pk,
        valor=date(2026, 12, 31),
        motivo="Data confirmada",
    )
    assert mudou
    assert valor.valor == "2026-12-31"


@pytest.mark.django_db
def test_tela_do_admin_cria_e_edita_coluna(
    client, contrato, perfil_modelo, administrador
):
    client.force_login(administrador)
    url = reverse("lista_mestra_colunas")
    resposta = client.post(
        f"{url}?contrato={contrato.pk}",
        {
            "contrato": contrato.pk,
            "acao": "criar_coluna",
            "nome": "Documento de retorno",
            "tipo": "lista",
            "nivel": "documento",
            "opcoes": "Pendente\nRespondido",
        },
    )
    coluna = ColunaPersonalizada.objects.get(contrato=contrato)
    assert resposta.status_code == 302
    assert coluna.opcoes == ["Pendente", "Respondido"]

    resposta = client.post(
        f"{url}?contrato={contrato.pk}",
        {
            "contrato": contrato.pk,
            "acao": "editar_coluna",
            "coluna_id": coluna.pk,
            "nome": "MR de retorno",
            "opcoes": "Pendente\nRespondido\nCancelado",
        },
    )
    coluna.refresh_from_db()
    assert resposta.status_code == 302
    assert coluna.nome == "MR de retorno"
    assert coluna.opcoes == ["Pendente", "Respondido", "Cancelado"]


@pytest.mark.django_db
def test_edicao_na_pasta_exige_motivo_e_registra_atividade(
    client, contrato, perfil_modelo, administrador
):
    documento = _documento(contrato, 1001)
    coluna = _criar_coluna(administrador, contrato)
    client.force_login(administrador)
    url = reverse("documento_pasta", args=(contrato.pk, documento.pk))
    sem_motivo = client.post(
        url,
        {"acao": "valor_coluna_personalizada", "coluna_id": coluna.pk, "valor": "ANA-MR-25-2026"},
    )
    assert sem_motivo.status_code == 302
    assert not ValorColunaPersonalizada.objects.filter(coluna=coluna).exists()

    resposta = client.post(
        url,
        {
            "acao": "valor_coluna_personalizada",
            "coluna_id": coluna.pk,
            "valor": "ANA-MR-25-2026",
            "motivo": "Vincular resposta do cliente",
        },
        follow=True,
    )
    valor = ValorColunaPersonalizada.objects.get(coluna=coluna, documento=documento)
    historico = valor.history.latest()
    html = resposta.content.decode("utf-8")
    assert resposta.status_code == 200
    assert historico.history_change_reason == "Vincular resposta do cliente"
    assert historico.history_user == administrador
    assert "Motivo: Vincular resposta do cliente" in html
    assert "ANA-MR-25-2026" in html


@pytest.mark.django_db
def test_previa_lote_aplica_e_reaplica_sem_duplicar(
    client, contrato, perfil_modelo, administrador
):
    aceito = _documento(contrato, 1001)
    conflito = _documento(contrato, 1002)
    coluna = _criar_coluna(administrador, contrato, "MR de retorno")
    salvar_valor_coluna_personalizada(
        administrador,
        contrato.pk,
        conflito.pk,
        coluna.pk,
        valor="OUTRO-MR-01-2026",
        motivo="Registro inicial",
    )
    client.force_login(administrador)
    url = reverse("lista_mestra_coluna_lote", args=(coluna.pk,))
    dados = {
        "contrato": contrato.pk,
        "codigos": f"{aceito.identificador_base}\n{conflito.identificador_base}\nDE-INEXISTENTE",
        "valor": "ANA-MR-25-2026",
        "motivo": "Vincular remessa de resposta",
    }
    previa = client.post(url, {**dados, "acao": "prever"})
    html = previa.content.decode("utf-8")
    assert previa.status_code == 200
    assert "Aceitos (1)" in html and "Conflitos (1)" in html and "Não encontrados (1)" in html

    aplicado = client.post(url, {**dados, "acao": "aplicar"})
    assert aplicado.status_code == 302
    valor_aceito = ValorColunaPersonalizada.objects.get(coluna=coluna, documento=aceito)
    assert valor_aceito.valor == "ANA-MR-25-2026"
    assert ValorColunaPersonalizada.objects.get(coluna=coluna, documento=conflito).valor == "OUTRO-MR-01-2026"
    assert valor_aceito.history.count() == 1
    client.post(url, {**dados, "acao": "aplicar"})
    valor_aceito.refresh_from_db()
    assert ValorColunaPersonalizada.objects.filter(coluna=coluna, documento=aceito).count() == 1
    assert valor_aceito.history.count() == 1
    client.post(url, {**dados, "acao": "aplicar", "substituir": "on"})
    assert ValorColunaPersonalizada.objects.get(coluna=coluna, documento=conflito).valor == "ANA-MR-25-2026"
    assert ValorColunaPersonalizada.objects.get(coluna=coluna, documento=conflito).history.count() == 2


@pytest.mark.django_db
def test_lista_mestra_mostra_filtra_painel_e_respeita_nivel_revisao(
    client, contrato, perfil_modelo, administrador
):
    documento = _documento(contrato, 1001)
    primeira = documento.emissoes.get()
    segunda = Emissao.objects.create(
        documento=documento,
        revisao="2",
        versao=None,
        fase=Emissao.Fase.ORIGINAL,
        data_emissao=date(2026, 2, 1),
        origem=Emissao.Origem.CLIENTE,
    )
    doc_coluna = _criar_coluna(administrador, contrato, "Documento de retorno")
    rev_coluna = _criar_coluna(
        administrador,
        contrato,
        "MR por revisão",
        nivel=ColunaPersonalizada.Nivel.REVISAO,
    )
    salvar_valor_coluna_personalizada(
        administrador,
        contrato.pk,
        documento.pk,
        doc_coluna.pk,
        valor="ANA-MR-25-2026",
        motivo="Vínculo confirmado",
    )
    salvar_valor_coluna_personalizada(
        administrador,
        contrato.pk,
        documento.pk,
        rev_coluna.pk,
        emissao_id=segunda.pk,
        valor="ANA-MR-26-2026",
        motivo="Resposta enviada na revisão 2",
    )
    client.force_login(administrador)
    todas = client.get(reverse("lista_mestra"), {"contrato": contrato.pk})
    filtrada = client.get(reverse("lista_mestra"), {"contrato": contrato.pk, "q": "ANA-MR-26-2026"})
    painel = client.get(reverse("documento_painel", args=(contrato.pk, documento.pk)))
    linhas = todas.context["pagina"].object_list
    por_emissao = {linha["emissao"].pk: linha for linha in linhas}
    primeira_celula = {
        celula["coluna"]["chave"]: celula["valor"]
        for celula in por_emissao[primeira.pk]["celulas_lista_mestra"]
    }
    segunda_celula = {
        celula["coluna"]["chave"]: celula["valor"]
        for celula in por_emissao[segunda.pk]["celulas_lista_mestra"]
    }

    assert "Documento de retorno" in todas.content.decode("utf-8")
    assert primeira_celula[f"personalizada:{rev_coluna.pk}"] == ""
    assert segunda_celula[f"personalizada:{rev_coluna.pk}"] == "ANA-MR-26-2026"
    assert filtrada.context["total_filtrado"] == 1
    assert filtrada.context["pagina"].object_list[0]["emissao"].pk == segunda.pk
    assert "ANA-MR-25-2026" in painel.content.decode("utf-8")
    assert "ANA-MR-26-2026" in painel.content.decode("utf-8")
