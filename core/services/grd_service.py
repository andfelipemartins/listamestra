"""
core/services/grd_service.py

Regras de aplicação para a geração de GRDs em lote (Guia de Remessa).

Orquestra o GrdRepository: cria UMA remessa (cabeçalho) e a aplica a múltiplas
revisões selecionadas em uma única transação, e lista documentos elegíveis já
enriquecidos para exibição/filtragem.

Não depende de Streamlit.
"""

from dataclasses import dataclass
from typing import Optional

from core.engine.disciplinas import ESTRUTURA
from core.engine.status import NOME_TRECHO, classificar_status
from core.formatacao import disciplina_do_codigo, filtrar_documentos
from core.repositories.grd_repository import GrdRepository
from db.connection import get_connection


@dataclass
class ResultadoGrd:
    sucesso: bool
    grd_id: Optional[int] = None
    total_itens: int = 0
    mensagem: str = ""


class GrdService:
    def __init__(
        self,
        grd_repo: Optional[GrdRepository] = None,
        db_path: Optional[str] = None,
    ):
        self._db_path = db_path
        self._repo = grd_repo or GrdRepository(db_path)

    def _connection_kwargs(self) -> dict:
        return {"db_path": self._db_path} if self._db_path else {}

    # ------------------------------------------------------------------
    # Listagem de documentos elegíveis (com enriquecimento de exibição)
    # ------------------------------------------------------------------

    def listar_documentos_selecionaveis(
        self, contrato_id: int, filtros: Optional[str] = None
    ) -> list[dict]:
        """
        Documentos com última revisão, enriquecidos para a tabela de seleção.

        Campos de exibição: nome_trecho, disciplina_display, status_atual.
        `filtros` aplica busca textual (código, título, trecho, estrutura, status).
        """
        docs = self._repo.listar_documentos_para_grd(contrato_id)
        enriquecidos = [self._enriquecer(d) for d in docs]
        if filtros:
            enriquecidos = filtrar_documentos(
                enriquecidos, filtros,
                campos=["codigo", "titulo", "nome_trecho", "disciplina_display", "status_atual"],
            )
        return enriquecidos

    @staticmethod
    def _enriquecer(doc: dict) -> dict:
        doc = dict(doc)
        trecho = doc.get("trecho") or ""
        doc["nome_trecho"] = NOME_TRECHO.get(trecho, trecho)
        disc = doc.get("disciplina") or disciplina_do_codigo(doc.get("codigo", "")) or ""
        doc["disciplina_display"] = disc
        doc["disciplina_desc"] = ESTRUTURA.get(disc, "")
        doc["status_atual"] = classificar_status(
            doc.get("situacao"), doc.get("data_emissao")
        )
        return doc

    # ------------------------------------------------------------------
    # Criação da GRD (cabeçalho + itens em uma transação)
    # ------------------------------------------------------------------

    def criar_grd(
        self,
        contrato_id: int,
        cabecalho: dict,
        revisao_ids: list[int],
    ) -> ResultadoGrd:
        """
        Cria UMA GRD e vincula todas as revisões selecionadas em uma transação.

        O usuário informa número/data/setor/trecho/módulo/observações apenas uma
        vez (cabeçalho); o serviço aplica a todas as revisões. Exige ≥ 1 revisão.
        """
        ids = [int(r) for r in dict.fromkeys(revisao_ids or [])]  # dedup preservando ordem
        if not ids:
            return ResultadoGrd(
                sucesso=False,
                mensagem="Selecione ao menos um documento/revisão para compor a GRD.",
            )

        data = {
            "contrato_id": contrato_id,
            "numero_grd":  (cabecalho.get("numero_grd") or "").strip() or None,
            "data_envio":  cabecalho.get("data_envio") or None,
            "setor":       (cabecalho.get("setor") or "").strip() or None,
            "trecho":      (cabecalho.get("trecho") or "").strip() or None,
            "modulo":      (cabecalho.get("modulo") or "").strip() or None,
            "observacoes": (cabecalho.get("observacoes") or "").strip() or None,
        }

        with get_connection(**self._connection_kwargs()) as conn:
            grd_id = self._repo.criar_remessa(data, conn=conn)
            total = self._repo.adicionar_itens(grd_id, ids, conn=conn)

        return ResultadoGrd(
            sucesso=True,
            grd_id=grd_id,
            total_itens=total,
            mensagem=f"GRD criada com {total} documento(s) vinculado(s).",
        )

    # ------------------------------------------------------------------
    # Consulta de GRDs criadas
    # ------------------------------------------------------------------

    def listar_grds(self, contrato_id: int) -> list[dict]:
        return self._repo.listar_remessas(contrato_id)

    def listar_itens(self, grd_id: int) -> list[dict]:
        return self._repo.listar_itens(grd_id)
