"""Verificações estruturais da Central de Pendências."""

import ast
from pathlib import Path


_PAGINA = Path("pages/7_Pendencias.py")


def _src() -> str:
    return _PAGINA.read_text(encoding="utf-8")


def test_pendencias_page_importavel_por_ast():
    ast.parse(_src(), filename=str(_PAGINA))


def test_pendencias_page_usa_service_e_cabecalho_padrao():
    source = _src()
    assert "PendenciasService" in source
    assert ".painel(" in source
    assert "resumo_por_categoria(" not in source
    assert "listar_pendencias(" not in source
    assert "opcoes_filtros(" not in source
    assert "require_contrato()" in source
    assert 'require_permission("view_dashboard")' in source
    assert "widget_seletor_perfil()" in source
    assert "sidebar_contexto()" in source


def test_pendencias_page_chama_painel_em_uma_unica_consulta():
    tree = ast.parse(_src(), filename=str(_PAGINA))
    chamadas_service = [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr
        in {"painel", "resumo_por_categoria", "listar_pendencias", "opcoes_filtros"}
    ]
    assert chamadas_service == ["painel"]


def test_pendencias_page_nao_usa_sql_direto():
    source = _src().lower()
    for termo in ("select ", "insert ", "update ", "get_connection", "sqlite3"):
        assert termo not in source, f"SQL/conexão direta na página: {termo!r}"


def test_acoes_de_gestao_exigem_permissao():
    tree = ast.parse(_src(), filename=str(_PAGINA))
    pais = {
        filho: pai
        for pai in ast.walk(tree)
        for filho in ast.iter_child_nodes(pai)
    }

    def verifica_permissao(node):
        pai = pais.get(node)
        while pai is not None:
            if isinstance(pai, ast.If) and isinstance(pai.test, ast.Call):
                teste = pai.test
                if (
                    isinstance(teste.func, ast.Name)
                    and teste.func.id == "can"
                    and teste.args
                    and isinstance(teste.args[0], ast.Constant)
                    and teste.args[0].value == "manage_pendencias"
                ):
                    return True
            pai = pais.get(pai)
        return False

    acoes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"dispensar_pendencia", "reativar_pendencia"}
    ]
    assert acoes
    assert all(verifica_permissao(acao) for acao in acoes)


def test_pendencias_page_tem_filtros_e_acoes():
    source = _src()
    for termo in (
        "Mostrar dispensadas",
        "Trecho",
        "Disciplina",
        "Limpar filtros",
        "pendencias_filtro_tipo",
        "Filtro selecionado",
        "pendências exibidas",
        "Verificações automáticas de consistência do contrato",
        "expanded=bool(_tipo_selecionado) or len(_itens) <= 10",
        "Resolvida",
        "Ignorar",
        "Reativar",
        "Abrir documento",
        'st.session_state["doc_pagina_id"]',
        'st.switch_page("pages/5_Documento.py")',
    ):
        assert termo in source


def test_pendencias_page_registrada_depois_de_pesquisar_documento():
    main_src = Path("main.py").read_text(encoding="utf-8")
    assert 'title="PENDÊNCIAS"' in main_src
    assert 'icon=":material/assignment_late:"' in main_src
    pos_pesquisa = main_src.index('title="PESQUISAR DOCUMENTO"')
    pos_pendencias = main_src.index('title="PENDÊNCIAS"')
    assert pos_pesquisa < pos_pendencias
