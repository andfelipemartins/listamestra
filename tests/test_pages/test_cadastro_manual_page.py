"""
tests/test_pages/test_cadastro_manual_page.py

Checks estruturais da pagina de Cadastro Manual.
"""

import ast
from pathlib import Path


def test_cadastro_manual_continua_importavel_por_ast():
    path = Path("pages/4_CadastroManual.py")
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_componente_dados_derivados_continua_importavel_por_ast():
    path = Path("app/components/dados_derivados_codigo.py")
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_cadastro_manual_usa_textarea_como_fluxo_principal():
    source = Path("pages/4_CadastroManual.py").read_text(encoding="utf-8")

    assert "st.text_area(" in source
    assert "Códigos dos documentos" in source
    assert "Analisar Códigos" in source


def test_cadastro_manual_nao_exige_fluxo_segmentado_individual():
    source = Path("pages/4_CadastroManual.py").read_text(encoding="utf-8")

    assert "Adicionar documento individual" not in source
    assert "entrada_codigo_segmentado" not in source
    assert "Campos segmentados" not in source
    assert "Colar codigo completo" not in source


# ---------------------------------------------------------------------------
# Testes do preview (Marco 10.7.4)
# ---------------------------------------------------------------------------

def test_cadastro_manual_tem_botao_revisar_antes_de_salvar():
    source = Path("pages/4_CadastroManual.py").read_text(encoding="utf-8")
    assert "Revisar antes de salvar" in source


def test_cadastro_manual_usa_flag_modo_preview():
    source = Path("pages/4_CadastroManual.py").read_text(encoding="utf-8")
    assert "cm_modo_preview" in source


def test_cadastro_manual_tem_botao_confirmar_e_salvar():
    source = Path("pages/4_CadastroManual.py").read_text(encoding="utf-8")
    assert "Confirmar e Salvar" in source


def test_cadastro_manual_tem_botao_voltar_e_editar():
    source = Path("pages/4_CadastroManual.py").read_text(encoding="utf-8")
    assert "Voltar e Editar" in source


def test_cadastro_manual_preview_usa_renderizar_preview():
    source = Path("pages/4_CadastroManual.py").read_text(encoding="utf-8")
    assert "_renderizar_preview" in source


def test_cadastro_manual_preview_redefine_modo_ao_analisar():
    """Garante que analisar novos codigos sempre reseta o modo para formulario."""
    source = Path("pages/4_CadastroManual.py").read_text(encoding="utf-8")
    # A atribuicao False deve estar no bloco do botao Analisar
    assert 'st.session_state["cm_modo_preview"]    = False' in source or \
           "st.session_state[\"cm_modo_preview\"] = False" in source


def test_cadastro_manual_nao_salva_sem_preview():
    """Garante que o fluxo obriga preview antes de salvar (sem botao direto de save)."""
    source = Path("pages/4_CadastroManual.py").read_text(encoding="utf-8")
    # O botão de entrada no preview existe
    assert "Revisar antes de salvar" in source
    # O salvamento real so ocorre dentro de _renderizar_preview (apos confirmacao)
    assert "Confirmar e Salvar" in source
    # Nao ha botao de salvar direto sem preview
    assert "Salvar documento" not in source
    assert "Salvar {n} documento" not in source


# ---------------------------------------------------------------------------
# Testes de UX visual dos cards (Block 002) — readonly vs editável
# ---------------------------------------------------------------------------

def test_dados_derivados_marcados_como_somente_leitura():
    """O componente de dados derivados deve sinalizar explicitamente readonly."""
    source = Path("app/components/dados_derivados_codigo.py").read_text(encoding="utf-8")
    assert "somente leitura" in source


def test_cadastro_manual_marca_secoes_editaveis():
    """A página deve identificar claramente as seções de campos editáveis."""
    source = Path("pages/4_CadastroManual.py").read_text(encoding="utf-8")
    assert "campos editáveis" in source or "campos editaveis" in source


def test_cadastro_manual_sinaliza_campos_obrigatorios():
    """A página deve trazer legenda explícita sobre campos obrigatórios."""
    source = Path("pages/4_CadastroManual.py").read_text(encoding="utf-8")
    assert "são obrigatórios" in source


def test_preview_usa_linguagem_readonly_editavel_consistente():
    """O modo preview deve reaproveitar o componente readonly e marcar editáveis."""
    source = Path("pages/4_CadastroManual.py").read_text(encoding="utf-8")
    assert "exibir_dados_derivados_codigo" in source
    assert "Dados informados (editáveis)" in source
