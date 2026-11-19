from pathlib import Path
from types import SimpleNamespace

from core.perfil import carregar_yaml
from core.perfil.ciclo import rotulo_cronologico, rotulos_ciclo


ROOT = Path(__file__).resolve().parents[2]


def _perfil(nome):
    return carregar_yaml(ROOT / "core" / "perfil" / "exemplos" / f"{nome}.yaml")


def _emissao(revisao, fase, versao=1):
    return SimpleNamespace(revisao=revisao, fase=fase, versao=versao)


def test_rotulos_metro_exemplo_real_nao_contam_reabertura_como_ciclo_novo():
    metro = _perfil("metro")
    emissoes = [
        _emissao("1", "preliminar"),
        _emissao("0", "original"),
        _emissao("A1", "preliminar"),
        _emissao("A", "original", versao=2),
    ]

    assert rotulos_ciclo(metro, emissoes) == [
        "Emissão Inicial",
        "Original (aprovado)",
        "Reabertura A · Revisão 1",
        "Original A (versão 2)",
    ]


def test_rotulos_reiniciam_em_cada_reabertura():
    metro = _perfil("metro")
    emissoes = [
        _emissao("1", "preliminar"),
        _emissao("0", "original"),
        _emissao("A1", "preliminar"),
        _emissao("A2", "preliminar"),
        _emissao("A", "original"),
        _emissao("B1", "preliminar"),
        _emissao("B", "original"),
    ]

    assert rotulos_ciclo(metro, emissoes) == [
        "Emissão Inicial",
        "Original (aprovado)",
        "Reabertura A · Revisão 1",
        "Reabertura A · Revisão 2",
        "Original A",
        "Reabertura B · Revisão 1",
        "Original B",
    ]


def test_rotulos_spobras_seguem_as_series_configuradas():
    spobras = _perfil("spobras")
    emissoes = [
        _emissao("A", "preliminar", versao=None),
        _emissao("1", "original", versao=None),
        _emissao("B", "preliminar", versao=None),
        _emissao("2", "original", versao=None),
    ]

    assert rotulos_ciclo(spobras, emissoes) == [
        "Emissão Inicial",
        "Original (aprovado)",
        "Reabertura 2 · Revisão 1",
        "Original 2",
    ]


def test_perfil_sem_eixo_de_revisao_usa_rotulo_cronologico_antigo():
    perfil = SimpleNamespace(emissao=SimpleNamespace(revisao=None, versao=None))
    emissoes = [_emissao("qualquer", "preliminar"), _emissao("sem-serie", "preliminar")]

    assert rotulos_ciclo(perfil, emissoes) == rotulo_cronologico(emissoes)


def test_revisao_fora_das_series_usa_rotulo_cronologico_antigo():
    metro = _perfil("metro")
    emissoes = [_emissao("1", "preliminar"), _emissao("Z9", "preliminar")]

    assert rotulos_ciclo(metro, emissoes) == rotulo_cronologico(emissoes)
