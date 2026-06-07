"""
tests/test_pages/test_grd_page.py

Checks estruturais da página de GRD (pages/6_GRD.py).
"""

import ast
from pathlib import Path

_PAGINA = Path("pages/6_GRD.py")


def _src() -> str:
    return _PAGINA.read_text(encoding="utf-8")


def test_grd_page_importavel_por_ast():
    ast.parse(_src(), filename=str(_PAGINA))


def test_grd_page_usa_grd_service():
    source = _src()
    assert "GrdService" in source
    assert "criar_grd" in source


def test_grd_page_nao_usa_sql_direto():
    """A página não deve conter SQL — toda persistência via service."""
    source = _src().lower()
    for termo in ("select ", "insert ", "update ", "get_connection", "sqlite3"):
        assert termo not in source, f"SQL/conexão direta na página: {termo!r}"


def test_grd_page_tem_selecao_com_copias():
    """Seleção via data_editor com coluna Incluir e formatos de cópia."""
    source = _src()
    assert "data_editor" in source
    assert "Incluir" in source
    for fmt in ("A0", "A1", "A2", "A3", "A4", "Digital"):
        assert fmt in source


def test_grd_page_tem_status_inicial():
    source = _src()
    assert "Status inicial" in source
    assert "rascunho" in source and "emitida" in source


def test_grd_page_tem_cabecalho_estendido():
    source = _src()
    for campo in ("grd_numero", "grd_data_envio", "grd_destinatario", "grd_obra"):
        assert campo in source


def test_grd_page_botao_criar():
    assert "Criar GRD" in _src()


def test_grd_page_tem_consulta_e_filtros():
    source = _src()
    assert "Consultar GRDs" in source
    assert "listar_grds" in source
    assert "grd_f_numero" in source  # filtro por número
    assert "grd_f_status" in source  # filtro por status


def test_grd_page_tem_downloads_e_status():
    source = _src()
    assert "download_button" in source
    assert "exportar_excel" in source and "exportar_pdf" in source
    assert "alterar_status" in source
    assert "cancelar_grd" in source


def test_grd_page_no_menu_entre_cadastrar_e_pesquisar():
    main_src = Path("main.py").read_text(encoding="utf-8")
    assert "pages/6_GRD.py" in main_src
    pos_grd = main_src.index("pages/6_GRD.py")
    pos_cadastro = main_src.index("pages/4_CadastroManual.py")
    pos_pesquisa = main_src.index("pages/5_Documento.py")
    assert pos_cadastro < pos_grd < pos_pesquisa
