"""
tests/test_pages/test_importacao_page.py

Checks estruturais da pagina de Importacao.
"""

import ast
from pathlib import Path


def test_importacao_continua_importavel_por_ast():
    path = Path("pages/2_Importacao.py")
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_importacao_importa_preview_service():
    source = Path("pages/2_Importacao.py").read_text(encoding="utf-8")
    assert "gerar_preview_lista" in source
    assert "importacao_preview_service" in source


def test_importacao_lista_tem_botao_analisar():
    source = Path("pages/2_Importacao.py").read_text(encoding="utf-8")
    assert "Analisar importação" in source


def test_importacao_lista_tem_botao_confirmar():
    source = Path("pages/2_Importacao.py").read_text(encoding="utf-8")
    assert "Confirmar importação" in source


def test_importacao_lista_tem_botao_cancelar():
    source = Path("pages/2_Importacao.py").read_text(encoding="utf-8")
    assert "Cancelar prévia" in source


def test_importacao_lista_usa_session_state_para_preview():
    source = Path("pages/2_Importacao.py").read_text(encoding="utf-8")
    assert "imp_lista_preview_" in source


def test_importacao_lista_usa_session_state_para_bytes():
    source = Path("pages/2_Importacao.py").read_text(encoding="utf-8")
    assert "imp_lista_bytes_" in source


def test_importacao_lista_nao_importa_direto_sem_preview():
    """Garante que o botão direto 'Importar Lista de Documentos' foi substituído."""
    source = Path("pages/2_Importacao.py").read_text(encoding="utf-8")
    assert "Importar Lista de Documentos" not in source


def test_importacao_lista_exibe_aviso_preview():
    source = Path("pages/2_Importacao.py").read_text(encoding="utf-8")
    assert "nenhuma alteração foi gravada" in source


def test_importacao_lista_tem_renderizar_preview():
    source = Path("pages/2_Importacao.py").read_text(encoding="utf-8")
    assert "_renderizar_preview_lista" in source


def test_importacao_preview_service_importavel_por_ast():
    path = Path("core/services/importacao_preview_service.py")
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_importacao_preview_service_tem_funcao_publica():
    source = Path("core/services/importacao_preview_service.py").read_text(encoding="utf-8")
    assert "def gerar_preview_lista" in source
    assert "ResultadoPreviewLista" in source
    assert "MudancaStatusPreview" in source


def test_B_confirmar_desabilitado_quando_lifecycle_bloqueante():
    """
    Teste B: o botão de confirmação deve usar disabled=preview.tem_lifecycle_bloqueante.
    Verifica que a UI passa o argumento disabled ao botão confirmar.
    """
    source = Path("pages/2_Importacao.py").read_text(encoding="utf-8")
    assert "disabled=preview.tem_lifecycle_bloqueante" in source, (
        "O botão 'Confirmar importação' deve ser desabilitado quando há issues bloqueantes"
    )


def test_UI_exibe_lifecycle_bloqueantes():
    """UI deve renderizar bloco de erros bloqueantes da engine de ciclo documental."""
    source = Path("pages/2_Importacao.py").read_text(encoding="utf-8")
    assert "lifecycle_bloqueantes" in source
    assert "tem_lifecycle_bloqueante" in source


def test_UI_exibe_linhas_novas_e_atualizadas():
    """UI deve exibir seções de revisões novas e atualizadas."""
    source = Path("pages/2_Importacao.py").read_text(encoding="utf-8")
    assert "linhas_novas" in source
    assert "linhas_atualizadas" in source


def test_UI_mensagem_status_atual():
    """Mensagem de ausência de mudança deve incluir a palavra 'atual'."""
    source = Path("pages/2_Importacao.py").read_text(encoding="utf-8")
    assert "Nenhuma mudança de status atual detectada." in source
