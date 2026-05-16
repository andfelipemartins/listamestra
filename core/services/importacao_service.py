"""
core/services/importacao_service.py

Regras de aplicacao relacionadas a importacoes.

Nao depende de Streamlit. Estado de sessao, upload e renderizacao permanecem
nas paginas.
"""

from typing import Optional

from core.repositories.importacao_repository import ImportacaoRepository


class ImportacaoService:
    def __init__(self, repository: Optional[ImportacaoRepository] = None):
        self._repository = repository or ImportacaoRepository()

    def validar_dados_importacao(
        self,
        contrato_id: int,
        origem: str,
        arquivo_importado: str,
        total_registros: int = 0,
        status: str = "em_andamento",
        usuario: str | None = None,
    ) -> dict:
        try:
            contrato_id_int = int(contrato_id)
        except (TypeError, ValueError):
            contrato_id_int = 0

        try:
            total_registros_int = int(total_registros or 0)
        except (TypeError, ValueError):
            total_registros_int = -1

        dados = {
            "contrato_id": contrato_id_int,
            "origem": (origem or "").strip(),
            "arquivo_importado": (arquivo_importado or "").strip(),
            "total_registros": total_registros_int,
            "status": (status or "").strip(),
            "usuario": (usuario or "").strip() or None,
        }

        if dados["contrato_id"] <= 0:
            raise ValueError("O contrato da importacao e obrigatorio.")
        if not dados["origem"]:
            raise ValueError("A origem da importacao e obrigatoria.")
        if dados["total_registros"] < 0:
            raise ValueError("O total de registros nao pode ser negativo.")
        if not dados["status"]:
            raise ValueError("O status da importacao e obrigatorio.")

        return dados

    def listar_historico_importacoes(self, contrato_id: int, limite: int = 10) -> list[dict]:
        return self._repository.listar_historico_importacoes(contrato_id, limite)

    def obter_ultima_importacao(self, contrato_id: int) -> dict | None:
        return self._repository.obter_ultima_importacao(contrato_id)

    def obter_resumo_importacoes(self, contrato_id: int) -> dict:
        return {
            "total": self._repository.contar_importacoes(contrato_id),
            "ultima": self.obter_ultima_importacao(contrato_id),
            "historico": self.listar_historico_importacoes(contrato_id),
        }

    def registrar_importacao(
        self,
        contrato_id: int,
        origem: str,
        arquivo_importado: str,
        total_registros: int = 0,
        status: str = "em_andamento",
        usuario: str | None = None,
        conn=None,
    ) -> int:
        dados = self.validar_dados_importacao(
            contrato_id,
            origem,
            arquivo_importado,
            total_registros,
            status,
            usuario,
        )
        return self._repository.registrar_importacao(conn=conn, **dados)

    def finalizar_importacao(
        self,
        importacao_id: int,
        total_erros: int,
        total_novos: int,
        total_atualizados: int,
        status: str = "concluido",
        conn=None,
    ) -> None:
        self._repository.finalizar_importacao(
            importacao_id=importacao_id,
            total_erros=total_erros,
            total_novos=total_novos,
            total_atualizados=total_atualizados,
            status=status,
            conn=conn,
        )
