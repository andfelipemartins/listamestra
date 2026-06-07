"""
tests/test_pages/test_grd_page.py

Checks estruturais da página de Geração de GRD (pages/6_GRD.py).
"""

import ast
from pathlib import Path

_PAGINA = Path("pages/6_GRD.py")


def test_grd_page_importavel_por_ast():
    ast.parse(_PAGINA.read_text(encoding="utf-8"), filename=str(_PAGINA))


def test_grd_page_usa_grd_service():
    source = _PAGINA.read_text(encoding="utf-8")
    assert "GrdService" in source
    assert "criar_grd" in source


def test_grd_page_tem_selecao_multipla():
    source = _PAGINA.read_text(encoding="utf-8")
    assert 'selection_mode="multi-row"' in source


def test_grd_page_tem_cabecalho_unico():
    """Cabeçalho da GRD preenchido uma vez (número, data, setor)."""
    source = _PAGINA.read_text(encoding="utf-8")
    assert "Cabeçalho da GRD" in source
    assert "grd_numero" in source
    assert "grd_data_envio" in source


def test_grd_page_botao_criar():
    source = _PAGINA.read_text(encoding="utf-8")
    assert "Criar GRD" in source


def test_grd_page_no_menu_entre_cadastrar_e_pesquisar():
    """main.py deve registrar a página GRD entre Cadastrar e Pesquisar."""
    main_src = Path("main.py").read_text(encoding="utf-8")
    assert "pages/6_GRD.py" in main_src
    pos_grd = main_src.index("pages/6_GRD.py")
    pos_cadastro = main_src.index("pages/4_CadastroManual.py")
    pos_pesquisa = main_src.index("pages/5_Documento.py")
    assert pos_cadastro < pos_grd < pos_pesquisa
