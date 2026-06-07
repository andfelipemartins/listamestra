"""
core/services/grd_service.py

Regras de aplicação para a GRD como entidade operacional (Guia de Remessa).

Orquestra o GrdRepository: valida cabeçalho e número único por contrato, congela
o snapshot dos itens no momento da criação, controla o status de ciclo
(rascunho→emitida→enviada→recebida/cancelada), lista/filtra GRDs e prepara os
dados para exportação Excel/PDF. Não depende de Streamlit.
"""

import sqlite3
from dataclasses import dataclass
from typing import Optional

from core.engine.disciplinas import ESTRUTURA
from core.engine.status import NOME_TRECHO, classificar_status
from core.formatacao import disciplina_do_codigo, filtrar_documentos
from core.repositories.grd_repository import GrdRepository, STATUS_GRD
from db.connection import get_connection

# Status com que uma GRD pode nascer.
STATUS_INICIAIS = ("rascunho", "emitida")
_QTD_CAMPOS = ("qtd_a0", "qtd_a1", "qtd_a2", "qtd_a3", "qtd_a4", "qtd_digital")


@dataclass
class ResultadoGrd:
    sucesso: bool
    grd_id: Optional[int] = None
    total_itens: int = 0
    mensagem: str = ""


class GrdService:
    def __init__(self, grd_repo: Optional[GrdRepository] = None, db_path: Optional[str] = None):
        self._db_path = db_path
        self._repo = grd_repo or GrdRepository(db_path)

    def _connection_kwargs(self) -> dict:
        return {"db_path": self._db_path} if self._db_path else {}

    # ------------------------------------------------------------------
    # Listagem de documentos elegíveis (tabela de seleção/preparação)
    # ------------------------------------------------------------------

    def listar_documentos_selecionaveis(
        self, contrato_id: int, filtros: Optional[str] = None
    ) -> list[dict]:
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
        doc["status_atual"] = classificar_status(doc.get("situacao"), doc.get("data_emissao"))
        return doc

    # ------------------------------------------------------------------
    # Validação
    # ------------------------------------------------------------------

    def validar_cabecalho(self, contrato_id: int, cabecalho: dict) -> list[str]:
        """Retorna lista de erros (vazia se válido)."""
        erros: list[str] = []
        status = (cabecalho.get("status") or "rascunho")
        if status not in STATUS_INICIAIS:
            erros.append(f"Status inicial inválido: {status!r} (use 'rascunho' ou 'emitida').")
        numero = (cabecalho.get("numero_grd") or "").strip()
        if numero and self._repo.numero_existe(contrato_id, numero):
            erros.append(f"Já existe uma GRD com o número '{numero}' neste contrato.")
        return erros

    def numero_disponivel(self, contrato_id: int, numero_grd: str) -> bool:
        return not self._repo.numero_existe(contrato_id, numero_grd)

    # ------------------------------------------------------------------
    # Criação com snapshot congelado
    # ------------------------------------------------------------------

    def criar_grd(self, contrato_id: int, cabecalho: dict, itens: list[dict]) -> ResultadoGrd:
        """
        Cria UMA GRD e vincula os itens selecionados, congelando o snapshot de
        cada documento (código, título, revisão, versão, situação, data, trecho,
        disciplina) e as quantidades de cópias por formato.

        `itens`: lista de dicts com `revisao_id` e qtd_a0..qtd_digital.
        O snapshot é montado a partir do estado atual do documento no banco.
        """
        itens = [it for it in (itens or []) if it.get("revisao_id") is not None]
        if not itens:
            return ResultadoGrd(False, mensagem="Selecione ao menos um documento para compor a GRD.")

        erros = self.validar_cabecalho(contrato_id, cabecalho)
        if erros:
            return ResultadoGrd(False, mensagem=" ".join(erros))

        # Estado atual dos documentos para congelar o snapshot
        docs = {d["revisao_id"]: d for d in self._repo.listar_documentos_para_grd(contrato_id)}

        data = {
            "contrato_id": contrato_id,
            "numero_grd":  (cabecalho.get("numero_grd") or "").strip() or None,
            "data_envio":  cabecalho.get("data_envio") or None,
            "setor":       (cabecalho.get("setor") or "").strip() or None,
            "trecho":      (cabecalho.get("trecho") or "").strip() or None,
            "modulo":      (cabecalho.get("modulo") or "").strip() or None,
            "observacoes": (cabecalho.get("observacoes") or "").strip() or None,
            "status":      cabecalho.get("status") or "rascunho",
            "destinatario": (cabecalho.get("destinatario") or "").strip() or None,
            "ac":          (cabecalho.get("ac") or "").strip() or None,
            "obra":        (cabecalho.get("obra") or "").strip() or None,
            "emitido_por": (cabecalho.get("emitido_por") or "").strip() or None,
        }

        try:
            with get_connection(**self._connection_kwargs()) as conn:
                grd_id = self._repo.criar_remessa(data, conn=conn)
                total = 0
                vistos = set()
                for it in itens:
                    rid = int(it["revisao_id"])
                    if rid in vistos:
                        continue
                    vistos.add(rid)
                    total += self._repo.adicionar_item_snapshot(
                        grd_id, self._montar_snapshot(rid, docs.get(rid, {}), it), conn=conn
                    )
        except sqlite3.IntegrityError:
            return ResultadoGrd(
                False,
                mensagem=f"Número de GRD duplicado no contrato: '{data['numero_grd']}'.",
            )

        return ResultadoGrd(
            True, grd_id=grd_id, total_itens=total,
            mensagem=f"GRD criada com {total} documento(s).",
        )

    @staticmethod
    def _montar_snapshot(revisao_id: int, doc: dict, item: dict) -> dict:
        trecho = doc.get("trecho") or ""
        disc = doc.get("disciplina") or disciplina_do_codigo(doc.get("codigo", "")) or None
        snap = {
            "revisao_id": revisao_id,
            "codigo_snapshot":        doc.get("codigo"),
            "titulo_snapshot":        doc.get("titulo"),
            "label_revisao_snapshot": doc.get("label_revisao"),
            "versao_snapshot":        doc.get("versao"),
            "situacao_snapshot":      doc.get("situacao"),
            "data_emissao_snapshot":  doc.get("data_emissao"),
            "trecho_snapshot":        NOME_TRECHO.get(trecho, trecho) or None,
            "disciplina_snapshot":    disc,
        }
        for campo in _QTD_CAMPOS:
            snap[campo] = int(item.get(campo) or 0)
        return snap

    # ------------------------------------------------------------------
    # Status de ciclo
    # ------------------------------------------------------------------

    def alterar_status(self, grd_id: int, novo_status: str, extra: Optional[dict] = None) -> ResultadoGrd:
        if novo_status not in STATUS_GRD:
            return ResultadoGrd(False, grd_id=grd_id, mensagem=f"Status inválido: {novo_status!r}.")
        self._repo.atualizar_status(grd_id, novo_status, extra)
        return ResultadoGrd(True, grd_id=grd_id, mensagem=f"Status alterado para '{novo_status}'.")

    def cancelar_grd(self, grd_id: int) -> ResultadoGrd:
        """Cancela a GRD (preserva todos os dados)."""
        return self.alterar_status(grd_id, "cancelada")

    # ------------------------------------------------------------------
    # Consulta
    # ------------------------------------------------------------------

    def listar_grds(self, contrato_id: int, filtros: Optional[dict] = None) -> list[dict]:
        return self._repo.listar_remessas(contrato_id, filtros)

    def buscar_grd(self, grd_id: int) -> dict | None:
        return self._repo.buscar_por_id(grd_id)

    def listar_itens(self, grd_id: int) -> list[dict]:
        return self._repo.listar_itens(grd_id)

    # ------------------------------------------------------------------
    # Exportação
    # ------------------------------------------------------------------

    def montar_dados_exportacao(self, grd_id: int) -> Optional[dict]:
        """Dict {cabecalho, itens} pronto para os exportadores."""
        cab = self._repo.buscar_por_id(grd_id)
        if cab is None:
            return None
        return {"cabecalho": cab, "itens": self._repo.listar_itens(grd_id)}

    def exportar_excel(self, grd_id: int) -> Optional[bytes]:
        dados = self.montar_dados_exportacao(grd_id)
        if dados is None:
            return None
        from core.exporters.grd_exporter import exportar_grd_excel
        return exportar_grd_excel(dados)

    def exportar_pdf(self, grd_id: int) -> Optional[bytes]:
        dados = self.montar_dados_exportacao(grd_id)
        if dados is None:
            return None
        from core.exporters.grd_exporter import exportar_grd_pdf
        return exportar_grd_pdf(dados)
