"""
tests/test_parsers/test_arquivo_parser.py

Testes do parser de nome de arquivo (core/parsers/arquivo_parser.py).

Execute com:
    pytest tests/ -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from core.parsers.arquivo_parser import parsear_arquivo, ArquivoParseado, ErroParsearArquivo


class TestFormatoNovo:
    """Arquivos com revisão E versão: CODIGO-REVISAO-VERSAO.ext"""

    def test_revisao_numerica_versao_1(self):
        r = parsear_arquivo("DE-15.25.00.00-6A1-1001-1-1.pdf")
        assert isinstance(r, ArquivoParseado)
        assert r.codigo == "DE-15.25.00.00-6A1-1001"
        assert r.label_revisao == "1"
        assert r.versao == 1
        assert r.extensao == "pdf"

    def test_revisao_numerica_versao_2(self):
        r = parsear_arquivo("DE-15.25.00.00-6A1-1001-1-2.pdf")
        assert isinstance(r, ArquivoParseado)
        assert r.label_revisao == "1"
        assert r.versao == 2

    def test_revisao_0_aprovado_com_versao(self):
        r = parsear_arquivo("DE-15.19.02.00-6F2-1001-0-1.dwg")
        assert isinstance(r, ArquivoParseado)
        assert r.codigo == "DE-15.19.02.00-6F2-1001"
        assert r.label_revisao == "0"
        assert r.versao == 1
        assert r.extensao == "dwg"

    def test_revisao_letra_sub_com_versao(self):
        r = parsear_arquivo("DE-15.25.00.00-6A1-1001-A1-1.pdf")
        assert isinstance(r, ArquivoParseado)
        assert r.label_revisao == "A1"
        assert r.versao == 1

    def test_revisao_letra_simples_com_versao(self):
        r = parsear_arquivo("DE-15.25.00.00-6A1-1001-A-1.pdf")
        assert isinstance(r, ArquivoParseado)
        assert r.label_revisao == "A"
        assert r.versao == 1

    def test_revisao_letra_b_com_versao(self):
        r = parsear_arquivo("DE-15.25.00.00-6A1-1001-B2-3.pdf")
        assert isinstance(r, ArquivoParseado)
        assert r.label_revisao == "B2"
        assert r.versao == 3

    def test_extensao_em_minusculas(self):
        r = parsear_arquivo("DE-15.25.00.00-6A1-1001-1-1.PDF")
        assert isinstance(r, ArquivoParseado)
        assert r.extensao == "pdf"

    def test_codigo_em_maiusculas(self):
        r = parsear_arquivo("de-15.25.00.00-6a1-1001-1-1.pdf")
        assert isinstance(r, ArquivoParseado)
        assert r.codigo == "DE-15.25.00.00-6A1-1001"

    def test_nome_arquivo_preservado(self):
        nome = "DE-15.25.00.00-6A1-1001-1-1.pdf"
        r = parsear_arquivo(nome)
        assert r.nome_arquivo == nome


class TestFormatoAntigo:
    """Arquivos sem versão: CODIGO-REVISAO.ext (em transição)"""

    def test_formato_antigo_sem_versao(self):
        r = parsear_arquivo("DE-15.25.00.00-6F2-1001-0.dwg")
        assert isinstance(r, ArquivoParseado)
        assert r.codigo == "DE-15.25.00.00-6F2-1001"
        assert r.label_revisao == "0"
        assert r.versao is None
        assert r.extensao == "dwg"

    def test_formato_antigo_revisao_numerica(self):
        r = parsear_arquivo("DE-15.25.00.00-6F2-1002-1.pdf")
        assert isinstance(r, ArquivoParseado)
        assert r.label_revisao == "1"
        assert r.versao is None

    def test_formato_antigo_revisao_letra(self):
        r = parsear_arquivo("DE-15.25.00.00-6A1-1001-A.pdf")
        assert isinstance(r, ArquivoParseado)
        assert r.label_revisao == "A"
        assert r.versao is None


class TestComCaminho:
    """Linhas com caminho completo (dir /b /s)"""

    def test_caminho_windows(self):
        r = parsear_arquivo(
            r"C:\SharePoint\EXECUTIVO\25-00-00\DE-15.25.00.00-6A1-1001-1-1.pdf"
        )
        assert isinstance(r, ArquivoParseado)
        assert r.nome_arquivo == "DE-15.25.00.00-6A1-1001-1-1.pdf"
        assert r.codigo == "DE-15.25.00.00-6A1-1001"

    def test_caminho_com_espacos(self):
        r = parsear_arquivo(
            r"C:\Pasta Com Espacos\DE-15.25.00.00-6A1-1001-1-1.pdf"
        )
        assert isinstance(r, ArquivoParseado)
        assert r.nome_arquivo == "DE-15.25.00.00-6A1-1001-1-1.pdf"

    def test_caminho_unix(self):
        r = parsear_arquivo(
            "/mnt/sharepoint/EXECUTIVO/DE-15.25.00.00-6A1-1001-1-1.pdf"
        )
        assert isinstance(r, ArquivoParseado)
        assert r.nome_arquivo == "DE-15.25.00.00-6A1-1001-1-1.pdf"


class TestErros:
    """Nomes que devem retornar ErroParsearArquivo"""

    def test_nome_sem_extensao(self):
        r = parsear_arquivo("DE-15.25.00.00-6A1-1001-1-1")
        assert isinstance(r, ErroParsearArquivo)

    def test_nome_sem_revisao(self):
        r = parsear_arquivo("DE-15.25.00.00-6A1-1001.pdf")
        assert isinstance(r, ErroParsearArquivo)

    def test_nome_totalmente_diferente(self):
        r = parsear_arquivo("planilha_controle.xlsx")
        assert isinstance(r, ErroParsearArquivo)

    def test_linha_vazia(self):
        r = parsear_arquivo("")
        assert isinstance(r, ErroParsearArquivo)

    def test_linha_so_espacos(self):
        r = parsear_arquivo("   ")
        assert isinstance(r, ErroParsearArquivo)

    def test_linha_so_pasta(self):
        r = parsear_arquivo(r"C:\pasta\subpasta\\")
        assert isinstance(r, ErroParsearArquivo)

    def test_codigo_linha_errada(self):
        # linha 16 em vez de 15
        r = parsear_arquivo("DE-16.25.00.00-6A1-1001-1-1.pdf")
        assert isinstance(r, ErroParsearArquivo)


class TestParametrizado:
    @pytest.mark.parametrize("nome, codigo_esperado, revisao, versao, ext", [
        ("DE-15.25.00.00-6A1-1001-1-1.pdf",  "DE-15.25.00.00-6A1-1001", "1",  1,    "pdf"),
        ("DE-15.25.00.00-6A1-1001-1-2.pdf",  "DE-15.25.00.00-6A1-1001", "1",  2,    "pdf"),
        ("DE-15.25.00.00-6A1-1001-2-1.pdf",  "DE-15.25.00.00-6A1-1001", "2",  1,    "pdf"),
        ("DE-15.25.00.00-6A1-1001-0-1.pdf",  "DE-15.25.00.00-6A1-1001", "0",  1,    "pdf"),
        ("DE-15.25.00.00-6A1-1001-0-3.pdf",  "DE-15.25.00.00-6A1-1001", "0",  3,    "pdf"),
        ("DE-15.25.00.00-6A1-1001-A1-1.pdf", "DE-15.25.00.00-6A1-1001", "A1", 1,    "pdf"),
        ("DE-15.25.00.00-6A1-1001-A-1.pdf",  "DE-15.25.00.00-6A1-1001", "A",  1,    "pdf"),
        ("DE-15.25.00.00-6F2-1001-0.dwg",    "DE-15.25.00.00-6F2-1001", "0",  None, "dwg"),
        ("DE-15.19.02.00-6F2-1001-0-1.dwg",  "DE-15.19.02.00-6F2-1001", "0",  1,    "dwg"),
        ("MC-15.25.00.00-6A1-1001-1-1.pdf",  "MC-15.25.00.00-6A1-1001", "1",  1,    "pdf"),
    ])
    def test_matriz_completa(self, nome, codigo_esperado, revisao, versao, ext):
        r = parsear_arquivo(nome)
        assert isinstance(r, ArquivoParseado)
        assert r.codigo == codigo_esperado
        assert r.label_revisao == revisao
        assert r.versao == versao
        assert r.extensao == ext
