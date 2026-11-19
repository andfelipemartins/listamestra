from datetime import timedelta
from pathlib import Path
import re

import pytest
import yaml
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import resolve, reverse
from django.utils import timezone

from contratos.models import Contrato, Participacao, PerfilContrato
from documentos.models import Documento
from importacoes.models import IndiceDocumentos, ItemPrevisto


METRO = Path(__file__).resolve().parents[2] / "core" / "perfil" / "exemplos" / "metro.yaml"


def test_base_renderiza_topo_e_menu_fixos():
    request = RequestFactory().get(reverse("inicio"))
    request.resolver_match = resolve(request.path)
    html = render_to_string(
        "base.html",
        {
            "request": request,
            "user": AnonymousUser(),
            "contratos_painel": [],
        },
    )

    assert 'class="topbar topbar--fixed"' in html
    assert 'class="sidebar sidebar--fixed"' in html


@pytest.mark.django_db
def test_filtros_get_aplicam_sem_botao_e_limpar_mantem_caixa_aberta(client):
    contrato = Contrato.objects.create(
        nome="Contrato de layout",
        codigo_interno="CT-LAYOUT",
        cliente="Cliente de teste",
    )
    definicao = yaml.safe_load(METRO.read_text(encoding="utf-8"))
    inicio = timezone.localdate() - timedelta(days=30)
    definicao["vigencia_inicio"] = inicio.isoformat()
    PerfilContrato.objects.create(
        contrato=contrato,
        versao=1,
        vigencia_inicio=inicio,
        definicao=definicao,
    )
    usuario = get_user_model().objects.create_user(username="layout", password="senha")
    Participacao.objects.create(
        usuario=usuario,
        contrato=contrato,
        papel=get_user_model().Perfil.ADMIN,
    )
    indice = IndiceDocumentos.objects.create(
        contrato=contrato,
        codigo="ID-LAYOUT",
        revisao="1",
        fonte=IndiceDocumentos.Fonte.EXCEL_ID,
        arquivo_nome="ID-LAYOUT.xlsx",
        importado_em=timezone.now(),
    )
    for tipo, sequencial in (("DE", "9101"), ("MC", "9102")):
        documento = Documento.objects.create(
            contrato=contrato,
            identificador_base=f"{tipo}-15.25.00.00-6A1-{sequencial}",
            tipo=tipo,
            trecho="25",
            disciplina="P7",
            titulo=f"Documento {tipo}",
            atributos={
                "tipo": tipo,
                "trecho": "25",
                "subtrecho": "00",
                "unidade": "00",
                "etapa": "6",
                "classe": "A",
                "subclasse": "1",
                "sequencial": sequencial,
            },
        )
        ItemPrevisto.objects.create(indice=indice, documento=documento, titulo=documento.titulo)

    client.force_login(usuario)
    url = reverse("painel", args=(contrato.pk,))
    resposta_filtrada = client.get(url, {"tipo": "MC", "trecho": "25", "por": "trecho"})
    html_filtrado = resposta_filtrada.content.decode()

    assert resposta_filtrada.status_code == 200
    assert "Documentos previstos em conta</span><strong>1</strong>" in html_filtrado
    assert re.search(r"<noscript>\s*<button[^>]*>Aplicar filtros</button>\s*</noscript>", html_filtrado)
    assert "Aplicar filtros" not in re.sub(r"<noscript>.*?</noscript>", "", html_filtrado, flags=re.DOTALL)
    assert 'name="tipo" value="MC" checked' in html_filtrado
    assert 'name="trecho" value="25" checked' in html_filtrado
    assert 'name="tipo" value="DE" checked' not in html_filtrado
    assert '<nav class="painel-filtros-ativos" aria-label="Filtros ativos">' in html_filtrado
    assert "Limpar todos</a>" in html_filtrado

    links_remover = re.findall(
        r'<a class="painel-filtro-remover" aria-label="[^"]*"\s+href="([^"]*)">×</a>',
        html_filtrado,
    )
    assert len(links_remover) == 2
    url_remover_tipo = next(href for href in links_remover if "tipo=MC" not in href)
    url_remover_trecho = next(href for href in links_remover if "tipo=MC" in href)
    assert "tipo=" not in url_remover_tipo
    assert "trecho=25" in url_remover_tipo
    assert "por=trecho" in url_remover_tipo
    assert "tipo=MC" in url_remover_trecho
    assert "trecho=" not in url_remover_trecho
    assert "por=trecho" in url_remover_trecho
    assert f'href="{url}?por=trecho&amp;manter_filtros_abertos=1">Limpar todos</a>' in html_filtrado

    resposta_limpa = client.get(url, {"por": "trecho", "manter_filtros_abertos": "1"})
    html_limpo = resposta_limpa.content.decode()
    assert "Documentos previstos em conta</span><strong>2</strong>" in html_limpo
    assert '<details class="painel-filtros" open>' in html_limpo
    assert 'class="painel-filtros-ativos"' not in html_limpo
