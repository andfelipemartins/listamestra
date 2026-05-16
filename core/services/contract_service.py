"""
core/services/contract_service.py

Regras de aplicacao relacionadas a contratos.

Nao depende de Streamlit. Estado de sessao e renderizacao permanecem em
app/session.py e nas paginas.
"""

from typing import Optional

from core.repositories.contract_repository import ContractRepository


class ContractService:
    def __init__(self, repository: Optional[ContractRepository] = None):
        self._repository = repository or ContractRepository()

    def verificar_banco(self) -> bool:
        return self._repository.verificar_banco()

    def listar_contratos_ativos(self) -> list[dict]:
        return self._repository.listar_contratos_ativos()

    def listar_contratos_com_metricas(self) -> list[dict]:
        contratos = self._repository.listar_contratos_ativos()
        for contrato in contratos:
            contrato.update(self._repository.obter_metricas_contrato(contrato["id"]))
        return contratos

    def validar_dados_contrato(self, nome: str, cliente: str = "") -> dict:
        dados = {
            "nome": (nome or "").strip(),
            "cliente": (cliente or "").strip(),
        }
        if not dados["nome"]:
            raise ValueError("O nome do contrato é obrigatório.")
        return dados

    def criar_contrato(self, nome: str, cliente: str = "") -> int:
        dados = self.validar_dados_contrato(nome, cliente)
        return self._repository.criar_contrato(dados["nome"], dados["cliente"])

    def obter_contrato_ativo(self, contrato_id: int | None = None) -> dict | None:
        if contrato_id is not None:
            return self._repository.obter_contrato_por_id(contrato_id)
        return self._repository.obter_primeiro_contrato_ativo()

