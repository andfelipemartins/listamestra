"""
core/services/grd_service.py

Regras de aplicaÃ§Ã£o para a GRD como entidade operacional (Guia de Remessa).

Orquestra o GrdRepository: valida cabeÃ§alho e nÃºmero Ãºnico por contrato, congela
o snapshot dos itens no momento da criaÃ§Ã£o, controla o status de ciclo
(rascunhoâ†’emitidaâ†’enviadaâ†’recebida/cancelada), lista/filtra GRDs e prepara os
dados para exportaÃ§Ã£o Excel/PDF. NÃ£o depende de Streamlit.
"""

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from core.config import GRD_TOKEN_TTL_DIAS
from core.engine.disciplinas import ESTRUTURA
from core.engine.status import NOME_TRECHO, classificar_status
from core.formatacao import disciplina_do_codigo, filtrar_documentos
from core.repositories.grd_repository import GrdRepository, STATUS_GRD
from db.connection import get_connection

# Status com que uma GRD pode nascer.
STATUS_INICIAIS = ("rascunho", "emitida")
_QTD_CAMPOS = ("qtd_a0", "qtd_a1", "qtd_a2", "qtd_a3", "qtd_a4", "qtd_digital")

# MÃ¡quina de estados unidirecional da GRD (regra de domÃ­nio central,
# reutilizÃ¡vel por qualquer adapter futuro â€” FastAPI/Django).
TRANSICOES: dict[str, set] = {
    "rascunho": {"emitida"},
    "emitida":  {"enviada", "anulada"},
    "enviada":  {"recebida", "anulada"},
    "recebida": set(),   # imutÃ¡vel
    "anulada":  set(),   # imutÃ¡vel
}


@dataclass
class ResultadoGrd:
    sucesso: bool
    grd_id: Optional[int] = None
    total_itens: int = 0
    mensagem: str = ""
    dados: Optional[dict] = None


class GrdService:
    def __init__(self, grd_repo: Optional[GrdRepository] = None, db_path: Optional[str] = None):
        self._db_path = db_path
        self._repo = grd_repo or GrdRepository(db_path)

    def _connection_kwargs(self) -> dict:
        return {"db_path": self._db_path} if self._db_path else {}

    @staticmethod
    def _agora() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _iso(dt: datetime) -> str:
        return dt.astimezone(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def _parse_iso(valor: Optional[str]) -> Optional[datetime]:
        if not valor:
            return None
        texto = str(valor)
        try:
            if texto.endswith("Z"):
                texto = texto[:-1] + "+00:00"
            dt = datetime.fromisoformat(texto)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Listagem de documentos elegÃ­veis (tabela de seleÃ§Ã£o/preparaÃ§Ã£o)
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
    # ValidaÃ§Ã£o
    # ------------------------------------------------------------------

    def validar_cabecalho(self, contrato_id: int, cabecalho: dict) -> list[str]:
        """Retorna lista de erros (vazia se vÃ¡lido)."""
        erros: list[str] = []
        status = (cabecalho.get("status") or "rascunho")
        if status not in STATUS_INICIAIS:
            erros.append(f"Status inicial invÃ¡lido: {status!r} (use 'rascunho' ou 'emitida').")
        numero = (cabecalho.get("numero_grd") or "").strip()
        if numero and self._repo.numero_existe(contrato_id, numero):
            erros.append(f"JÃ¡ existe uma GRD com o nÃºmero '{numero}' neste contrato.")
        return erros

    def numero_disponivel(self, contrato_id: int, numero_grd: str) -> bool:
        return not self._repo.numero_existe(contrato_id, numero_grd)

    # ------------------------------------------------------------------
    # CriaÃ§Ã£o com snapshot congelado
    # ------------------------------------------------------------------

    def criar_grd(self, contrato_id: int, cabecalho: dict, itens: list[dict]) -> ResultadoGrd:
        """
        Cria UMA GRD e vincula os itens selecionados, congelando o snapshot de
        cada documento (cÃ³digo, tÃ­tulo, revisÃ£o, versÃ£o, situaÃ§Ã£o, data, trecho,
        disciplina) e as quantidades de cÃ³pias por formato.

        `itens`: lista de dicts com `revisao_id` e qtd_a0..qtd_digital.
        O snapshot Ã© montado a partir do estado atual do documento no banco.
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
                mensagem=f"NÃºmero de GRD duplicado no contrato: '{data['numero_grd']}'.",
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
    # Ciclo formal de status (unidirecional)
    # ------------------------------------------------------------------

    @staticmethod
    def transicao_permitida(de: str, para: str) -> bool:
        return para in TRANSICOES.get(de, set())

    def _transitar(self, grd_id: int, novo: str, extra: Optional[dict] = None) -> ResultadoGrd:
        grd = self._repo.buscar_por_id(grd_id)
        if grd is None:
            return ResultadoGrd(False, grd_id=grd_id, mensagem="GRD nÃ£o encontrada.")
        atual = grd.get("status") or "rascunho"
        if not self.transicao_permitida(atual, novo):
            return ResultadoGrd(
                False, grd_id=grd_id,
                mensagem=f"TransiÃ§Ã£o de status nÃ£o permitida: '{atual}' â†’ '{novo}'.",
            )
        self._repo.atualizar_status(grd_id, novo, extra)
        return ResultadoGrd(True, grd_id=grd_id, mensagem=f"GRD agora estÃ¡ '{novo}'.")

    def emitir_grd(self, grd_id: int) -> ResultadoGrd:
        """rascunho â†’ emitida. Exige nÃºmero formal (reservado para sempre)."""
        grd = self._repo.buscar_por_id(grd_id)
        if grd is None:
            return ResultadoGrd(False, grd_id=grd_id, mensagem="GRD nÃ£o encontrada.")
        numero = (grd.get("numero_grd") or "").strip()
        if not numero:
            return ResultadoGrd(False, grd_id=grd_id, mensagem="Informe o nÃºmero da GRD antes de emitir.")
        if self._repo.numero_existe(grd["contrato_id"], numero, excluir_id=grd_id):
            return ResultadoGrd(False, grd_id=grd_id, mensagem=f"NÃºmero '{numero}' jÃ¡ usado neste contrato.")
        return self._transitar(grd_id, "emitida")

    def marcar_enviada(self, grd_id: int) -> ResultadoGrd:
        """emitida â†’ enviada."""
        return self._transitar(grd_id, "enviada")

    def marcar_recebida(
        self, grd_id: int, recebido_por: str, recebido_cargo: str,
        declaracao: Optional[str] = None, recebido_em: Optional[str] = None,
    ) -> ResultadoGrd:
        """enviada â†’ recebida. Nome e cargo sÃ£o obrigatÃ³rios. E-mail NÃƒO Ã© exigido."""
        if not (recebido_por or "").strip() or not (recebido_cargo or "").strip():
            return ResultadoGrd(
                False, grd_id=grd_id,
                mensagem="Nome e cargo de quem recebeu sÃ£o obrigatÃ³rios.",
            )
        from datetime import date
        quando = recebido_em or date.today().isoformat()
        extra = {
            "recebido_por": recebido_por.strip(),
            "recebido_cargo": recebido_cargo.strip(),
            "declaracao_recebimento": (declaracao or "").strip() or None,
            "recebido_em": quando,
            "data_recebimento": quando,
        }
        return self._transitar(grd_id, "recebida", extra)

    def anular_grd(self, grd_id: int, motivo: str) -> ResultadoGrd:
        """emitida/enviada â†’ anulada. Motivo obrigatÃ³rio; nÃ£o apaga dados."""
        if not (motivo or "").strip():
            return ResultadoGrd(False, grd_id=grd_id, mensagem="Motivo Ã© obrigatÃ³rio para anular a GRD.")
        from datetime import datetime
        extra = {"motivo_anulacao": motivo.strip(), "anulada_em": datetime.now().isoformat(timespec="seconds")}
        return self._transitar(grd_id, "anulada", extra)

    def excluir_rascunho(self, grd_id: int) -> ResultadoGrd:
        """ExclusÃ£o fÃ­sica â€” apenas GRD em rascunho. Libera o nÃºmero para reuso."""
        if self._repo.excluir_rascunho(grd_id):
            return ResultadoGrd(True, grd_id=grd_id, mensagem="Rascunho de GRD excluÃ­do.")
        return ResultadoGrd(False, grd_id=grd_id, mensagem="SÃ³ Ã© possÃ­vel excluir GRD em rascunho.")

    def pode_editar(self, grd_id: int) -> bool:
        grd = self._repo.buscar_por_id(grd_id)
        return bool(grd) and grd.get("status") == "rascunho"

    def pode_excluir(self, grd_id: int) -> bool:
        return self.pode_editar(grd_id)

    # ------------------------------------------------------------------
    # Recebimento por token (preparaÃ§Ã£o â€” sem rota pÃºblica nesta etapa)
    # ------------------------------------------------------------------

    def gerar_token_recebimento(self, grd_id: int) -> ResultadoGrd:
        """
        Gera e salva um token Ãºnico para recebimento por link.

        Apenas para GRD 'emitida' ou 'enviada'. NÃƒO cria rota/pÃ¡gina pÃºblica â€”
        o token fica disponÃ­vel para distribuiÃ§Ã£o por qualquer canal. A rota
        pÃºblica (FastAPI/Django) Ã© um block futuro (ver ADR 0004).
        """
        grd = self._repo.buscar_por_id(grd_id)
        if grd is None:
            return ResultadoGrd(False, grd_id=grd_id, mensagem="GRD nÃ£o encontrada.")
        if grd.get("status") not in ("emitida", "enviada"):
            return ResultadoGrd(
                False, grd_id=grd_id,
                mensagem="Token sÃ³ pode ser gerado para GRD emitida ou enviada.",
            )
        token = secrets.token_urlsafe(32)
        agora = self._agora()
        expira_em = agora + timedelta(days=GRD_TOKEN_TTL_DIAS)
        self._repo.salvar_token(
            grd_id,
            self._hash_token(token),
            self._iso(expira_em),
            self._iso(agora),
        )
        return ResultadoGrd(
            True,
            grd_id=grd_id,
            mensagem=token,
            dados={"token": token, "token_expira_em": self._iso(expira_em)},
        )

    def buscar_por_token(self, token: str) -> dict | None:
        """Busca de domÃ­nio por token â€” reutilizÃ¡vel por adapter futuro (FastAPI/Django)."""
        if not (token or "").strip():
            return None
        return self._repo.buscar_por_token(self._hash_token(token.strip()))

    def estado_token(self, token: str) -> dict:
        """Estado do token para adapter publico futuro, sem depender de Streamlit."""
        grd = self.buscar_por_token(token)
        if grd is None:
            return {"valido": False, "motivo": "Token invalido.", "grd": None}
        if grd.get("token_usado_em"):
            return {"valido": False, "motivo": "Este link ja foi utilizado.", "grd": grd}
        expira_em = self._parse_iso(grd.get("token_expira_em"))
        if expira_em is None or expira_em <= self._agora():
            return {"valido": False, "motivo": "Este link expirou.", "grd": grd}
        if grd.get("status") != "enviada":
            return {
                "valido": False,
                "motivo": "O recebimento por token so e permitido para GRD enviada.",
                "grd": grd,
            }
        return {"valido": True, "motivo": None, "grd": grd}

    def registrar_recebimento_por_token(
        self, token: str, recebido_por: str, recebido_cargo: str,
        declaracao: Optional[str] = None, recebido_em: Optional[str] = None,
    ) -> ResultadoGrd:
        """
        Registra o recebimento a partir do token (regra de domÃ­nio, sem HTTP).

        Esta funÃ§Ã£o existe para o futuro adapter pÃºblico (FastAPI/Django) chamar
        sem depender de Streamlit. NÃ£o hÃ¡ rota pÃºblica nesta etapa.
        """
        if not (recebido_por or "").strip() or not (recebido_cargo or "").strip():
            return ResultadoGrd(False, mensagem="Nome e cargo de quem recebeu sao obrigatorios.")
        estado = self.estado_token(token)
        if not estado["valido"]:
            grd = estado.get("grd") or {}
            return ResultadoGrd(False, grd_id=grd.get("id"), mensagem=estado["motivo"])
        grd = estado["grd"]
        quando = recebido_em or self._agora().date().isoformat()
        ok = self._repo.registrar_recebimento_por_token(
            grd["id"],
            recebido_por.strip(),
            recebido_cargo.strip(),
            (declaracao or "").strip() or None,
            quando,
            self._iso(self._agora()),
        )
        if not ok:
            return ResultadoGrd(
                False,
                grd_id=grd["id"],
                mensagem="Este link ja foi utilizado ou nao pode mais receber esta GRD.",
            )
        return ResultadoGrd(True, grd_id=grd["id"], mensagem="GRD agora esta 'recebida'.")

    # ------------------------------------------------------------------
    # Consulta
    # ------------------------------------------------------------------

    def listar_grds(self, contrato_id: int, filtros: Optional[dict] = None) -> list[dict]:
        return self._repo.listar_remessas(contrato_id, filtros)

    def buscar_grd(self, grd_id: int) -> dict | None:
        return self._repo.buscar_por_id(grd_id)

    def listar_itens(self, grd_id: int) -> list[dict]:
        return self._repo.listar_itens(grd_id)

    def listar_grds_por_revisao(self, revisao_ids) -> dict:
        """{revisao_id: [GRDs vinculadas]} â€” usa snapshot da GRD (pÃ¡gina Documento)."""
        return self._repo.listar_por_revisao(revisao_ids)

    # ------------------------------------------------------------------
    # ExportaÃ§Ã£o
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
