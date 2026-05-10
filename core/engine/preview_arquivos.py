"""
core/engine/preview_arquivos.py

Geração de preview (dry-run) da importação de arquivos via nomes.txt.

Identifica apenas o que é novo — arquivos já registrados não aparecem.
Agrupa por código de documento para que o usuário confirme/preencha
o Objeto uma única vez por documento, mesmo que haja PDF + DWG.
"""

import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db.connection import get_connection
from core.parsers.arquivo_parser import parsear_arquivo, ArquivoParseado, ErroParsearArquivo


@dataclass
class ItemPreview:
    """Representa um arquivo novo, pronto para confirmação."""
    nome_arquivo:  str
    codigo:        str
    label_revisao: str
    versao:        Optional[int]
    extensao:      str
    documento_id:  int
    titulo_atual:  Optional[str]  # pré-preenchido de documentos ou documentos_previstos
    caminho:       Optional[str]  # path completo se disponível


@dataclass
class ResultadoPreview:
    """
    Resultado de um dry-run da importação de arquivos.

    novos_por_codigo — dict codigo → lista de ItemPreview (PDF + DWG do mesmo doc)
    Cada chave representa um documento; o Objeto é confirmado/preenchido uma
    vez por documento.
    """
    novos_por_codigo: Dict[str, List[ItemPreview]] = field(default_factory=dict)
    ja_existentes:    int = 0
    sem_documento:    List[str] = field(default_factory=list)
    nao_reconhecidos: int = 0
    obsoletos:        int = 0

    @property
    def total_arquivos_novos(self) -> int:
        return sum(len(v) for v in self.novos_por_codigo.values())

    @property
    def total_documentos_novos(self) -> int:
        return len(self.novos_por_codigo)

    @property
    def vazio(self) -> bool:
        return self.total_arquivos_novos == 0


def gerar_preview(
    conteudo: str,
    contrato_id: int,
    db_path: Optional[str] = None,
) -> ResultadoPreview:
    """
    Parseia o conteúdo de um nomes.txt e retorna o que seria importado,
    sem gravar nada no banco.

    conteudo    — texto completo do arquivo (str)
    contrato_id — contrato ao qual os arquivos pertencem
    """
    linhas = [l for l in conteudo.splitlines() if l.strip()]
    resultado = ResultadoPreview()

    kwargs = {"db_path": db_path} if db_path else {}
    with get_connection(**kwargs) as conn:
        for linha in linhas:
            _processar_linha(conn, linha, contrato_id, resultado)

    return resultado


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _processar_linha(conn, linha: str, contrato_id: int, resultado: ResultadoPreview):
    if "OBSOLETO" in linha.upper():
        resultado.obsoletos += 1
        return

    parseado = parsear_arquivo(linha)
    if isinstance(parseado, ErroParsearArquivo):
        resultado.nao_reconhecidos += 1
        return

    if _ja_existe(conn, contrato_id, parseado.nome_arquivo):
        resultado.ja_existentes += 1
        return

    doc = _buscar_documento(conn, contrato_id, parseado.codigo)
    if doc is None:
        if parseado.codigo not in resultado.sem_documento:
            resultado.sem_documento.append(parseado.codigo)
        return

    linha_strip = linha.strip()
    caminho = linha_strip if os.path.basename(linha_strip) != linha_strip else None

    item = ItemPreview(
        nome_arquivo=parseado.nome_arquivo,
        codigo=parseado.codigo,
        label_revisao=parseado.label_revisao,
        versao=parseado.versao,
        extensao=parseado.extensao,
        documento_id=doc["id"],
        titulo_atual=doc["titulo"],
        caminho=caminho,
    )

    if parseado.codigo not in resultado.novos_por_codigo:
        resultado.novos_por_codigo[parseado.codigo] = []
    resultado.novos_por_codigo[parseado.codigo].append(item)


def _ja_existe(conn, contrato_id: int, nome_arquivo: str) -> bool:
    return conn.execute(
        """
        SELECT 1 FROM arquivos a
        JOIN documentos d ON d.id = a.documento_id
        WHERE d.contrato_id = ? AND a.nome_arquivo = ?
        """,
        (contrato_id, nome_arquivo),
    ).fetchone() is not None


def _buscar_documento(conn, contrato_id: int, codigo: str) -> Optional[dict]:
    row = conn.execute(
        """
        SELECT d.id,
               COALESCE(d.titulo, dp.titulo) AS titulo
        FROM documentos d
        LEFT JOIN documentos_previstos dp
               ON dp.contrato_id = d.contrato_id AND dp.codigo = d.codigo
        WHERE d.contrato_id = ? AND d.codigo = ?
        """,
        (contrato_id, codigo),
    ).fetchone()
    return dict(row) if row else None
