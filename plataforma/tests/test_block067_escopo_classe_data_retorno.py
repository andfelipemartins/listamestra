from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

import pytest
import yaml
from django.utils import timezone
from openpyxl import Workbook

from core.perfil import perfil_de_dict
from contratos.models import Contrato, EscopoContrato, PerfilContrato
from documentos.models import Documento
from importacoes.models import IndiceDocumentos, ItemPrevisto
from importacoes.situacao_padrao import gerar_previa_situacao_padrao
from painel.servicos import carregar_painel


ROOT = Path(__file__).resolve().parents[2]
METRO = ROOT / "core" / "perfil" / "exemplos" / "metro.yaml"
CODIGO = "DE-15.25.00.00-6A1-1001"


@pytest.fixture
def contrato_com_perfil(db):
    contrato = Contrato.objects.create(
        nome="Contrato do block 067",
        codigo_interno="CT-B067",
        cliente="Cliente de teste",
    )
    definicao = _json_compatibility(yaml.safe_load(METRO.read_text(encoding="utf-8")))
    PerfilContrato.objects.create(
        contrato=contrato,
        versao=1,
        vigencia_inicio=timezone.localdate() - timedelta(days=30),
        definicao=definicao,
    )
    return contrato


def _json_compatibility(valor):
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {chave: _json_compatibility(item) for chave, item in valor.items()}
    if isinstance(valor, list):
        return [_json_compatibility(item) for item in valor]
    return valor


@pytest.mark.django_db
def test_filtro_usa_escopo_da_classe_sem_herdar_do_id(contrato_com_perfil):
    contrato = contrato_com_perfil
    indice = IndiceDocumentos.objects.create(
        contrato=contrato,
        codigo="ID-15.25.00.00-6A9-2001",
        revisao="1",
        fonte=IndiceDocumentos.Fonte.EXCEL_ID,
        arquivo_nome="ID-2001.xlsx",
        importado_em=timezone.now(),
    )
    indice.escopos.add(
        EscopoContrato.objects.create(contrato=contrato, nome="Arquitetura e Civil")
    )
    sistemas = Documento.objects.create(
        contrato=contrato,
        identificador_base="DOC-SISTEMAS",
        tipo="DE",
        disciplina="P7",
        atributos={"classe": "P7"},
    )
    sem_ligacao = Documento.objects.create(
        contrato=contrato,
        identificador_base="DOC-SEM-ESCOPO-CLASSE",
        tipo="DE",
        disciplina="A5",
        atributos={"classe": "A5", "tipo": "DE"},
    )
    ItemPrevisto.objects.create(indice=indice, documento=sistemas)
    ItemPrevisto.objects.create(indice=indice, documento=sem_ligacao)

    painel_sistemas = carregar_painel(contrato, filtros={"escopo": "Sistemas"})
    painel_id = carregar_painel(contrato, filtros={"escopo": "Arquitetura e Civil"})
    painel_sem_escopo = carregar_painel(
        contrato, filtros={"escopo": "__sem_escopo__"}
    )

    assert painel_sistemas["total_documentos_previstos"] == 1
    assert painel_sem_escopo["total_documentos_previstos"] == 1
    assert painel_sistemas["filtros_ativos"] == [{"rotulo": "Escopo", "valores": ["Sistemas"]}]
    assert any(
        opcao["rotulo"] == "Sem escopo"
        for filtro in painel_sistemas["filtros"]
        if filtro["nome"] == "escopo"
        for opcao in filtro["opcoes"]
    )
    assert not any(
        opcao["valor"] == "Arquitetura e Civil"
        for filtro in painel_id["filtros"]
        if filtro["nome"] == "escopo"
        for opcao in filtro["opcoes"]
    )


def _planilha_situacao(data=None, data_retorno=None):
    workbook = Workbook()
    planilha = workbook.active
    planilha.append(["Código", "Revisão", "Situação", "Data", "Data de retorno"])
    planilha.append([CODIGO, "1", "Em Análise", data, data_retorno])
    conteudo = BytesIO()
    workbook.save(conteudo)
    workbook.close()
    conteudo.seek(0)
    return conteudo


def _previa_data(data, data_retorno):
    perfil = perfil_de_dict(yaml.safe_load(METRO.read_text(encoding="utf-8")))
    return gerar_previa_situacao_padrao(
        _planilha_situacao(data, data_retorno),
        nome_arquivo="situacao.xlsx",
        contrato_id=1,
        perfil_id=1,
        perfil=perfil,
        documentos_existentes={
            CODIGO: {
                "id": 1,
                "emissoes": [
                    {
                        "id": 1,
                        "revisao": "1",
                        "data_emissao": date(2025, 1, 1),
                        "analises": [
                            {"id": 1, "situacao": "Em Análise", "data_analise": date(2025, 1, 2)}
                        ],
                    }
                ],
            }
        },
        data_importacao=date(2026, 11, 26),
    ).linhas[0]


def test_data_de_retorno_substitui_data_vazia_e_data_vazia_usa_importacao():
    vazias = _previa_data(None, None)
    retorno = _previa_data(None, date(2026, 11, 25))
    data_sem_retorno = _previa_data(date(2026, 11, 20), None)

    assert vazias.data_analise == date(2026, 11, 26)
    assert not vazias.data_informada
    assert retorno.data_analise == date(2026, 11, 25)
    assert retorno.data_informada
    assert data_sem_retorno.data_analise == date(2026, 11, 20)
    assert data_sem_retorno.data_informada


def test_data_divergente_prioriza_data_e_mostra_aviso():
    linha = _previa_data(date(2026, 11, 20), date(2026, 11, 25))

    assert linha.data_analise == date(2026, 11, 20)
    assert linha.aviso == "Data e Data de retorno são diferentes; foi considerada a coluna Data."
