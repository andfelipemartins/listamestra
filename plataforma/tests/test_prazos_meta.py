from datetime import date
from pathlib import Path
import re
from types import SimpleNamespace

from django.template.loader import render_to_string

from core.perfil import carregar_yaml
from core.perfil.modelo import perfil_de_dict
from core.perfil.prazos import AvaliacaoPrazo
from painel.prazos import calcular_indicador_cronograma, calcular_indicadores_prazo
import yaml


METRO = Path(__file__).resolve().parents[2] / "core" / "perfil" / "exemplos" / "metro.yaml"


def test_painel_usa_metas_por_regra_e_oculta_meta_nula(monkeypatch):
    perfil = carregar_yaml(METRO)
    indicadores, analises_sem_data = calcular_indicadores_prazo(
        perfil,
        [],
        "tipo",
        None,
        date(2026, 11, 19),
        valor_recorte=lambda *_: "",
        rotulo_recorte=lambda *_: "",
    )

    monkeypatch.setattr(
        "painel.prazos.PrevisaoEmissao.objects",
        SimpleNamespace(filter=lambda **_: SimpleNamespace(exists=lambda: True)),
    )
    monkeypatch.setattr("painel.prazos.comparar_previsoes_cronograma", lambda *_args, **_kwargs: [])
    cronograma = calcular_indicador_cronograma(
        object(),
        perfil,
        [],
        "tipo",
        None,
        date(2026, 11, 19),
        valor_recorte=lambda *_: "",
        rotulo_recorte=lambda *_: "",
    )

    assert analises_sem_data == 0
    assert {item["regra"].id: item["meta_percentual"] for item in indicadores} == {
        "analise_cliente": None,
        "devolucao_nossa": 80,
    }
    assert cronograma["meta_percentual"] == 80

    html_prazos = render_to_string(
        "painel/_prazos.html",
        {
            "indicadores_prazo": indicadores,
            "indicador_cronograma": None,
            "rotulo_caixa": "Tipo",
            "analises_deduzidas_sem_data": 0,
            "user": SimpleNamespace(is_staff=False),
        },
    )
    inicio_regra_sem_meta = html_prazos.index('aria-labelledby="painel-prazo-titulo-1"')
    fim_regra_sem_meta = html_prazos.index("</article>", inicio_regra_sem_meta)
    cartao_regra_sem_meta = html_prazos[inicio_regra_sem_meta:fim_regra_sem_meta]
    assert "Linha tracejada: Meta" not in cartao_regra_sem_meta
    assert "border-left:2px dashed" not in cartao_regra_sem_meta
    assert "Linha tracejada: Meta 80%" in html_prazos

    html_cronograma = render_to_string(
        "painel/_cronograma.html",
        {
            "indicador_cronograma": {
                **cronograma,
                "tem_dados": False,
                "percentual": None,
                "previstos": 0,
                "no_prazo": 0,
                "atrasados": 0,
                "vencidos_sem_emissao": 0,
                "futuros": 0,
                "base": 0,
                "recortes": [],
            },
            "rotulo_caixa": "Tipo",
        },
    )
    assert "Linha tracejada: Meta 80%" in html_cronograma
    assert re.search(r"left:80(?:\.0)?%", html_cronograma)


def test_painel_mostra_faixas_e_contagens_de_atraso_por_regra(monkeypatch):
    with METRO.open(encoding="utf-8") as arquivo:
        dados = yaml.safe_load(arquivo)
    dados["prazos"]["regras"][1]["faixas_atraso"] = [
        {"ate_dias": 10, "rotulo": "Curto"},
        {"ate_dias": None, "rotulo": "Longo"},
    ]
    perfil = perfil_de_dict(dados)
    item = SimpleNamespace(documento=SimpleNamespace(pk=1))
    avaliacao_entregue = AvaliacaoPrazo("atrasado", date(2026, 11, 1), 3)
    avaliacao_aberta = AvaliacaoPrazo("aberto_atrasado", date(2026, 11, 1), 61)
    monkeypatch.setattr("painel.prazos.feriados_prazo", lambda *_: set())
    monkeypatch.setattr(
        "painel.prazos._itens_avaliados_da_regra",
        lambda *_: (
            [
                SimpleNamespace(avaliacao=avaliacao_entregue),
                SimpleNamespace(avaliacao=avaliacao_aberta),
            ],
            set(),
        ),
    )

    indicadores, analises_sem_data = calcular_indicadores_prazo(
        perfil,
        [item],
        "tipo",
        None,
        date(2026, 11, 19),
        valor_recorte=lambda *_: "DE",
        rotulo_recorte=lambda *_: "Desenho",
    )
    html_prazos = render_to_string(
        "painel/_prazos.html",
        {
            "indicadores_prazo": indicadores,
            "indicador_cronograma": None,
            "rotulo_caixa": "Tipo",
            "analises_deduzidas_sem_data": analises_sem_data,
            "user": SimpleNamespace(is_staff=False),
        },
    )

    assert [faixa["rotulo"] for faixa in indicadores[0]["faixas_atraso"]] == [
        "Leve",
        "Moderado",
        "Grave",
        "Crítico",
    ]
    assert [faixa["rotulo"] for faixa in indicadores[1]["faixas_atraso"]] == ["Curto", "Longo"]
    assert indicadores[0]["faixas_atraso"][0]["entregues_com_atraso"] == 1
    assert indicadores[0]["faixas_atraso"][3]["abertos_vencidos"] == 1
    assert 'role="img" aria-label="Distribuição dos atrasos:' in html_prazos
    assert "<strong>Leve</strong> (Até 5 dias): Entregues com atraso: 1; abertos vencidos: 0." in html_prazos
    assert "<strong>Crítico</strong> (Mais de 60 dias): Entregues com atraso: 0; abertos vencidos: 1." in html_prazos
    assert "<strong>Curto</strong> (Até 10 dias)" in html_prazos
    assert "<strong>Longo</strong> (Mais de 10 dias)" in html_prazos
    assert "background:var(--success-border)" in html_prazos
    assert "background:var(--danger-border)" in html_prazos
