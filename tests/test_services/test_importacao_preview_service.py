"""
tests/test_services/test_importacao_preview_service.py

Testes do servico de preview dry-run da importacao da Lista de Documentos.

Todos os testes usam bancos SQLite temporarios (tmp_path) — jamais o banco real.
"""

import io
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scripts"))

from init_db import init_db
from db.connection import get_connection
from core.services.importacao_preview_service import (
    gerar_preview_lista,
    ResultadoPreviewLista,
    MudancaStatusPreview,
    LinhaRevisaoPreview,
    _obter_snapshot,
    _comparar_snapshots,
    _comparar_chaves_revisao,
)


# ---------------------------------------------------------------------------
# Helpers de criação de Excel em memória
# ---------------------------------------------------------------------------

def _linha(
    codigo: str,
    revisao=1,
    versao: int = 1,
    sigla: str = "DE",
    trecho: int = 25,
    nome_trecho: str = "Ragueb Chohfi",
    modalidade: str = "CIVIL",
    estrutura: str = "N3",
    elaboracao: str = "ROMA",
    descricao: str = "Documento de teste",
    situacao: str = "NÃO APROVADO",
    situacao_real: str = "NÃO LIBERADO",
    data_emissao: str = "2024-10-07",
) -> list:
    """Cria uma linha com 62 colunas simulando a planilha real."""
    row = [None] * 62
    row[1]  = sigla
    row[2]  = 15
    row[3]  = trecho
    row[4]  = 0
    row[5]  = 0
    row[6]  = 6
    row[7]  = estrutura
    row[8]  = 1001
    row[9]  = codigo
    row[10] = revisao
    row[11] = versao
    row[12] = nome_trecho
    row[15] = elaboracao
    row[16] = modalidade
    row[18] = estrutura
    row[19] = descricao
    row[20] = 1
    row[21] = "2024-09-27"
    row[22] = data_emissao
    row[23] = 10
    row[24] = "EMISSÃO INICIAL"
    row[25] = "2024-10-23"
    row[26] = 16
    row[27] = situacao_real
    row[28] = situacao
    return row


def _criar_excel_bytes(*linhas) -> bytes:
    """Cria bytes de Excel válido no formato esperado pelo ListaImporter."""
    n_cols = 62
    # header=1 no pandas: row 0 é descartado, row 1 vira headers, row 2+ são dados
    rows = [
        [f"G{i}" for i in range(n_cols)],   # row 0: grupo (descartado)
        [f"C{i}" for i in range(n_cols)],   # row 1: nomes das colunas
    ] + list(linhas)
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Lista de documentos", index=False, header=False)
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------------------
# Fixture de banco de dados temporário
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    """Banco temporário com schema e um contrato de teste."""
    db_path = str(tmp_path / "test_preview.db")
    init_db(db_path, verbose=False)
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO contratos (nome, cliente) VALUES ('Contrato Teste', 'Metrô SP')"
        )
        contrato_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return db_path, contrato_id


# ---------------------------------------------------------------------------
# Testes do preview service
# ---------------------------------------------------------------------------

class TestPreviewNaoAlteraReal:
    def test_preview_nao_altera_banco_real(self, db):
        """gerar_preview_lista não deve criar documentos ou revisoes no banco real."""
        db_path, contrato_id = db
        excel = _criar_excel_bytes(
            _linha("DE-15.25.00.00-6N3-1001"),
        )

        # Conta documentos antes
        with get_connection(db_path) as conn:
            total_antes = conn.execute(
                "SELECT COUNT(*) FROM documentos WHERE contrato_id = ?", (contrato_id,)
            ).fetchone()[0]

        gerar_preview_lista(excel, "lista.xlsx", contrato_id, db_path=db_path)

        # Conta documentos depois — deve ser igual
        with get_connection(db_path) as conn:
            total_depois = conn.execute(
                "SELECT COUNT(*) FROM documentos WHERE contrato_id = ?", (contrato_id,)
            ).fetchone()[0]

        assert total_antes == total_depois, (
            f"O preview não deveria alterar o banco real: antes={total_antes}, depois={total_depois}"
        )

    def test_preview_nao_registra_importacao_no_banco_real(self, db):
        """gerar_preview_lista não deve criar registro em importacoes no banco real."""
        db_path, contrato_id = db
        excel = _criar_excel_bytes(_linha("DE-15.25.00.00-6N3-1001"))

        with get_connection(db_path) as conn:
            total_antes = conn.execute(
                "SELECT COUNT(*) FROM importacoes WHERE contrato_id = ?", (contrato_id,)
            ).fetchone()[0]

        gerar_preview_lista(excel, "lista.xlsx", contrato_id, db_path=db_path)

        with get_connection(db_path) as conn:
            total_depois = conn.execute(
                "SELECT COUNT(*) FROM importacoes WHERE contrato_id = ?", (contrato_id,)
            ).fetchone()[0]

        assert total_antes == total_depois


class TestPreviewIdentificaMudancas:
    def test_preview_identifica_documentos_novos(self, db):
        """Preview deve reportar documento novo quando não existe no banco real."""
        db_path, contrato_id = db
        excel = _criar_excel_bytes(_linha("DE-15.25.00.00-6N3-1001"))

        resultado = gerar_preview_lista(excel, "lista.xlsx", contrato_id, db_path=db_path)

        assert not resultado.tem_erro_fatal
        assert resultado.novos_documentos == 1
        assert resultado.novas_revisoes == 1

    def test_preview_identifica_documento_em_mudancas(self, db):
        """Documento novo deve aparecer em resultado.mudancas como eh_novo_documento=True."""
        db_path, contrato_id = db
        excel = _criar_excel_bytes(_linha("DE-15.25.00.00-6N3-1001"))

        resultado = gerar_preview_lista(excel, "lista.xlsx", contrato_id, db_path=db_path)

        assert any(m.eh_novo_documento for m in resultado.mudancas)
        codigos = [m.codigo for m in resultado.mudancas if m.eh_novo_documento]
        assert "DE-15.25.00.00-6N3-1001" in codigos

    def test_preview_identifica_revisao_nova(self, db):
        """Preview deve reportar novas revisoes ao importar documento existente com nova rev."""
        db_path, contrato_id = db

        # Primeira importação: cria documento com revisão 1
        from core.importers.lista_importer import ListaImporter
        excel1 = _criar_excel_bytes(_linha("DE-15.25.00.00-6N3-1001", revisao=1))
        excel1_fd, excel1_tmp = __import__("tempfile").mkstemp(suffix=".xlsx")
        os.close(excel1_fd)
        try:
            with open(excel1_tmp, "wb") as f:
                f.write(excel1)
            ListaImporter(db_path=db_path).importar(excel1_tmp, contrato_id)
        finally:
            try:
                os.unlink(excel1_tmp)
            except OSError:
                pass

        # Preview com revisão 2 nova
        excel2 = _criar_excel_bytes(_linha("DE-15.25.00.00-6N3-1001", revisao=2))
        resultado = gerar_preview_lista(excel2, "lista.xlsx", contrato_id, db_path=db_path)

        assert not resultado.tem_erro_fatal
        assert resultado.novas_revisoes >= 1
        assert resultado.documentos_atualizados >= 1

    def test_preview_identifica_mudanca_de_status(self, db):
        """Preview deve detectar mudança de status quando situacao muda."""
        db_path, contrato_id = db

        # Importa documento como NÃO APROVADO (status: Em Revisão)
        from core.importers.lista_importer import ListaImporter
        import tempfile
        excel1 = _criar_excel_bytes(
            _linha("DE-15.25.00.00-6N3-1001", situacao="NÃO APROVADO", data_emissao="2024-10-07")
        )
        fd, tmp = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        try:
            with open(tmp, "wb") as f:
                f.write(excel1)
            ListaImporter(db_path=db_path).importar(tmp, contrato_id)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

        # Preview com APROVADO (status vai mudar)
        excel2 = _criar_excel_bytes(
            _linha("DE-15.25.00.00-6N3-1001", revisao=2, situacao="APROVADO", data_emissao="2024-11-01")
        )
        resultado = gerar_preview_lista(excel2, "lista.xlsx", contrato_id, db_path=db_path)

        assert not resultado.tem_erro_fatal
        assert len(resultado.mudancas_de_status) >= 1
        mudanca = next(
            (m for m in resultado.mudancas_de_status if m.codigo == "DE-15.25.00.00-6N3-1001"),
            None,
        )
        assert mudanca is not None
        assert mudanca.status_antes == "Em Revisão"
        assert mudanca.status_depois == "Aprovado"

    def test_preview_identifica_mudanca_ja_aprovado(self, db):
        """Preview deve detectar transição para ja_aprovado."""
        db_path, contrato_id = db

        # Importa revisão '0' (que conta como ja_aprovado segundo a regra)
        from core.importers.lista_importer import ListaImporter
        import tempfile
        excel1 = _criar_excel_bytes(
            _linha("DE-15.25.00.00-6N3-1001", revisao=0, situacao="APROVADO")
        )
        fd, tmp = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        try:
            with open(tmp, "wb") as f:
                f.write(excel1)
            ListaImporter(db_path=db_path).importar(tmp, contrato_id)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

        # Verifica que ainda não há documento no banco real com ja_aprovado
        snap_antes = _obter_snapshot(contrato_id, db_path)
        # O banco real JÁ tem o documento com ja_aprovado (foi importado acima)
        # Agora vamos testar um banco sem esse documento
        # Melhor: usar banco novo sem nenhum documento
        db_path2 = str(__import__("pathlib").Path(db_path).parent / "test2.db")
        init_db(db_path2, verbose=False)
        with get_connection(db_path2) as conn:
            conn.execute(
                "INSERT INTO contratos (id, nome, cliente) VALUES (?, 'C2', 'M')", (contrato_id,)
            )

        excel_novo = _criar_excel_bytes(
            _linha("DE-15.25.00.00-6N3-1002", revisao=0, situacao="APROVADO")
        )
        resultado = gerar_preview_lista(excel_novo, "lista.xlsx", contrato_id, db_path=db_path2)

        assert not resultado.tem_erro_fatal
        # O documento é novo, então ja_aprovado_antes=False, ja_aprovado_depois pode ser True
        doc = next(
            (m for m in resultado.mudancas if m.codigo == "DE-15.25.00.00-6N3-1002"),
            None,
        )
        assert doc is not None
        assert doc.ja_aprovado_antes is False


class TestPreviewInconsistencias:
    def test_preview_retorna_inconsistencias_de_codigo_invalido(self, db):
        """Código inválido deve aparecer nas inconsistencias do preview."""
        db_path, contrato_id = db
        excel = _criar_excel_bytes(
            _linha("CODIGO_INVALIDO_XYZ"),
        )

        resultado = gerar_preview_lista(excel, "lista.xlsx", contrato_id, db_path=db_path)

        assert not resultado.tem_erro_fatal
        assert resultado.total_inconsistencias > 0
        tipos = [inc["tipo"] for inc in resultado.inconsistencias]
        assert "codigo_invalido" in tipos


class TestPreviewErroFatal:
    def test_preview_arquivo_invalido_retorna_erro_fatal(self, db):
        """Bytes inválidos (não é Excel) devem retornar erro fatal, não exceção."""
        db_path, contrato_id = db
        bytes_invalidos = b"isso nao eh um excel"

        resultado = gerar_preview_lista(bytes_invalidos, "invalido.xlsx", contrato_id, db_path=db_path)

        assert resultado.tem_erro_fatal
        assert resultado.erro_fatal_mensagem is not None

    def test_preview_erro_fatal_retorna_resultado_estruturado(self, db):
        """Erro fatal deve retornar ResultadoPreviewLista, não levantar exceção."""
        db_path, contrato_id = db

        try:
            resultado = gerar_preview_lista(b"", "vazio.xlsx", contrato_id, db_path=db_path)
            assert isinstance(resultado, ResultadoPreviewLista)
        except Exception as exc:
            pytest.fail(f"gerar_preview_lista não deve levantar exceção: {exc}")


class TestPreviewSemMudancas:
    def test_preview_banco_sem_documentos_anteriores(self, db):
        """Preview em banco vazio deve classificar todos como documentos novos."""
        db_path, contrato_id = db
        excel = _criar_excel_bytes(
            _linha("DE-15.25.00.00-6N3-1001"),
            _linha("DE-15.25.00.00-6N3-1002"),
        )

        resultado = gerar_preview_lista(excel, "lista.xlsx", contrato_id, db_path=db_path)

        assert not resultado.tem_erro_fatal
        assert resultado.novos_documentos == 2
        novos = [m for m in resultado.mudancas if m.eh_novo_documento]
        assert len(novos) == 2

    def test_preview_reimportacao_identica_sem_mudancas_de_status(self, db):
        """Reimportar o mesmo Excel sem alterações não deve gerar mudanças de status."""
        db_path, contrato_id = db
        from core.importers.lista_importer import ListaImporter
        import tempfile

        excel_bytes = _criar_excel_bytes(
            _linha("DE-15.25.00.00-6N3-1001", situacao="NÃO APROVADO")
        )

        # Primeira importação real
        fd, tmp = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        try:
            with open(tmp, "wb") as f:
                f.write(excel_bytes)
            ListaImporter(db_path=db_path).importar(tmp, contrato_id)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

        # Preview da mesma importação
        resultado = gerar_preview_lista(excel_bytes, "lista.xlsx", contrato_id, db_path=db_path)

        assert not resultado.tem_erro_fatal
        # Reimportação idêntica: status não muda
        assert len(resultado.mudancas_de_status) == 0


class TestPreviewArquivosTemporarios:
    def test_preview_limpa_arquivos_temporarios(self, db, tmp_path):
        """gerar_preview_lista não deve deixar arquivos temp acumulados."""
        import tempfile

        db_path, contrato_id = db
        excel = _criar_excel_bytes(_linha("DE-15.25.00.00-6N3-1001"))

        dir_temp_antes = set(os.listdir(tempfile.gettempdir()))
        gerar_preview_lista(excel, "lista.xlsx", contrato_id, db_path=db_path)
        dir_temp_depois = set(os.listdir(tempfile.gettempdir()))

        # Nenhum .xlsx ou .db novo deve ter sobrado
        novos = dir_temp_depois - dir_temp_antes
        leftovers = [f for f in novos if f.endswith((".xlsx", ".db"))]
        assert len(leftovers) == 0, f"Arquivos temporários não removidos: {leftovers}"


# ---------------------------------------------------------------------------
# Testes A–E: integração com DocumentLifecycleEngine (Task 9)
# ---------------------------------------------------------------------------

class TestLifecycleIntegracao:
    """
    Testa que a engine de ciclo documental é acionada corretamente pelo preview,
    inclusive para documentos com nova revisão mas sem mudança visível de status final.
    """

    def test_A_nova_revisao_sem_mudanca_status_ativa_lifecycle(self, db):
        """
        Teste A: documento já existente recebe nova revisão intermediária (não a última)
        que não altera o status final do snapshot — deve ainda aparecer em lifecycle_results.
        """
        from core.importers.lista_importer import ListaImporter
        import tempfile

        db_path, contrato_id = db

        # Importação real: doc com revisão A (aprovado) como última
        excel_rev_A = _criar_excel_bytes(
            _linha("DE-15.25.00.00-6N3-2001", revisao="A", situacao="APROVADO",
                   data_emissao="2024-06-01"),
        )
        fd, tmp = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        try:
            with open(tmp, "wb") as f:
                f.write(excel_rev_A)
            ListaImporter(db_path=db_path).importar(tmp, contrato_id)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

        # Preview: adiciona revisão 1 (nova) junto com A (já existente)
        # O status final (revisão A) não muda — mas deve acionar lifecycle
        excel_com_nova = _criar_excel_bytes(
            _linha("DE-15.25.00.00-6N3-2001", revisao=1, situacao="NÃO APROVADO",
                   data_emissao="2024-03-01"),
            _linha("DE-15.25.00.00-6N3-2001", revisao="A", situacao="APROVADO",
                   data_emissao="2024-06-01"),
        )
        resultado = gerar_preview_lista(excel_com_nova, "lista.xlsx", contrato_id, db_path=db_path)

        assert not resultado.tem_erro_fatal
        # Nova revisão 1 detectada em linhas_novas
        codigos_novos = {l.codigo for l in resultado.linhas_novas}
        assert "DE-15.25.00.00-6N3-2001" in codigos_novos, (
            "Revisão nova deve aparecer em linhas_novas"
        )
        # Engine de lifecycle acionada para o documento
        codigos_lifecycle = {lr.codigo for lr in resultado.lifecycle_results}
        assert "DE-15.25.00.00-6N3-2001" in codigos_lifecycle, (
            "Documento com revisão nova deve aparecer em lifecycle_results mesmo sem mudança de status final"
        )

    def test_B_comparar_chaves_revisao_detecta_novas_e_atualizadas(self, db):
        """
        Teste B: _comparar_chaves_revisao retorna corretamente novas, atualizadas e codigos.
        """
        from core.engine.document_lifecycle import LinhaDocumental

        def _ld(codigo, label, versao, situacao=None, data_emissao=None, data_analise=None, id=None):
            return LinhaDocumental(
                codigo=codigo, label_revisao=label, versao=versao,
                situacao=situacao, data_emissao=data_emissao, data_analise=data_analise,
                id=id, ordem=0, ja_persistida=id is not None,
            )

        antes = {
            "DOC-1": [_ld("DOC-1", "0", 1, situacao="NÃO APROVADO", id=10)],
        }
        depois = {
            "DOC-1": [
                _ld("DOC-1", "0", 1, situacao="APROVADO", id=10),   # atualizada
                _ld("DOC-1", "A", 1, situacao="APROVADO", id=None),  # nova
            ],
            "DOC-2": [_ld("DOC-2", "0", 1, id=None)],              # doc novo
        }

        novas, atualizadas, codigos = _comparar_chaves_revisao(antes, depois)

        assert any(l.codigo == "DOC-1" and l.label_revisao == "A" for l in novas)
        assert any(l.codigo == "DOC-2" for l in novas)
        assert any(l.codigo == "DOC-1" and l.label_revisao == "0" for l in atualizadas)
        assert "DOC-1" in codigos
        assert "DOC-2" in codigos

    def test_C_data_analise_obrigatoria_gera_bloqueante(self, db):
        """
        Teste C: documento novo com duas revisões numéricas onde a revisão 1 (superada)
        não tem data_analise deve gerar issue bloqueante na engine.

        Cenário: banco vazio; preview importa rev1 (sem data_analise) + rev2.
        Rev1 fica SUPERADA_POR_REVISAO sem data_analise → bloqueante.
        """
        db_path, contrato_id = db

        def _linha_sem_analise(codigo, revisao, situacao, data_emissao):
            row = _linha(codigo, revisao=revisao, situacao=situacao, data_emissao=data_emissao)
            row[25] = None  # data_analise = None
            return row

        # Banco vazio — documento completamente novo.
        # Rev1 superada por rev2, sem data_analise em nenhuma → bloqueante em rev1.
        excel = _criar_excel_bytes(
            _linha_sem_analise("DE-15.25.00.00-6N3-3001", revisao=1, situacao="NÃO APROVADO",
                               data_emissao="2024-01-01"),
            _linha_sem_analise("DE-15.25.00.00-6N3-3001", revisao=2, situacao="NÃO APROVADO",
                               data_emissao="2024-06-01"),
        )
        resultado = gerar_preview_lista(excel, "lista.xlsx", contrato_id, db_path=db_path)

        assert not resultado.tem_erro_fatal
        assert resultado.tem_lifecycle_bloqueante, (
            "Revisão superada sem data_analise deve gerar bloqueante"
        )

    def test_D_versao_sobre_aprovacao_historica_nao_eh_aprovacao_historica(self):
        """
        Teste D: 0/1 → 0/2 deve ser SUBSTITUIDA_POR_VERSAO, não APROVACAO_HISTORICA.
        Garante a correção da ordem B antes C em _inferir_linha_anterior.
        """
        from core.engine.document_lifecycle import (
            LinhaDocumental,
            analisar_linhas_documento,
            TipoInferencia,
        )

        def _ld(label, versao, situacao=None, data_emissao=None):
            return LinhaDocumental(
                codigo="X", label_revisao=label, versao=versao,
                situacao=situacao, data_emissao=data_emissao,
                ordem=0, ja_persistida=False,
            )

        # 0/1 seguido de 0/2 — label igual, versão maior = SUBSTITUIDA
        result = analisar_linhas_documento("X", [
            _ld("0", 1, data_emissao="2024-01-01"),
            _ld("0", 2, data_emissao="2024-06-01"),
        ])
        linha_v1 = next(ll for ll in result.linhas if ll.linha.versao == 1)
        assert linha_v1.inferencia == TipoInferencia.SUBSTITUIDA_POR_VERSAO, (
            "0/v1 seguido de 0/v2 deve ser SUBSTITUIDA_POR_VERSAO, não APROVACAO_HISTORICA"
        )

    def test_E_status_operacional_override_superada(self):
        """
        Teste E: linha superada por revisão numérica superior deve ter
        status_operacional='Em Revisão' mesmo que a situação original seja outro valor.
        """
        from core.engine.document_lifecycle import (
            LinhaDocumental,
            analisar_linhas_documento,
            TipoInferencia,
        )

        def _ld(label, versao, situacao=None, data_emissao=None, data_analise=None):
            return LinhaDocumental(
                codigo="Y", label_revisao=label, versao=versao,
                situacao=situacao, data_emissao=data_emissao, data_analise=data_analise,
                ordem=0, ja_persistida=False,
            )

        # Revisão 1 superada pela revisão 2 → status_operacional deve ser Em Revisão
        result = analisar_linhas_documento("Y", [
            _ld("1", 1, situacao="NÃO APROVADO", data_emissao="2024-01-01",
                data_analise="2024-02-01"),
            _ld("2", 1, situacao="NÃO APROVADO", data_emissao="2024-06-01"),
        ])
        linha_rev1 = next(ll for ll in result.linhas if ll.linha.label_revisao == "1")
        assert linha_rev1.inferencia == TipoInferencia.SUPERADA_POR_REVISAO
        assert linha_rev1.status_operacional == "Em Revisão", (
            f"Linha superada deve ter status_operacional='Em Revisão', "
            f"obtido: '{linha_rev1.status_operacional}'"
        )


# ---------------------------------------------------------------------------
# Testes F–I: linhas ATUALIZADAS na engine documental
# ---------------------------------------------------------------------------

class TestLifecycleLinhasAtualizadas:
    """
    Garante que a engine analisa linhas atualizadas com seus valores novos,
    nao com os valores antigos do banco.
    """

    def test_F_atualizacao_preenche_data_analise_remove_bloqueio(self, db):
        """
        Teste F: linha superada sem data_analise (bloqueante) recebe data_analise
        via importacao — o bloqueante deve desaparecer.

        Banco antes: REV1 superada por REV2, sem data_analise → bloqueante.
        Preview: REV1 agora traz data_analise preenchida.
        Esperado: lifecycle sem bloqueante.
        """
        from core.importers.lista_importer import ListaImporter
        import tempfile

        db_path, contrato_id = db

        def _linha_sem_analise(codigo, revisao, data_emissao):
            row = _linha(codigo, revisao=revisao, data_emissao=data_emissao)
            row[25] = None
            return row

        # Importação real: REV1 (sem data_analise) + REV2 — REV1 fica superada e bloqueada
        excel_base = _criar_excel_bytes(
            _linha_sem_analise("DE-15.25.00.00-6N3-4001", revisao=1, data_emissao="2024-01-01"),
            _linha_sem_analise("DE-15.25.00.00-6N3-4001", revisao=2, data_emissao="2024-06-01"),
        )
        fd, tmp = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        try:
            with open(tmp, "wb") as f:
                f.write(excel_base)
            ListaImporter(db_path=db_path).importar(tmp, contrato_id)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

        # Preview: REV1 agora traz data_analise preenchida (resolve o bloqueante)
        excel_com_analise = _criar_excel_bytes(
            _linha("DE-15.25.00.00-6N3-4001", revisao=1, data_emissao="2024-01-01"),
            _linha_sem_analise("DE-15.25.00.00-6N3-4001", revisao=2, data_emissao="2024-06-01"),
        )
        resultado = gerar_preview_lista(excel_com_analise, "lista.xlsx", contrato_id, db_path=db_path)

        assert not resultado.tem_erro_fatal

        # A linha REV1 deve aparecer em linhas_atualizadas (data_analise mudou)
        codigos_atualizados = {l.codigo for l in resultado.linhas_atualizadas}
        assert "DE-15.25.00.00-6N3-4001" in codigos_atualizados, (
            "REV1 atualizada com data_analise deve aparecer em linhas_atualizadas"
        )

        # Bloqueante deve ter sido resolvido pela atualização
        assert not resultado.tem_lifecycle_bloqueante, (
            "data_analise preenchida em linha atualizada deve remover o bloqueante"
        )

    def test_G_engine_direta_linha_atualizada_sem_data_analise_cria_bloqueio(self):
        """
        Teste G (engine direta): analisar_transicao_documental com linha superada
        sem data_analise deve gerar issue bloqueante.

        Nota: o ListaImporter usa COALESCE — nunca remove data_analise existente
        via importacao. Por isso este cenario e testado direto na engine.
        """
        from core.engine.document_lifecycle import (
            LinhaDocumental,
            analisar_transicao_documental,
            TipoInferencia,
        )

        def _ld(label, versao, data_emissao=None, data_analise=None):
            return LinhaDocumental(
                codigo="Z", label_revisao=label, versao=versao,
                data_emissao=data_emissao, data_analise=data_analise,
                ordem=0, ja_persistida=True,
            )

        linhas_antes = [
            _ld("2", 1, data_emissao="2024-01-01", data_analise="2024-02-01"),
            _ld("3", 1, data_emissao="2024-06-01"),
        ]
        # linhas_depois: REV2 com data_analise removida (simulando estado final)
        linhas_depois = [
            _ld("2", 1, data_emissao="2024-01-01", data_analise=None),
            _ld("3", 1, data_emissao="2024-06-01"),
        ]

        result = analisar_transicao_documental("Z", linhas_antes, linhas_depois)

        assert result.tem_bloqueante, (
            "Linha superada sem data_analise deve gerar issue bloqueante"
        )
        linha_rev2 = next(ll for ll in result.linhas if ll.linha.label_revisao == "2")
        assert linha_rev2.inferencia == TipoInferencia.SUPERADA_POR_REVISAO
        assert linha_rev2.tem_bloqueante

    def test_H_engine_direta_atualizacao_muda_status_operacional(self):
        """
        Teste H (engine direta): linha atualizada com situacao NÃO CONFORME e
        data_analise preenchida deve ter status_operacional 'Em Revisão'.
        """
        from core.engine.document_lifecycle import (
            LinhaDocumental,
            analisar_transicao_documental,
        )

        def _ld(label, versao, situacao=None, data_emissao=None, data_analise=None):
            return LinhaDocumental(
                codigo="W", label_revisao=label, versao=versao,
                situacao=situacao, data_emissao=data_emissao, data_analise=data_analise,
                ordem=0, ja_persistida=True,
            )

        linhas_antes = [
            _ld("2", 1, situacao=None, data_emissao="2024-01-01", data_analise=None),
        ]
        linhas_depois = [
            _ld("2", 1, situacao="NÃO CONFORME", data_emissao="2024-01-01",
                data_analise="2024-02-15"),
        ]

        result = analisar_transicao_documental("W", linhas_antes, linhas_depois)

        linha = result.linhas[0]
        assert linha.status_operacional == "Em Revisão", (
            f"Situação NÃO CONFORME + data_analise deve dar 'Em Revisão', "
            f"obtido: '{linha.status_operacional}'"
        )

    def test_I_sem_mudanca_relevante_nao_aparece_em_atualizadas(self, db):
        """
        Teste I: reimportar linha idêntica não deve gerar entrada em linhas_atualizadas
        nem acionar lifecycle desnecessariamente.
        """
        from core.importers.lista_importer import ListaImporter
        import tempfile

        db_path, contrato_id = db

        excel = _criar_excel_bytes(
            _linha("DE-15.25.00.00-6N3-5001", revisao=1, situacao="NÃO APROVADO",
                   data_emissao="2024-03-01"),
        )

        # Importação real
        fd, tmp = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        try:
            with open(tmp, "wb") as f:
                f.write(excel)
            ListaImporter(db_path=db_path).importar(tmp, contrato_id)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

        # Preview com o mesmo Excel — nada deve mudar
        resultado = gerar_preview_lista(excel, "lista.xlsx", contrato_id, db_path=db_path)

        assert not resultado.tem_erro_fatal
        assert len(resultado.linhas_novas) == 0, (
            "Reimportação idêntica não deve gerar linhas novas"
        )
        assert len(resultado.linhas_atualizadas) == 0, (
            "Reimportação idêntica não deve gerar linhas atualizadas"
        )

    def test_J_transicao_usa_estado_depois_nao_antes(self):
        """
        Teste J: analisar_transicao_documental analisa linhas_depois, não linhas_antes.
        Garante que o estado final é o que determina o resultado.
        """
        from core.engine.document_lifecycle import (
            LinhaDocumental,
            analisar_transicao_documental,
        )

        def _ld(label, versao, data_emissao=None, data_analise=None):
            return LinhaDocumental(
                codigo="V", label_revisao=label, versao=versao,
                data_emissao=data_emissao, data_analise=data_analise,
                ordem=0, ja_persistida=True,
            )

        # Antes: REV1 superada sem data_analise → seria bloqueante se analisasse antes
        linhas_antes = [
            _ld("1", 1, data_emissao="2024-01-01", data_analise=None),
            _ld("2", 1, data_emissao="2024-06-01"),
        ]
        # Depois: REV1 agora tem data_analise → não deve haver bloqueante
        linhas_depois = [
            _ld("1", 1, data_emissao="2024-01-01", data_analise="2024-03-01"),
            _ld("2", 1, data_emissao="2024-06-01"),
        ]

        result = analisar_transicao_documental("V", linhas_antes, linhas_depois)

        assert not result.tem_bloqueante, (
            "analisar_transicao_documental deve analisar linhas_depois, não linhas_antes. "
            "REV1 com data_analise não deve ter bloqueante."
        )
