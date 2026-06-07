"""
core/services/documento_service.py

Regras de aplicacao para consulta e enriquecimento de documentos.

Nao depende de Streamlit. Orquestra DocumentoRepository e RevisaoRepository.
"""

from typing import Optional

from core.engine.disciplinas import ESTRUTURA
from core.engine.status import NOME_TRECHO, classificar_status
from core.engine.document_lifecycle import (
    LinhaDocumental,
    analisar_linhas_documento,
    calcular_resultado_linha,
)
from core.formatacao import disciplina_do_codigo, filtrar_documentos
from core.parsers.registry import ParserRegistry
from core.repositories.documento_repository import DocumentoRepository
from core.repositories.revisao_repository import RevisaoRepository


class DocumentoService:
    def __init__(
        self,
        doc_repo: Optional[DocumentoRepository] = None,
        rev_repo: Optional[RevisaoRepository] = None,
    ):
        self._doc_repo = doc_repo or DocumentoRepository()
        self._rev_repo = rev_repo or RevisaoRepository()
        self._parser_registry = ParserRegistry()

    # ------------------------------------------------------------------
    # Busca básica
    # ------------------------------------------------------------------

    def buscar_documento_por_codigo(
        self, contrato_id: int, codigo: str
    ) -> dict | None:
        return self._doc_repo.buscar_por_codigo(contrato_id, codigo)

    def buscar_documento_por_id(self, documento_id: int) -> dict | None:
        return self._doc_repo.buscar_por_id(documento_id)

    def buscar_previsto(
        self, contrato_id: int, codigo: str
    ) -> dict | None:
        """Retorna dados do escopo previsto (ID) para o codigo, ou None."""
        return self._doc_repo.buscar_previsto(contrato_id, codigo)

    # ------------------------------------------------------------------
    # Revisões
    # ------------------------------------------------------------------

    def listar_revisoes_do_documento(self, documento_id: int) -> list[dict]:
        return self._rev_repo.listar_por_documento(documento_id)

    # ------------------------------------------------------------------
    # Ciclo documental (engine como fonte de verdade)
    # ------------------------------------------------------------------

    @staticmethod
    def _linha_documental_de_revisao(codigo: str, rev: dict) -> LinhaDocumental:
        """Converte um dict de revisao (tabela revisoes) em LinhaDocumental."""
        return LinhaDocumental(
            codigo=codigo,
            label_revisao=rev.get("label_revisao") or "0",
            versao=rev.get("versao") or 1,
            situacao=rev.get("situacao"),
            data_emissao=rev.get("data_emissao"),
            data_analise=rev.get("data_analise"),
            data_elaboracao=rev.get("data_elaboracao"),
            situacao_real=rev.get("situacao_real"),
            id=rev.get("id"),
            ordem=rev.get("id") or 0,
            ja_persistida=True,
        )

    def enriquecer_revisoes_com_resultado(
        self, codigo: str, revisoes: list[dict]
    ):
        """
        Enriquece cada revisao com 'resultado_linha' calculado pela engine.

        Muta os dicts em revisoes adicionando a chave 'resultado_linha' (label
        visual da revisao individual). Retorna o LifecycleResult da analise
        completa — fonte do status consolidado e de ja_aprovado.

        A regra de status fica inteiramente na engine; a pagina apenas exibe.
        """
        if not revisoes:
            return analisar_linhas_documento(codigo, [])

        linhas = [self._linha_documental_de_revisao(codigo, r) for r in revisoes]
        resultado = analisar_linhas_documento(codigo, linhas)

        por_id = {
            ll.linha.id: ll.resultado_linha
            for ll in resultado.linhas
            if ll.linha.id is not None
        }
        for rev in revisoes:
            rev["resultado_linha"] = por_id.get(
                rev.get("id"),
                calcular_resultado_linha(
                    rev.get("situacao"),
                    rev.get("data_emissao"),
                    rev.get("data_analise"),
                ),
            )
        return resultado

    # ------------------------------------------------------------------
    # Enriquecimento e fallback
    # ------------------------------------------------------------------

    def _trecho_do_codigo(self, codigo: str) -> str:
        try:
            resultado = self._parser_registry.parse(codigo)
            if hasattr(resultado, "extras"):
                return resultado.extras.get("trecho", "")
        except Exception:
            pass
        return ""

    def enriquecer_documento(
        self, doc: dict, previsto: Optional[dict] = None
    ) -> dict:
        """Adiciona campos de exibicao a uma copia do dict do documento.

        Campos adicionados: nome_trecho, disciplina_display, disciplina_desc,
        status_atual. Recebe previsto opcionalmente para uso futuro.
        """
        doc = dict(doc)
        trecho = doc.get("trecho") or ""
        doc["nome_trecho"] = NOME_TRECHO.get(trecho, trecho)

        disc = (
            doc.get("disciplina")
            or disciplina_do_codigo(doc.get("codigo", ""))
            or ""
        )
        doc["disciplina_display"] = disc
        doc["disciplina_desc"] = ESTRUTURA.get(disc, "")
        doc["status_atual"] = classificar_status(
            doc.get("situacao"), doc.get("data_emissao")
        )
        return doc

    def obter_titulo_exibicao(
        self, doc: dict, previsto: Optional[dict] = None
    ) -> str:
        """Titulo do documento com fallback para o titulo do ID previsto."""
        return (
            doc.get("titulo")
            or (previsto.get("titulo") if previsto else None)
            or ""
        )

    def obter_trecho_exibicao(
        self, doc: dict, previsto: Optional[dict] = None
    ) -> str:
        """String de exibicao do trecho com fallback: doc → previsto → parser.

        Retorna string no formato 'Nome (codigo)' ou vazio se indisponivel.
        """
        codigo = (
            doc.get("trecho")
            or (previsto.get("trecho") if previsto else None)
            or self._trecho_do_codigo(doc.get("codigo", ""))
            or ""
        )
        if not codigo:
            return ""
        nome = NOME_TRECHO.get(codigo, codigo)
        return f"{nome} ({codigo})"

    def obter_disciplina_exibicao(
        self, doc: dict, previsto: Optional[dict] = None
    ) -> str:
        """String de exibicao da estrutura/disciplina com fallback: doc → previsto → parser.

        Retorna 'CODIGO — Descricao' ou apenas 'CODIGO' ou vazio se indisponivel.
        """
        codigo = (
            doc.get("disciplina")
            or (previsto.get("disciplina") if previsto else None)
            or disciplina_do_codigo(doc.get("codigo", ""))
            or ""
        )
        if not codigo:
            return ""
        descricao = ESTRUTURA.get(codigo, "")
        if descricao:
            return f"{codigo} — {descricao}"
        return codigo

    def montar_resumo_documento(self, doc: dict) -> dict:
        """Dict de campos de exibicao prontos para a tabela de busca.

        Pressupoe doc ja enriquecido por enriquecer_documento().
        """
        return {
            "id": doc["id"],
            "codigo": doc["codigo"],
            "tipo": doc.get("tipo") or "—",
            "nome_trecho": doc.get("nome_trecho") or doc.get("trecho") or "—",
            "disciplina_display": doc.get("disciplina_display") or "—",
            "status_atual": doc.get("status_atual") or "—",
            "titulo": doc.get("titulo") or "(sem título)",
        }

    # ------------------------------------------------------------------
    # Listagens
    # ------------------------------------------------------------------

    def listar_documentos_enriquecidos(self, contrato_id: int) -> list[dict]:
        """Documentos do contrato enriquecidos com campos de exibicao."""
        docs = self._doc_repo.listar_com_ultima_revisao(contrato_id)
        return [self.enriquecer_documento(doc) for doc in docs]

    def buscar_documentos_para_consulta(
        self,
        contrato_id: int,
        filtros: Optional[str] = None,
    ) -> list[dict]:
        """Documentos enriquecidos com filtro de texto opcional."""
        docs = self.listar_documentos_enriquecidos(contrato_id)
        if filtros:
            docs = filtrar_documentos(docs, filtros)
        return docs

    # ------------------------------------------------------------------
    # Detalhe
    # ------------------------------------------------------------------

    def carregar_detalhe_documento(self, documento_id: int) -> Optional[dict]:
        """Documento com revisoes e status atual resolvido pela engine.

        Retorna None se nao existir. Estrutura do retorno:
          documento      — dict bruto da tabela documentos
          revisoes       — lista ordenada da tabela revisoes, cada uma enriquecida
                           com 'resultado_linha' (label visual da revisao)
          ultima_revisao — dict da revisao marcada ultima_revisao=1, ou None
          status_atual   — status consolidado do documento (DocumentLifecycleEngine)
          ja_aprovado    — True se ha aprovacao historica em alguma revisao

        O status consolidado e o resultado de cada linha vem da engine de ciclo
        documental — fonte unica de verdade. classificar_status() (legado) nao
        e mais usado aqui.
        """
        doc = self._doc_repo.buscar_por_id(documento_id)
        if doc is None:
            return None
        revisoes = self._rev_repo.listar_por_documento(documento_id)
        ultima = next((r for r in revisoes if r.get("ultima_revisao")), None)

        lifecycle = self.enriquecer_revisoes_com_resultado(doc["codigo"], revisoes)

        return {
            "documento": doc,
            "revisoes": revisoes,
            "ultima_revisao": ultima,
            "status_atual": lifecycle.status_atual,
            "ja_aprovado": lifecycle.ja_aprovado,
        }
