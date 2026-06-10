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


def test_grd_page_tem_downloads():
    source = _src()
    assert "download_button" in source
    assert "exportar_excel" in source and "exportar_pdf" in source


def test_grd_page_acoes_controladas_por_status():
    """Sem selectbox de status livre; ações nomeadas via service."""
    source = _src()
    assert 'st.selectbox(\n                        "Alterar status"' not in source
    assert "Alterar status" not in source  # selectbox de status livre removido
    for acao in ("emitir_grd", "marcar_enviada", "marcar_recebida", "anular_grd", "excluir_rascunho"):
        assert acao in source, f"ação ausente: {acao}"


def test_grd_page_prepara_token():
    source = _src()
    assert "gerar_token_recebimento" in source
    # deixa claro que a página pública ainda não existe
    assert "ainda não está implementada" in source.lower() or "adr 0004" in source.lower()


def test_grd_page_token_feedback_sobrevive_rerun():
    """Feedback do token usa session_state (sobrevive ao rerun) e é limpo depois."""
    source = _src()
    assert "grd_token_feedback" in source
    assert "Token de recebimento gerado" in source
    # o flag é definido antes do rerun e removido após exibir
    assert 'del st.session_state["grd_token_feedback"]' in source


def test_grd_page_token_persistente_readonly():
    """Token exibido em campo somente-leitura, com observação de página pública."""
    source = _src()
    assert "disabled=True" in source
    assert "página pública ainda não está implementada" in source


def test_grd_page_token_nao_chamado_de_link():
    """Vocabulário: 'Token de recebimento', não 'link de recebimento'."""
    source = _src().lower()
    assert "link de recebimento" not in source
    assert "token de recebimento" in source


def test_grd_page_avisa_congelamento():
    source = _src()
    assert "imutável" in source.lower() or "congelad" in source.lower()


def test_grd_page_no_menu_entre_cadastrar_e_pesquisar():
    main_src = Path("main.py").read_text(encoding="utf-8")
    assert "pages/6_GRD.py" in main_src
    pos_grd = main_src.index("pages/6_GRD.py")
    pos_cadastro = main_src.index("pages/4_CadastroManual.py")
    pos_pesquisa = main_src.index("pages/5_Documento.py")
    assert pos_cadastro < pos_grd < pos_pesquisa
