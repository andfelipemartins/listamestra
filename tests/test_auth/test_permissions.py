"""
tests/test_auth/test_permissions.py

Testes de can_perfil — pura, sem Streamlit.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from core.auth.permissions import can_perfil, PERFIS, PERMISSOES


# ---------------------------------------------------------------------------
# Estrutura dos perfis
# ---------------------------------------------------------------------------

class TestEstruturaPerfis:

    def test_todos_os_perfis_existem(self):
        for key in ("admin", "editor", "reader", "visitor"):
            assert key in PERFIS

    def test_perfis_tem_label_e_permissions(self):
        for key, perfil in PERFIS.items():
            assert "label" in perfil
            assert "permissions" in perfil
            assert isinstance(perfil["permissions"], frozenset)

    def test_admin_tem_todas_as_permissoes(self):
        admin_perms = PERFIS["admin"]["permissions"]
        assert admin_perms == PERMISSOES

    def test_visitor_tem_apenas_view_dashboard(self):
        assert PERFIS["visitor"]["permissions"] == frozenset({"view_dashboard"})


# ---------------------------------------------------------------------------
# can_perfil — Administrador
# ---------------------------------------------------------------------------

class TestAdministrador:

    def test_admin_pode_tudo(self):
        for perm in PERMISSOES:
            assert can_perfil(perm, "admin") is True

    def test_admin_permissao_invalida_retorna_false(self):
        assert can_perfil("permissao_inexistente", "admin") is False


# ---------------------------------------------------------------------------
# can_perfil — Controle Documental (editor)
# ---------------------------------------------------------------------------

class TestEditor:

    def test_editor_pode_criar_documento(self):
        assert can_perfil("create_document", "editor") is True

    def test_editor_pode_importar(self):
        assert can_perfil("import_data", "editor") is True

    def test_editor_pode_exportar(self):
        assert can_perfil("export_data", "editor") is True

    def test_editor_nao_pode_gerenciar_contratos(self):
        assert can_perfil("manage_contracts", "editor") is False

    def test_editor_pode_ver_dashboard(self):
        assert can_perfil("view_dashboard", "editor") is True


# ---------------------------------------------------------------------------
# can_perfil — Leitor / Consulta (reader)
# ---------------------------------------------------------------------------

class TestLeitor:

    def test_reader_pode_ver_dashboard(self):
        assert can_perfil("view_dashboard", "reader") is True

    def test_reader_pode_ver_documento(self):
        assert can_perfil("view_document", "reader") is True

    def test_reader_pode_ver_comparacao(self):
        assert can_perfil("view_comparison", "reader") is True

    def test_reader_pode_exportar(self):
        assert can_perfil("export_data", "reader") is True

    def test_reader_nao_pode_criar_documento(self):
        assert can_perfil("create_document", "reader") is False

    def test_reader_nao_pode_importar(self):
        assert can_perfil("import_data", "reader") is False

    def test_reader_nao_pode_gerenciar_contratos(self):
        assert can_perfil("manage_contracts", "reader") is False


# ---------------------------------------------------------------------------
# can_perfil — Visitante
# ---------------------------------------------------------------------------

class TestVisitante:

    def test_visitor_pode_ver_dashboard(self):
        assert can_perfil("view_dashboard", "visitor") is True

    def test_visitor_nao_pode_criar_documento(self):
        assert can_perfil("create_document", "visitor") is False

    def test_visitor_nao_pode_importar(self):
        assert can_perfil("import_data", "visitor") is False

    def test_visitor_nao_pode_exportar(self):
        assert can_perfil("export_data", "visitor") is False

    def test_visitor_nao_pode_ver_comparacao(self):
        assert can_perfil("view_comparison", "visitor") is False


# ---------------------------------------------------------------------------
# can_perfil — perfil desconhecido
# ---------------------------------------------------------------------------

class TestPerfilDesconhecido:

    def test_perfil_inexistente_nega_tudo(self):
        for perm in PERMISSOES:
            assert can_perfil(perm, "fantasma") is False

    def test_string_vazia_nega_tudo(self):
        assert can_perfil("view_dashboard", "") is False
