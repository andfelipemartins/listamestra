from pathlib import Path

import pytest
import yaml

from core.perfil.modelo import ErroPerfil, carregar_yaml, perfil_de_dict


RAIZ = Path(__file__).resolve().parents[2]


def test_metro_liga_comparacao_com_pw_e_spobras_mantem_desligada():
    metro = carregar_yaml(RAIZ / "core" / "perfil" / "exemplos" / "metro.yaml")
    spobras = carregar_yaml(RAIZ / "core" / "perfil" / "exemplos" / "spobras.yaml")

    assert metro.comparar_id_cliente is True
    assert metro.nome_id_cliente == "PW"
    assert spobras.comparar_id_cliente is False


def test_comparar_id_cliente_padrao_e_desligado():
    dados = yaml.safe_load(
        (RAIZ / "core" / "perfil" / "exemplos" / "spobras.yaml").read_text(encoding="utf-8")
    )
    dados.pop("comparar_id_cliente")

    assert perfil_de_dict(dados).comparar_id_cliente is False


@pytest.mark.parametrize("valor", [None, 0, 1, "true", "false"])
def test_comparar_id_cliente_exige_booleano(valor):
    dados = yaml.safe_load(
        (RAIZ / "core" / "perfil" / "exemplos" / "metro.yaml").read_text(encoding="utf-8")
    )
    dados["comparar_id_cliente"] = valor

    with pytest.raises(ErroPerfil, match="comparar_id_cliente.*booleano"):
        perfil_de_dict(dados)


@pytest.fixture
def metro():
    return carregar_yaml(RAIZ / "core" / "perfil" / "exemplos" / "metro.yaml")
