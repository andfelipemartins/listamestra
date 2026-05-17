"""
tests/test_pages/test_cadastro_manual_page.py

Checks estruturais da pagina de Cadastro Manual.
"""

import ast
from pathlib import Path


def test_cadastro_manual_continua_importavel_por_ast():
    path = Path("pages/4_CadastroManual.py")
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_componente_codigo_segmentado_continua_importavel_por_ast():
    path = Path("app/components/codigo_segmentado.py")
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
