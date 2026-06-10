"""
tests/test_pages/test_documento_page.py

Checks estruturais da pagina de Documento (pages/5_Documento.py).

Garante que a linha do tempo nao usa mais classificar_status() para o status
de cada revisao e que o resultado de linha vem da engine (via resultado_linha).
"""

import ast
from pathlib import Path

_PAGINA = Path("pages/5_Documento.py")


def test_documento_continua_importavel_por_ast():
    ast.parse(_PAGINA.read_text(encoding="utf-8"), filename=str(_PAGINA))


def test_linha_do_tempo_nao_usa_classificar_status():
    """A linha do tempo deve usar resultado_linha (engine), nao classificar_status()."""
    source = _PAGINA.read_text(encoding="utf-8")
    assert "classificar_status(" not in source, (
        "pages/5_Documento.py não deve mais chamar classificar_status() — "
        "o resultado da revisão vem da engine via resultado_linha."
    )


def test_linha_do_tempo_usa_resultado_linha():
    source = _PAGINA.read_text(encoding="utf-8")
    assert "resultado_linha" in source, (
        "A linha do tempo deve exibir o resultado_linha calculado pela engine."
    )


def test_nao_importa_classificar_status():
    """classificar_status nao deve nem ser importado pela pagina."""
    source = _PAGINA.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(_PAGINA))
    importados: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                importados.add(alias.name)
    assert "classificar_status" not in importados


# ---------------------------------------------------------------------------
# Integração de GRDs no detalhe do documento (block-002 v2)
# ---------------------------------------------------------------------------

def test_documento_integra_grds_via_service():
    """GRDs no detalhe vêm do GrdService (snapshot), não de SQL direto."""
    source = _PAGINA.read_text(encoding="utf-8")
    assert "GrdService" in source
    assert "listar_grds_por_revisao" in source
    # não consulta mais a tabela legada grds via SQL
    assert "FROM grds" not in source


def test_documento_grd_mostra_status_e_recebimento():
    source = _PAGINA.read_text(encoding="utf-8")
    assert "GRDs vinculadas" in source
    assert "recebido_por" in source
