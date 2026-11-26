from copy import deepcopy
from pathlib import Path

import yaml
import pytest

from core.perfil.modelo import ErroPerfil, carregar_yaml, perfil_de_dict


ROOT = Path(__file__).parents[2]


def _metro_dict():
    caminho = ROOT / "core" / "perfil" / "exemplos" / "metro.yaml"
    with caminho.open(encoding="utf-8") as arquivo:
        return yaml.safe_load(arquivo)


def test_motivos_de_cancelamento_padrao_sao_usados_quando_perfil_nao_declara():
    definicao = _metro_dict()
    definicao.pop("cancelamento", None)

    perfil = perfil_de_dict(definicao)

    assert [(item.id, item.rotulo) for item in perfil.cancelamento.motivos] == [
        ("desmembrado", "Desmembrado em outros documentos"),
        ("incorporado", "Incorporado a outro documento"),
        ("substituido", "Substituído por outro documento"),
        ("cliente", "Pedido do cliente"),
        ("fora_escopo", "Fora do escopo"),
        ("inviavel", "Inviável (constatado em campo)"),
        ("solucao", "Mudança de solução de projeto"),
        ("duplicado", "Duplicado / código em dobro"),
        ("outro", "Outro"),
    ]
    assert perfil.cancelamento.motivos[-1].exige_observacao is True


def test_motivos_de_cancelamento_explicitos_sao_carregados_do_perfil():
    definicao = _metro_dict()
    definicao["cancelamento"] = {
        "motivos": [
            {"id": "decisao_cliente", "rotulo": "Decisão do cliente"},
            {
                "id": "restricao_local",
                "rotulo": "Restrição local",
                "exige_observacao": True,
            },
        ]
    }

    perfil = perfil_de_dict(definicao)

    assert [(item.id, item.rotulo) for item in perfil.cancelamento.motivos] == [
        ("decisao_cliente", "Decisão do cliente"),
        ("restricao_local", "Restrição local"),
    ]
    assert perfil.cancelamento.motivos[0].exige_observacao is False
    assert perfil.cancelamento.motivos[1].exige_observacao is True


@pytest.mark.parametrize("identificador", ["Motivo", "com espaço", "", "x" * 51])
def test_perfil_recusa_id_de_motivo_de_cancelamento_invalido(identificador):
    definicao = _metro_dict()
    definicao["cancelamento"] = {
        "motivos": [{"id": identificador, "rotulo": "Motivo"}]
    }

    with pytest.raises(ErroPerfil, match="id"):
        perfil_de_dict(definicao)


def test_metro_tem_motivos_explicitos_e_spobras_usa_o_padrao():
    metro = carregar_yaml(ROOT / "core" / "perfil" / "exemplos" / "metro.yaml")
    spobras = carregar_yaml(ROOT / "core" / "perfil" / "exemplos" / "spobras.yaml")

    assert len(metro.cancelamento.motivos) == 9
    assert [item.id for item in spobras.cancelamento.motivos] == [
        item.id for item in perfil_de_dict(_metro_sem_cancelamento()).cancelamento.motivos
    ]


def _metro_sem_cancelamento():
    definicao = deepcopy(_metro_dict())
    definicao.pop("cancelamento", None)
    return definicao
