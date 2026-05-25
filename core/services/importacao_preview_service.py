"""
core/services/importacao_preview_service.py

Preview/dry-run da importacao da Lista de Documentos.

Estrategia: copia o banco real para um arquivo temporario,
executa o ListaImporter na copia e compara snapshots antes/depois
para montar um resumo do impacto sem alterar o banco operacional.

Nenhuma dependencia de Streamlit. Estado de sessao e renderizacao
permanecem na pagina.
"""

import gc
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from typing import Optional

from db.connection import get_connection, DB_PATH
from core.importers.lista_importer import ListaImporter
from core.engine.status import classificar_status
from core.engine.document_lifecycle import (
    LinhaDocumental,
    LifecycleResult,
    analisar_transicao_documental,
)


@dataclass
class MudancaStatusPreview:
    """Mudanca relevante detectada em um documento durante o dry-run."""
    codigo: str
    titulo: str
    tipo: str
    trecho: str
    # estado antes da importacao
    status_antes: Optional[str]
    situacao_antes: Optional[str]
    data_emissao_antes: Optional[str]
    ja_aprovado_antes: bool
    # estado depois da importacao simulada
    status_depois: str
    situacao_depois: Optional[str]
    data_emissao_depois: Optional[str]
    ja_aprovado_depois: bool
    # flags de classificacao
    eh_novo_documento: bool
    tem_mudanca_status: bool
    tem_mudanca_ja_aprovado: bool


@dataclass
class LinhaRevisaoPreview:
    """Uma linha de revisao nova ou atualizada detectada pelo dry-run."""
    codigo: str
    label_revisao: str
    versao: int
    data_emissao: Optional[str]
    data_analise: Optional[str]
    situacao: Optional[str]
    situacao_real: Optional[str]
    acao: str  # "nova" | "atualizada"


@dataclass
class ResultadoPreviewLista:
    """Resultado completo do dry-run da importacao da Lista de Documentos."""
    total_lidas: int = 0
    novos_documentos: int = 0
    documentos_atualizados: int = 0
    novas_revisoes: int = 0
    revisoes_atualizadas: int = 0
    inconsistencias: list = field(default_factory=list)
    erros: int = 0
    mudancas: list = field(default_factory=list)        # list[MudancaStatusPreview]
    linhas_novas: list = field(default_factory=list)    # list[LinhaRevisaoPreview]
    linhas_atualizadas: list = field(default_factory=list)  # list[LinhaRevisaoPreview]
    tem_erro_fatal: bool = False
    erro_fatal_mensagem: Optional[str] = None

    # Resultados de ciclo documental calculados pela DocumentLifecycleEngine
    # Populado por _enriquecer_com_lifecycle() apos o dry-run.
    lifecycle_results: list = field(default_factory=list)   # list[LifecycleResult]

    @property
    def total_inconsistencias(self) -> int:
        return len(self.inconsistencias)

    @property
    def mudancas_de_status(self) -> list:
        return [m for m in self.mudancas if m.tem_mudanca_status]

    @property
    def mudancas_ja_aprovado(self) -> list:
        return [m for m in self.mudancas if m.tem_mudanca_ja_aprovado]

    @property
    def documentos_novos_lista(self) -> list:
        return [m for m in self.mudancas if m.eh_novo_documento]

    @property
    def lifecycle_bloqueantes(self) -> list:
        """Issues bloqueantes detectadas pela engine de ciclo documental."""
        issues = []
        for lr in self.lifecycle_results:
            issues.extend(lr.issues_bloqueantes)
        return issues

    @property
    def tem_lifecycle_bloqueante(self) -> bool:
        return any(lr.tem_bloqueante for lr in self.lifecycle_results)


def _obter_linhas_revisao(contrato_id: int, db_path: str) -> dict:
    """
    Retorna todas as linhas de revisao do contrato agrupadas por codigo.

    Retorna: {codigo: [LinhaDocumental, ...]}

    Conexao fechada explicitamente (Windows file handle — ver _obter_snapshot).
    """
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT
                d.codigo,
                r.id,
                r.label_revisao,
                r.versao,
                r.situacao,
                r.data_emissao,
                r.data_analise,
                r.data_elaboracao,
                r.situacao_real,
                r.importacao_id,
                r.criado_em
            FROM revisoes r
            JOIN documentos d ON d.id = r.documento_id
            WHERE d.contrato_id = ?
            ORDER BY d.codigo, r.id
            """,
            (contrato_id,),
        ).fetchall()
    finally:
        conn.close()

    resultado: dict[str, list[LinhaDocumental]] = {}
    for i, row in enumerate(rows):
        codigo = row["codigo"]
        if codigo not in resultado:
            resultado[codigo] = []
        resultado[codigo].append(LinhaDocumental(
            codigo=codigo,
            label_revisao=row["label_revisao"] or "0",
            versao=row["versao"] or 1,
            situacao=row["situacao"],
            data_emissao=row["data_emissao"],
            data_analise=row["data_analise"],
            data_elaboracao=row["data_elaboracao"],
            situacao_real=row["situacao_real"],
            id=row["id"],
            importacao_id=row["importacao_id"],
            ordem=i,
            ja_persistida=True,
        ))
    return resultado


def _comparar_chaves_revisao(
    linhas_antes: dict,
    linhas_depois: dict,
) -> tuple[list, list, set]:
    """
    Compara linhas de revisao antes/depois usando chave logica codigo|label|versao.

    Retorna (linhas_novas, linhas_atualizadas, codigos_com_mudanca_revisao).

    Uma linha e 'nova' quando a chave nao existia antes.
    Uma linha e 'atualizada' quando a chave ja existia mas algum campo relevante mudou.
    codigos_com_mudanca_revisao inclui qualquer documento que teve insercao ou atualizacao
    de revisao — usado para acionar a engine de ciclo documental.
    """
    novas: list[LinhaRevisaoPreview] = []
    atualizadas: list[LinhaRevisaoPreview] = []
    codigos: set[str] = set()

    # Monta indice antes: {(codigo, label, versao): LinhaDocumental}
    idx_antes: dict[tuple, LinhaDocumental] = {}
    for lista in linhas_antes.values():
        for l in lista:
            idx_antes[(l.codigo, l.label_revisao, l.versao)] = l

    for codigo, lista_depois in linhas_depois.items():
        for l in lista_depois:
            chave = (l.codigo, l.label_revisao, l.versao)
            anterior = idx_antes.get(chave)

            if anterior is None:
                novas.append(LinhaRevisaoPreview(
                    codigo=l.codigo,
                    label_revisao=l.label_revisao,
                    versao=l.versao,
                    data_emissao=l.data_emissao,
                    data_analise=l.data_analise,
                    situacao=l.situacao,
                    situacao_real=l.situacao_real,
                    acao="nova",
                ))
                codigos.add(codigo)
            else:
                # Verifica se houve mudanca em campos relevantes
                if (
                    anterior.situacao != l.situacao
                    or anterior.data_emissao != l.data_emissao
                    or anterior.data_analise != l.data_analise
                    or anterior.situacao_real != l.situacao_real
                ):
                    atualizadas.append(LinhaRevisaoPreview(
                        codigo=l.codigo,
                        label_revisao=l.label_revisao,
                        versao=l.versao,
                        data_emissao=l.data_emissao,
                        data_analise=l.data_analise,
                        situacao=l.situacao,
                        situacao_real=l.situacao_real,
                        acao="atualizada",
                    ))
                    codigos.add(codigo)

    return novas, atualizadas, codigos


def _enriquecer_com_lifecycle(
    resultado: "ResultadoPreviewLista",
    linhas_antes: dict,
    linhas_depois: dict,
    codigos_alterados: set,
) -> None:
    """
    Enriquece ResultadoPreviewLista com analise da DocumentLifecycleEngine.

    Para cada documento que teve mudanca em nivel de revisao (nova ou atualizada):
    - Analisa o estado COMPLETO depois da importacao (banco temporario), nao apenas
      as linhas novas. Isso garante que linhas atualizadas sao analisadas com seus
      novos valores — ex: data_analise preenchida resolve bloqueante; data_analise
      ausente cria bloqueante.
    - Usa analisar_transicao_documental para refletir o estado final correto.

    Nao persiste nada. Nao altera o banco real.
    """
    if not codigos_alterados:
        return

    for codigo in codigos_alterados:
        todas_depois = linhas_depois.get(codigo, [])
        if not todas_depois:
            continue

        lifecycle = analisar_transicao_documental(
            codigo,
            linhas_antes=linhas_antes.get(codigo, []),
            linhas_depois=todas_depois,
        )
        resultado.lifecycle_results.append(lifecycle)


def _obter_snapshot(contrato_id: int, db_path: str) -> dict:
    """
    Retorna snapshot de todos os documentos do contrato com seus campos de status.

    Retorna: {codigo: {titulo, tipo, trecho, situacao, data_emissao, status_atual, ja_aprovado}}

    A conexao e fechada explicitamente para liberar o file handle no Windows,
    permitindo que arquivos temporarios sejam deletados logo apos a chamada.
    """
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT
                d.codigo,
                d.titulo,
                d.tipo,
                COALESCE(d.trecho, '00') AS trecho,
                r.situacao,
                r.data_emissao,
                CASE WHEN EXISTS (
                    SELECT 1 FROM revisoes rh
                    WHERE rh.documento_id = d.id
                      AND (rh.label_revisao = '0' OR rh.label_revisao GLOB '[A-Z]')
                ) THEN 1 ELSE 0 END AS ja_aprovado
            FROM documentos d
            LEFT JOIN revisoes r ON r.documento_id = d.id AND r.ultima_revisao = 1
            WHERE d.contrato_id = ?
            ORDER BY d.codigo
            """,
            (contrato_id,),
        ).fetchall()
        return {
            row["codigo"]: {
                "titulo":        row["titulo"],
                "tipo":          row["tipo"],
                "trecho":        row["trecho"],
                "situacao":      row["situacao"],
                "data_emissao":  row["data_emissao"],
                "status_atual":  classificar_status(row["situacao"], row["data_emissao"]),
                "ja_aprovado":   bool(row["ja_aprovado"]),
            }
            for row in rows
        }
    finally:
        conn.close()


def _comparar_snapshots(
    antes: dict,
    depois: dict,
) -> list:
    """
    Compara snapshots antes/depois e retorna lista de MudancaStatusPreview.

    Inclui: documentos novos, documentos com mudanca de status, documentos
    com mudanca de ja_aprovado. Exclui documentos sem nenhuma mudanca relevante.
    """
    mudancas: list[MudancaStatusPreview] = []
    for codigo, d in depois.items():
        a = antes.get(codigo)
        eh_novo = a is None

        status_antes      = a["status_atual"]   if a else None
        situacao_antes    = a["situacao"]        if a else None
        data_emissao_antes = a["data_emissao"]  if a else None
        ja_aprovado_antes = a["ja_aprovado"]     if a else False

        tem_mudanca_status      = status_antes != d["status_atual"]
        tem_mudanca_ja_aprovado = ja_aprovado_antes != d["ja_aprovado"]

        if eh_novo or tem_mudanca_status or tem_mudanca_ja_aprovado:
            mudancas.append(MudancaStatusPreview(
                codigo=codigo,
                titulo=d["titulo"] or "—",
                tipo=d["tipo"] or "—",
                trecho=d["trecho"] or "00",
                status_antes=status_antes,
                situacao_antes=situacao_antes,
                data_emissao_antes=data_emissao_antes,
                ja_aprovado_antes=ja_aprovado_antes,
                status_depois=d["status_atual"],
                situacao_depois=d["situacao"],
                data_emissao_depois=d["data_emissao"],
                ja_aprovado_depois=d["ja_aprovado"],
                eh_novo_documento=eh_novo,
                tem_mudanca_status=tem_mudanca_status,
                tem_mudanca_ja_aprovado=tem_mudanca_ja_aprovado,
            ))
    return mudancas


def gerar_preview_lista(
    arquivo_bytes: bytes,
    arquivo_nome: str,
    contrato_id: int,
    db_path: Optional[str] = None,
) -> ResultadoPreviewLista:
    """
    Simula a importacao da Lista de Documentos sem alterar o banco real.

    Passos:
    1. Salva bytes do Excel em arquivo temporario.
    2. Copia banco real para banco temporario.
    3. Captura snapshot do banco real (antes) e linhas de revisao (antes).
    4. Executa ListaImporter no banco temporario.
    5. Captura snapshot do banco temporario (depois) e linhas de revisao (depois).
    6. Compara snapshots de status; compara chaves de revisao.
    7. Enriquece com engine de ciclo documental para codigos com mudanca em revisoes.
    8. Remove arquivos temporarios (try/finally).

    O banco real nunca e tocado. Nenhuma importacao e registrada no historico real.
    """
    real_db = db_path or DB_PATH

    xls_fd, xls_tmp = tempfile.mkstemp(suffix=".xlsx")
    os.close(xls_fd)
    db_fd, db_tmp = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)

    try:
        # 1. Salvar Excel em arquivo temporario
        with open(xls_tmp, "wb") as f:
            f.write(arquivo_bytes)

        # 2. Copiar banco real para banco temporario
        shutil.copy2(real_db, db_tmp)

        # 3. Snapshots e linhas antes (banco real)
        snapshot_antes = _obter_snapshot(contrato_id, real_db)
        linhas_antes   = _obter_linhas_revisao(contrato_id, real_db)

        # 4. Importacao simulada no banco temporario
        importer = ListaImporter(db_path=db_tmp)
        resultado_imp = importer.importar(xls_tmp, contrato_id)

        # 5. Snapshots e linhas depois (banco temporario)
        snapshot_depois = _obter_snapshot(contrato_id, db_tmp)
        linhas_depois   = _obter_linhas_revisao(contrato_id, db_tmp)

        # 6. Comparacoes
        mudancas = _comparar_snapshots(snapshot_antes, snapshot_depois)
        linhas_novas, linhas_atualizadas, codigos_com_revisao = _comparar_chaves_revisao(
            linhas_antes, linhas_depois
        )

        # Engine de ciclo documental para TODO documento com mudanca em revisoes,
        # nao apenas aqueles com mudanca visivel no status final do snapshot.
        codigos_alterados = codigos_com_revisao | {m.codigo for m in mudancas}

        resultado_preview = ResultadoPreviewLista(
            total_lidas=resultado_imp.total_lidas,
            novos_documentos=resultado_imp.novos_documentos,
            documentos_atualizados=resultado_imp.documentos_atualizados,
            novas_revisoes=resultado_imp.novas_revisoes,
            revisoes_atualizadas=resultado_imp.revisoes_atualizadas,
            inconsistencias=resultado_imp.inconsistencias,
            erros=resultado_imp.erros,
            mudancas=mudancas,
            linhas_novas=linhas_novas,
            linhas_atualizadas=linhas_atualizadas,
        )

        # 7. Enriquecimento com engine de ciclo documental
        _enriquecer_com_lifecycle(
            resultado_preview, linhas_antes, linhas_depois, codigos_alterados
        )
        return resultado_preview

    except Exception as exc:
        return ResultadoPreviewLista(
            tem_erro_fatal=True,
            erro_fatal_mensagem=str(exc),
        )

    finally:
        # Forca o GC a coletar conexoes sqlite3 ainda em uso pelo ListaImporter
        # (que usa `with conn:` sem close explicito). Necessario no Windows para
        # liberar os file handles antes do os.unlink().
        gc.collect()
        for tmp in (xls_tmp, db_tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass
