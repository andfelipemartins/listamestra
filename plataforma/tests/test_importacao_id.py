from datetime import date, datetime
from io import BytesIO
from pathlib import Path

import pytest
import yaml
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook

from core.perfil import perfil_de_dict
from contratos.models import Contrato, Participacao, PerfilContrato
from documentos.models import CodigoDocumento, Documento
from importacoes.id_excel import FORMATOS_ID, gerar_previa_id, gerar_previa_linhas_recusadas
from importacoes.models import InconsistenciaImportacao, ImportacaoID, IndiceDocumentos, ItemPrevisto
from importacoes.services import aplicar_previa, previstos_vigentes


RAIZ_REPOSITORIO = Path(__file__).resolve().parents[2]
PERFIL_METRO = RAIZ_REPOSITORIO / "core" / "perfil" / "exemplos" / "metro.yaml"
CODIGO_1001 = "DE-15.25.00.00-6A1-1001"
CODIGO_1002 = "DE-15.25.00.00-6A1-1002"


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato de importação",
        codigo_interno="CT-ID",
        cliente="Cliente de teste",
    )


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


def definicao_metro_atualizada():
    with PERFIL_METRO.open(encoding="utf-8") as arquivo:
        return _json_compatibility(yaml.safe_load(arquivo))


def remover_a7_do_perfil(perfil):
    definicao = definicao_metro_atualizada()
    campo_classe = next(
        campo
        for campo in definicao["codigo"]["segmentos"]
        if campo.get("nome") == "classe"
    )
    campo_classe["valores"].pop("A7")
    perfil.definicao = definicao
    perfil.save(update_fields=["definicao"])


def _json_compatibility(valor):
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {chave: _json_compatibility(item) for chave, item in valor.items()}
    if isinstance(valor, list):
        return [_json_compatibility(item) for item in valor]
    return valor


def criar_excel_id(linhas, *, formato="excel_id"):
    definicao = FORMATOS_ID[formato]
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = definicao["planilha"]
    cabecalhos_base = [
        definicao["cabecalho_titulo"],
        *definicao["cabecalhos_segmentos"].values(),
        definicao["cabecalho_codigo"],
    ]
    if formato == "extracao_pw":
        cabecalhos = [*cabecalhos_base, "Assinador_A1", definicao["cabecalho_excluido"], "NumeroContrato"]
    else:
        cabecalhos = [*cabecalhos_base, definicao["cabecalho_excluido"], "Assinador_A1"]
    worksheet.append(cabecalhos)
    for linha in linhas:
        valores = [
            linha.get("titulo", "Título sintético"),
            linha.get("tipo", "DE"),
            linha.get("linha", "15"),
            linha.get("trecho", "25"),
            linha.get("subtrecho", "00"),
            linha.get("unidade", "00"),
            linha.get("etapa", "6"),
            linha.get("classe", "A1"),
            linha.get("sequencial", "1001"),
            linha.get("codigo"),
        ]
        if formato == "extracao_pw":
            valores.extend(
                [
                    linha.get("assinador", "DADO PESSOAL SINTÉTICO"),
                    linha.get("excluido", False),
                    "CONTRATO-SINTÉTICO",
                ]
            )
        else:
            valores.extend(
                [
                    linha.get("excluido", 0),
                    linha.get("assinador", "DADO PESSOAL SINTÉTICO"),
                ]
            )
        worksheet.append(valores)
        if linha.get("formula"):
            numero_linha = worksheet.max_row
            worksheet.cell(numero_linha, len(cabecalhos_base)).value = f"=CONCAT(A{numero_linha})"
    conteudo = BytesIO()
    workbook.save(conteudo)
    conteudo.seek(0)
    return conteudo


def previa_para(arquivo, contrato, perfil_modelo, *, nome="ID-sintetico.xlsx", codigo="ID-SINTETICO", revisao="1", data=None):
    return gerar_previa_id(
        arquivo,
        nome_arquivo=nome,
        contrato_id=contrato.pk,
        perfil_id=perfil_modelo.pk,
        perfil=perfil_de_dict(perfil_modelo.definicao),
        documentos_existentes=list(
            Documento.objects.filter(contrato=contrato).values_list("identificador_base", "titulo")
        ),
        codigo_indice=codigo,
        revisao=revisao,
        data_importacao=data,
    )


@pytest.mark.django_db
def test_previa_classifica_linhas_e_aponta_a_caixa_invalida(contrato, perfil_modelo):
    interpretado = perfil_de_dict(perfil_modelo.definicao)
    codigo_base_existente = "DE-15.25.00.00-6A1-1002"
    from core.perfil.codigo import interpretar

    documento_existente = interpretar(interpretado, codigo_base_existente)
    Documento.objects.create(
        contrato=contrato,
        identificador_base=documento_existente.identificador_base,
        titulo="Título anterior",
    )
    codigo_ja_existente = interpretar(interpretado, "DE-15.25.00.00-6A1-1003")
    Documento.objects.create(
        contrato=contrato,
        identificador_base=codigo_ja_existente.identificador_base,
        titulo="Título estável",
    )
    linhas = [
        {"titulo": "Documento novo", "sequencial": "1001", "formula": True},
        {"titulo": "Título alterado", "sequencial": "1002"},
        {"titulo": "Título estável", "sequencial": "1003"},
        {"titulo": "Código quebrado", "sequencial": "10X1", "codigo": "DE-15.25.00.00-6A1-10X1"},
        {"titulo": "Documento excluído", "sequencial": "1004", "excluido": 1},
    ]
    previa = previa_para(criar_excel_id(linhas), contrato, perfil_modelo)

    assert previa.formato == "excel_id"
    assert previa.contagens == {
        "novos": 1,
        "ja_existentes": 1,
        "titulos_divergentes": 1,
        "codigos_invalidos": 1,
        "atributos_divergentes": 0,
        "linhas_ilegiveis": 0,
        "excluidos": 1,
    }
    invalido = next(linha for linha in previa.linhas if linha.categoria == "codigos_invalidos")
    assert invalido.campo_falhou == "sequencial"
    assert invalido.caixa_falhou == "sequencial"
    assert Documento.objects.filter(contrato=contrato).count() == 2


@pytest.mark.django_db
def test_importacao_e_idempotente_e_revisao_nova_substitui_a_anterior(contrato, perfil_modelo):
    arquivo = criar_excel_id(
        [
            {"titulo": "Documento ativo", "sequencial": "1001"},
            {"titulo": "Documento excluído", "sequencial": "1002", "excluido": 1},
        ]
    )
    previa = previa_para(arquivo, contrato, perfil_modelo, codigo="ID-01", revisao="1")

    indice = aplicar_previa(previa, contrato=contrato, perfil_modelo=perfil_modelo)
    total_historico_documento = sum(
        documento.history.count() for documento in Documento.objects.filter(contrato=contrato)
    )
    repetir = previa_para(
        criar_excel_id(
            [
                {"titulo": "Documento ativo", "sequencial": "1001"},
                {"titulo": "Documento excluído", "sequencial": "1002", "excluido": 1},
            ]
        ),
        contrato,
        perfil_modelo,
        codigo="ID-01",
        revisao="1",
    )
    mesmo_indice = aplicar_previa(repetir, contrato=contrato, perfil_modelo=perfil_modelo)

    assert indice.pk == mesmo_indice.pk
    assert IndiceDocumentos.objects.count() == 1
    assert ItemPrevisto.objects.filter(indice=indice).count() == 2
    assert total_historico_documento == sum(
        documento.history.count() for documento in Documento.objects.filter(contrato=contrato)
    )
    assert ItemPrevisto.objects.get(indice=indice, documento__identificador_base__endswith="1002").excluido

    revisao_nova = previa_para(
        criar_excel_id([{"titulo": "Documento ativo", "sequencial": "1001"}]),
        contrato,
        perfil_modelo,
        codigo="ID-01",
        revisao="2",
    )
    indice_novo = aplicar_previa(revisao_nova, contrato=contrato, perfil_modelo=perfil_modelo)
    indice.refresh_from_db()

    assert not indice.vigente
    assert indice.history.first().vigente is False
    assert indice_novo.vigente
    assert IndiceDocumentos.objects.filter(vigente=True).count() == 1


@pytest.mark.django_db
def test_importa_linhas_validas_e_registra_invalidas_sem_bloquear(contrato, perfil_modelo):
    previa = previa_para(
        criar_excel_id(
            [
                {"titulo": "Documento válido", "sequencial": "1001"},
                {
                    "titulo": "Documento inválido",
                    "sequencial": "10X2",
                    "codigo": "DE-15.25.00.00-6A1-10X2",
                },
            ]
        ),
        contrato,
        perfil_modelo,
        codigo="ID-PARCIAL",
    )

    indice = aplicar_previa(previa, contrato=contrato, perfil_modelo=perfil_modelo)

    importacao = ImportacaoID.objects.get(indice=indice)
    inconsistencia = InconsistenciaImportacao.objects.get(importacao_id=importacao)
    assert previa.linhas_validas == 1
    assert previa.linhas_fora == 1
    assert importacao.linhas_validas == 1
    assert importacao.linhas_invalidas == 1
    assert ItemPrevisto.objects.filter(indice=indice).count() == 1
    assert inconsistencia.numero_linha == 3
    assert inconsistencia.codigo_lido == "DE-15.25.00.00-6A1-10X2"
    assert inconsistencia.caixa_falhou == "sequencial"
    assert any(valor == previa.linhas[1].titulo for valor in inconsistencia.dados_linha.values())
    assert not any("Assinador" in nome for nome in inconsistencia.dados_linha)
    assert "DADO PESSOAL SINTÃ‰TICO" not in str(inconsistencia.dados_linha)


@pytest.mark.django_db
def test_recusas_ficam_agrupadas_por_caixa_e_valor_e_exigem_acesso(contrato, perfil_modelo, client, django_user_model):
    remover_a7_do_perfil(perfil_modelo)
    previa = previa_para(
        criar_excel_id(
            [
                {"titulo": "Documento A7 um", "classe": "A7", "sequencial": "1001", "codigo": "DE-15.25.00.00-6A7-1001"},
                {"titulo": "Documento A7 dois", "classe": "A7", "sequencial": "1002", "codigo": "DE-15.25.00.00-6A7-1002"},
                {"titulo": "", "sequencial": "1003", "codigo": "DE-15.25.00.00-6A1-1003"},
            ]
        ),
        contrato,
        perfil_modelo,
        codigo="ID-RECUSAS",
    )
    indice = aplicar_previa(previa, contrato=contrato, perfil_modelo=perfil_modelo)
    administrador = django_user_model.objects.create_superuser(
        username="admin-recusadas",
        email="admin-recusadas@example.com",
        password="senha-segura",
    )
    client.force_login(administrador)

    resposta = client.get(reverse("linhas_recusadas", args=(contrato.pk,)))

    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert "Reprocessar com o perfil vigente" in html
    assert "Código inválido — 2 linhas" in html
    assert "Linha ilegível — 1 linha" in html
    assert "Corrija o código na planilha ou no PW e importe de novo." in html
    assert "Descartar" not in html
    assert "ID-RECUSAS" in html
    assert "importada em" in html

    participante = django_user_model.objects.create_user(username="participante", password="senha")
    Participacao.objects.create(usuario=participante, contrato=contrato, papel="equipe")
    client.force_login(participante)
    url = reverse("linhas_recusadas", args=(contrato.pk,))
    resposta_participante = client.get(url)
    assert resposta_participante.status_code == 200
    html_participante = resposta_participante.content.decode()
    assert "Código inválido — 2 linhas" in html_participante
    assert "Corrija o código na planilha ou no PW e importe de novo." in html_participante
    assert "Reprocessar com o perfil vigente" not in html_participante
    assert client.post(url, {"acao": "prever_reprocessamento", "importacao_id": indice.importacoes.first().pk}).status_code == 403
    assert client.post(url, {"acao": "confirmar_reprocessamento"}).status_code == 403

    sem_participacao = django_user_model.objects.create_user(username="sem-participacao", password="senha")
    client.force_login(sem_participacao)
    assert client.get(url).status_code == 403


@pytest.mark.django_db
def test_reprocessa_com_perfil_vigente_e_permanece_idempotente(contrato, perfil_modelo):
    remover_a7_do_perfil(perfil_modelo)
    previa_inicial = previa_para(
        criar_excel_id(
            [{"titulo": "Documento A7 recuperado", "classe": "A7", "sequencial": "1001", "codigo": "DE-15.25.00.00-6A7-1001"}]
        ),
        contrato,
        perfil_modelo,
        codigo="ID-REPROCESSAR",
    )
    indice = aplicar_previa(previa_inicial, contrato=contrato, perfil_modelo=perfil_modelo)
    importacao = ImportacaoID.objects.get(indice=indice)
    inconsistencia = InconsistenciaImportacao.objects.get(importacao_id=importacao)

    definicao_v2 = definicao_metro_atualizada()
    perfil_v2 = PerfilContrato.objects.create(
        contrato=contrato,
        versao=2,
        vigencia_inicio=date.fromisoformat(definicao_v2["vigencia_inicio"]),
        definicao=definicao_v2,
    )
    assert perfil_de_dict(perfil_v2.definicao).codigo.campos[6].valores["A7"] == "Qualidade (a confirmar)"
    previa_reprocessada = gerar_previa_linhas_recusadas(
        [inconsistencia],
        contrato_id=contrato.pk,
        perfil_id=perfil_v2.pk,
        perfil=perfil_de_dict(perfil_v2.definicao),
        documentos_existentes=[],
    )
    assert previa_reprocessada.linhas_validas == 1
    assert previa_reprocessada.linhas_fora == 0

    aplicar_previa(
        previa_reprocessada,
        contrato=contrato,
        perfil_modelo=perfil_v2,
        inconsistencias_existentes=[inconsistencia],
    )
    inconsistencia.refresh_from_db()
    primeira_resolucao = inconsistencia.resolvida_em
    aplicar_previa(
        previa_reprocessada,
        contrato=contrato,
        perfil_modelo=perfil_v2,
        inconsistencias_existentes=[inconsistencia],
    )

    assert primeira_resolucao is not None
    inconsistencia.refresh_from_db()
    assert inconsistencia.resolvida_em == primeira_resolucao
    assert ImportacaoID.objects.count() == 1
    assert IndiceDocumentos.objects.get(pk=indice.pk).pk == indice.pk
    assert ItemPrevisto.objects.filter(indice=indice).count() == 1
    documento = Documento.objects.get(contrato=contrato)
    assert documento.titulo == "Documento A7 recuperado"
    assert CodigoDocumento.objects.get(documento=documento, perfil=perfil_v2).codigo == "DE-15.25.00.00-6A7-1001"


@pytest.mark.django_db
def test_tela_previsualiza_e_confirma_reprocessamento(client, contrato, perfil_modelo, django_user_model):
    remover_a7_do_perfil(perfil_modelo)
    previa_inicial = previa_para(
        criar_excel_id(
            [{"titulo": "Documento A7 da tela", "classe": "A7", "sequencial": "1001", "codigo": "DE-15.25.00.00-6A7-1001"}]
        ),
        contrato,
        perfil_modelo,
        codigo="ID-TELA-RECUSADAS",
    )
    indice = aplicar_previa(previa_inicial, contrato=contrato, perfil_modelo=perfil_modelo)
    importacao = ImportacaoID.objects.get(indice=indice)
    incidencia = InconsistenciaImportacao.objects.get(importacao_id=importacao)
    definicao_v2 = definicao_metro_atualizada()
    PerfilContrato.objects.create(
        contrato=contrato,
        versao=2,
        vigencia_inicio=date.fromisoformat(definicao_v2["vigencia_inicio"]),
        definicao=definicao_v2,
    )
    admin = django_user_model.objects.create_user(
        username="admin-reprocessa-ui", password="senha"
    )
    Participacao.objects.create(usuario=admin, contrato=contrato, papel="admin")
    client.force_login(admin)
    url = reverse("linhas_recusadas", args=(contrato.pk,))

    previa_resposta = client.post(
        url,
        {"acao": "prever_reprocessamento", "importacao_id": importacao.pk},
    )

    assert previa_resposta.status_code == 200
    assert "1 agora são válidas" in previa_resposta.content.decode()
    assert not Documento.objects.filter(contrato=contrato).exists()

    resposta = client.post(url, {"acao": "confirmar_reprocessamento"}, follow=True)

    assert resposta.status_code == 200
    assert "1 linhas reprocessadas" in resposta.content.decode()
    incidencia.refresh_from_db()
    assert incidencia.resolvida_em is not None
    assert ItemPrevisto.objects.filter(indice=indice).count() == 1


@pytest.mark.django_db
def test_participante_sem_papel_admin_consulta_recusas_mas_nao_reprocessa(
    client, contrato, perfil_modelo, django_user_model
):
    remover_a7_do_perfil(perfil_modelo)
    previa = previa_para(
        criar_excel_id(
            [{"titulo": "Documento A7 recusado", "classe": "A7", "sequencial": "1001", "codigo": "DE-15.25.00.00-6A7-1001"}]
        ),
        contrato,
        perfil_modelo,
        codigo="ID-RECUSAS-EQUIPE",
    )
    indice = aplicar_previa(previa, contrato=contrato, perfil_modelo=perfil_modelo)
    importacao = ImportacaoID.objects.get(indice=indice)
    participante = django_user_model.objects.create_user(username="equipe-recusa", password="senha")
    Participacao.objects.create(
        usuario=participante,
        contrato=contrato,
        papel="equipe",
        ativo=True,
    )
    client.force_login(participante)
    url = reverse("linhas_recusadas", args=(contrato.pk,))

    resposta = client.get(url)

    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert "ID-RECUSAS-EQUIPE" in html
    assert "Reprocessar com o perfil vigente" not in html
    assert "Confirmar reprocessamento" not in html
    assert client.post(
        url,
        {"acao": "prever_reprocessamento", "importacao_id": importacao.pk},
    ).status_code == 403
    assert client.post(url, {"acao": "confirmar_reprocessamento"}).status_code == 403


@pytest.mark.django_db
def test_previsto_vigente_e_uniao_de_dois_ids(contrato, perfil_modelo):
    primeira = previa_para(
        criar_excel_id([{"titulo": "Documento compartilhado", "sequencial": "1001"}]),
        contrato,
        perfil_modelo,
        codigo="ID-A",
    )
    segunda = previa_para(
        criar_excel_id(
            [
                {"titulo": "Documento compartilhado", "sequencial": "1001"},
                {"titulo": "Documento adicional", "sequencial": "1002"},
            ]
        ),
        contrato,
        perfil_modelo,
        codigo="ID-B",
    )
    aplicar_previa(primeira, contrato=contrato, perfil_modelo=perfil_modelo)
    aplicar_previa(segunda, contrato=contrato, perfil_modelo=perfil_modelo)

    previstos = list(previstos_vigentes(contrato))
    assert len(previstos) == 2
    assert {item.documento.titulo for item in previstos} == {
        "Documento compartilhado",
        "Documento adicional",
    }


@pytest.mark.django_db
def test_detecta_extracao_pw_e_usa_data_como_revisao(contrato, perfil_modelo):
    data1 = date(2026, 11, 17)
    data2 = date(2026, 11, 18)
    previa1 = previa_para(
        criar_excel_id(
            [{"titulo": "Documento da extração", "sequencial": "1001", "codigo": CODIGO_1001}],
            formato="extracao_pw",
        ),
        contrato,
        perfil_modelo,
        nome="ID PW.xlsx",
        data=data1,
    )
    indice1 = aplicar_previa(previa1, contrato=contrato, perfil_modelo=perfil_modelo)
    previa2 = previa_para(
        criar_excel_id(
            [{"titulo": "Documento da extração", "sequencial": "1001", "codigo": CODIGO_1001}],
            formato="extracao_pw",
        ),
        contrato,
        perfil_modelo,
        nome="ID PW.xlsx",
        data=data2,
    )
    indice2 = aplicar_previa(previa2, contrato=contrato, perfil_modelo=perfil_modelo)

    assert previa1.fonte == "extracao_pw"
    assert previa1.codigo_indice == "EXTRACAO-PW"
    assert previa1.revisao == "2026-11-17"
    assert not IndiceDocumentos.objects.get(pk=indice1.pk).vigente
    assert indice2.vigente
    assert "DADO PESSOAL SINTÉTICO" not in str(previa2)


@pytest.mark.django_db
def test_linha_com_atributo_pw_divergente_aponta_coluna(contrato, perfil_modelo):
    previa = previa_para(
        criar_excel_id(
            [
                {
                    "titulo": "Linha deslocada",
                    "sequencial": "1001",
                    "codigo": CODIGO_1001,
                    "classe": "B1",
                }
            ],
            formato="extracao_pw",
        ),
        contrato,
        perfil_modelo,
        nome="ID PW.xlsx",
        data=date(2026, 11, 18),
    )

    assert previa.contagens["atributos_divergentes"] == 1
    assert "Name diz classe e subclasse A1" in previa.linhas[0].mensagem
    assert "diz B1" in previa.linhas[0].mensagem


@pytest.mark.django_db
def test_tela_staff_mostra_previa_htmx_e_confirma_importacao(client, contrato, perfil_modelo, django_user_model):
    administrador = django_user_model.objects.create_superuser(
        username="admin-importador",
        email="admin-importador@example.com",
        password="senha-segura",
    )
    client.force_login(administrador)
    arquivo = criar_excel_id([{"titulo": "Documento na tela", "sequencial": "1001"}])
    upload = SimpleUploadedFile("ID-TESTE-1.xlsx", arquivo.read(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    resposta = client.post(
        reverse("importar_id"),
        {
            "acao": "prever",
            "contrato": str(contrato.pk),
            "codigo_id": "ID-TESTE",
            "revisao": "1",
            "arquivo": upload,
        },
        HTTP_HX_REQUEST="true",
    )

    assert resposta.status_code == 200
    assert b"ID-TESTE-1.xlsx" in resposta.content
    assert IndiceDocumentos.objects.count() == 0

    resposta = client.post(reverse("importar_id"), {"acao": "confirmar"}, follow=True)

    assert resposta.status_code == 200
    assert IndiceDocumentos.objects.get().importado_por == administrador
    assert ItemPrevisto.objects.count() == 1
    assert b"importado com 1 linhas v\xc3\xa1lidas" in resposta.content


@pytest.mark.django_db
def test_extracao_pw_separa_linha_defeituosa_de_atributos_divergentes(contrato, perfil_modelo):
    codigo = "DE-15.25.00.00-6A1-1009"
    previa = previa_para(
        criar_excel_id(
            [
                {"titulo": "Documento com Name inválido", "codigo": "19/11/2026"},
                {"titulo": "", "codigo": codigo, "tipo": ""},
                {"titulo": "Sigla divergente", "codigo": codigo, "tipo": "RT", "sequencial": "1009"},
                {"titulo": "Sequencial divergente", "codigo": codigo, "sequencial": "1006"},
            ],
            formato="extracao_pw",
        ),
        contrato,
        perfil_modelo,
    )

    assert [linha.categoria for linha in previa.linhas] == [
        "linhas_ilegiveis",
        "linhas_ilegiveis",
        "atributos_divergentes",
        "atributos_divergentes",
    ]
    assert previa.linhas[0].mensagem == (
        "A linha veio defeituosa da extração do PW (colunas fora do lugar). "
        "Reextraia essa disciplina e importe de novo."
    )
    assert previa.linhas[1].mensagem == previa.linhas[0].mensagem
    assert previa.linhas[2].mensagem == (
        "No PW, o Name diz tipo documental DE, mas a coluna Sigla diz RT. "
        "Corrija o atributo no PW ou reextraia."
    )
    assert previa.linhas[3].mensagem == (
        "No PW, o Name diz sequencial 1009, mas a coluna Sequencial diz 1006. "
        "Corrija o atributo no PW ou reextraia."
    )


@pytest.mark.django_db
def test_importacao_correta_resolve_recusa_pw_anterior_com_mesmo_codigo(contrato, perfil_modelo):
    codigo = "DE-15.25.00.00-6A1-1009"
    previa_incorreta = previa_para(
        criar_excel_id(
            [{"titulo": "Documento de teste", "codigo": codigo, "sequencial": "1006"}],
            formato="extracao_pw",
        ),
        contrato,
        perfil_modelo,
        codigo="ID-PW-CORRECAO",
    )
    indice = aplicar_previa(previa_incorreta, contrato=contrato, perfil_modelo=perfil_modelo)
    recusa = InconsistenciaImportacao.objects.get(importacao_id__indice=indice)
    assert recusa.categoria == "atributos_divergentes"
    assert recusa.resolvida_em is None

    previa_correta = previa_para(
        criar_excel_id(
            [{"titulo": "Documento de teste", "codigo": codigo, "sequencial": "1009"}],
            formato="extracao_pw",
        ),
        contrato,
        perfil_modelo,
        codigo="ID-PW-CORRECAO",
    )
    aplicar_previa(previa_correta, contrato=contrato, perfil_modelo=perfil_modelo)

    recusa.refresh_from_db()
    assert recusa.resolvida_em is not None
