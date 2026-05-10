"""
core/importers/arquivos_importer.py

Lê um arquivo de texto com nomes (ou caminhos) de arquivos — gerado por
'dir /b /o:n >nomes.txt' ou 'dir /b /s /o:n >nomes.txt' — e registra
cada arquivo reconhecido na tabela `arquivos`, vinculando-o ao documento
correspondente no banco.

Linhas cujo caminho contém 'OBSOLETO' são ignoradas automaticamente.
"""

import os
import sys
from dataclasses import dataclass, field
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db.connection import get_connection
from core.parsers.arquivo_parser import parsear_arquivo, ArquivoParseado, ErroParsearArquivo
from core.engine.preview_arquivos import ResultadoPreview


@dataclass
class ResultadoArquivos:
    novos:               int = 0
    ja_existentes:       int = 0
    sem_documento:       int = 0
    nao_reconhecidos:    int = 0
    obsoletos_ignorados: int = 0
    erros_parse:         List[str] = field(default_factory=list)
    sem_doc_codigos:     List[str] = field(default_factory=list)

    @property
    def total_linhas(self) -> int:
        return (self.novos + self.ja_existentes
                + self.sem_documento + self.nao_reconhecidos
                + self.obsoletos_ignorados)


class ArquivosImporter:

    def importar_texto(
        self,
        conteudo: str,
        contrato_id: int,
        nome_arquivo_txt: str = "nomes.txt",
        db_path: Optional[str] = None,
    ) -> ResultadoArquivos:
        """
        Processa o conteúdo de um nomes.txt e atualiza a tabela `arquivos`.

        conteudo           — texto completo do arquivo (str, não bytes)
        contrato_id        — contrato ao qual os arquivos pertencem
        nome_arquivo_txt   — nome original do arquivo enviado (para rastreabilidade)
        """
        linhas = [l for l in conteudo.splitlines() if l.strip()]
        resultado = ResultadoArquivos()

        kwargs = {"db_path": db_path} if db_path else {}
        with get_connection(**kwargs) as conn:
            importacao_id = self._registrar_importacao(
                conn, contrato_id, nome_arquivo_txt, len(linhas)
            )

            for linha in linhas:
                self._processar_linha(conn, linha, contrato_id, importacao_id, resultado)

            self._finalizar_importacao(conn, importacao_id, resultado)

        return resultado

    # ------------------------------------------------------------------

    def _processar_linha(self, conn, linha, contrato_id, importacao_id, resultado):
        if "OBSOLETO" in linha.upper():
            resultado.obsoletos_ignorados += 1
            return

        parseado = parsear_arquivo(linha)

        if isinstance(parseado, ErroParsearArquivo):
            resultado.nao_reconhecidos += 1
            resultado.erros_parse.append(f"{parseado.nome_arquivo}: {parseado.motivo}")
            self._registrar_inconsistencia(
                conn, importacao_id,
                documento_codigo=parseado.nome_arquivo,
                tipo="arquivo_nao_reconhecido",
                descricao=parseado.motivo,
            )
            return

        documento_id = self._buscar_documento(conn, contrato_id, parseado.codigo)
        if documento_id is None:
            resultado.sem_documento += 1
            resultado.sem_doc_codigos.append(parseado.codigo)
            self._registrar_inconsistencia(
                conn, importacao_id,
                documento_codigo=parseado.codigo,
                tipo="arquivo_sem_documento",
                descricao=f"Arquivo '{parseado.nome_arquivo}' reconhecido mas código não encontrado no banco",
            )
            return

        caminho = linha.strip() if os.path.basename(linha.strip()) != linha.strip() else None
        revisao_detectada = (
            f"{parseado.label_revisao}-{parseado.versao}"
            if parseado.versao is not None
            else parseado.label_revisao
        )
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO arquivos
                (documento_id, nome_arquivo, extensao, caminho,
                 origem, revisao_detectada, tipo_detectado, importacao_id)
            VALUES (?, ?, ?, ?, 'importacao_nomes', ?, ?, ?)
            """,
            (
                documento_id,
                parseado.nome_arquivo,
                parseado.extensao,
                caminho,
                revisao_detectada,
                parseado.codigo.split("-")[0],
                importacao_id,
            ),
        )
        if cur.rowcount > 0:
            resultado.novos += 1
        else:
            resultado.ja_existentes += 1

    def _buscar_documento(self, conn, contrato_id: int, codigo: str) -> Optional[int]:
        row = conn.execute(
            "SELECT id FROM documentos WHERE contrato_id = ? AND codigo = ?",
            (contrato_id, codigo),
        ).fetchone()
        return row[0] if row else None

    def _registrar_inconsistencia(self, conn, importacao_id, documento_codigo, tipo, descricao):
        conn.execute(
            """
            INSERT INTO inconsistencias
                (importacao_id, documento_codigo, tipo_inconsistencia, descricao)
            VALUES (?, ?, ?, ?)
            """,
            (importacao_id, documento_codigo, tipo, descricao),
        )

    def confirmar_preview(
        self,
        preview: ResultadoPreview,
        titulos: dict,
        contrato_id: int,
        nome_arquivo_txt: str = "nomes.txt",
        db_path: Optional[str] = None,
    ) -> "ResultadoArquivos":
        """
        Grava no banco os arquivos confirmados pelo usuário após o preview.

        preview         — resultado de gerar_preview()
        titulos         — dict codigo → Objeto editado pelo usuário na UI
        contrato_id     — contrato alvo
        nome_arquivo_txt — nome do arquivo original (para rastreabilidade)
        """
        # Valida Objeto obrigatório antes de abrir qualquer conexão
        vazios = [
            codigo for codigo in preview.novos_por_codigo
            if not (titulos.get(codigo) or "").strip()
        ]
        if vazios:
            raise ValueError(
                f"Objeto obrigatório para {len(vazios)} documento(s): "
                + ", ".join(vazios[:5])
                + ("…" if len(vazios) > 5 else "")
            )

        total_arquivos = preview.total_arquivos_novos
        resultado = ResultadoArquivos()

        kwargs = {"db_path": db_path} if db_path else {}
        with get_connection(**kwargs) as conn:
            importacao_id = self._registrar_importacao(
                conn, contrato_id, nome_arquivo_txt, total_arquivos
            )

            # Persiste erros do preview em inconsistencias para auditoria posterior
            for codigo in preview.sem_documento:
                self._registrar_inconsistencia(
                    conn, importacao_id,
                    documento_codigo=codigo,
                    tipo="arquivo_sem_documento",
                    descricao="Arquivo reconhecido mas código não encontrado no banco",
                )
            for nome in preview.nao_reconhecidos:
                self._registrar_inconsistencia(
                    conn, importacao_id,
                    documento_codigo=nome,
                    tipo="arquivo_nao_reconhecido",
                    descricao="Nome de arquivo não segue o padrão esperado",
                )

            for codigo, items in preview.novos_por_codigo.items():
                titulo_novo = (titulos.get(codigo) or "").strip()
                titulo_anterior = items[0].titulo_atual

                if titulo_novo and titulo_novo != titulo_anterior:
                    conn.execute(
                        "UPDATE documentos SET titulo = ? WHERE id = ?",
                        (titulo_novo, items[0].documento_id),
                    )

                for item in items:
                    revisao_detectada = (
                        f"{item.label_revisao}-{item.versao}"
                        if item.versao is not None
                        else item.label_revisao
                    )
                    cur = conn.execute(
                        """
                        INSERT OR IGNORE INTO arquivos
                            (documento_id, nome_arquivo, extensao, caminho,
                             origem, revisao_detectada, tipo_detectado, importacao_id)
                        VALUES (?, ?, ?, ?, 'importacao_nomes', ?, ?, ?)
                        """,
                        (
                            item.documento_id,
                            item.nome_arquivo,
                            item.extensao,
                            item.caminho,
                            revisao_detectada,
                            codigo.split("-")[0],
                            importacao_id,
                        ),
                    )
                    if cur.rowcount > 0:
                        resultado.novos += 1
                    else:
                        resultado.ja_existentes += 1

            self._finalizar_importacao(conn, importacao_id, resultado)

        return resultado

    def _registrar_importacao(self, conn, contrato_id, arquivo, total_linhas) -> int:
        conn.execute(
            """
            INSERT INTO importacoes
                (contrato_id, origem, arquivo_importado, total_registros, status)
            VALUES (?, 'arquivos_nomes', ?, ?, 'em_andamento')
            """,
            (contrato_id, arquivo, total_linhas),
        )
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def _finalizar_importacao(self, conn, importacao_id, resultado):
        conn.execute(
            """
            UPDATE importacoes SET
                total_novos       = ?,
                total_atualizados = ?,
                total_erros       = ?,
                status            = 'concluido',
                confirmado_em     = datetime('now')
            WHERE id = ?
            """,
            (
                resultado.novos,
                resultado.ja_existentes,
                resultado.nao_reconhecidos + resultado.sem_documento,
                importacao_id,
            ),
        )
