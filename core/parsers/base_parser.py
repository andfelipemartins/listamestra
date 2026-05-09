"""
core/parsers/base_parser.py

Define a interface (classe abstrata) que todos os parsers de código
documental devem implementar. Isso garante que parsers de contratos
diferentes sejam intercambiáveis no sistema.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CodigoParseado:
    """
    Resultado de um parse bem-sucedido.

    Campos comuns a qualquer contrato. Campos específicos de cada contrato
    ficam em 'extras' para não poluir a interface base.
    """
    codigo_original: str          # Código exatamente como veio da fonte
    tipo: str                     # Tipo documental (DE, MC, MD, RT, ...)
    descricao_tipo: str           # Descrição legível do tipo
    identificador_base: str       # Parte do código que identifica o documento
                                  # sem revisão/versão (chave de agrupamento)
    valido: bool = True
    parser_usado: str = ""        # Nome do parser que gerou este resultado
    extras: dict = field(default_factory=dict)  # Campos específicos do contrato


@dataclass
class ErroDeparse:
    """
    Resultado de um parse que falhou.
    Retorna mensagem amigável para o usuário e detalhes técnicos.
    """
    codigo_original: str
    mensagem: str                 # Mensagem legível para o usuário
    detalhe: Optional[str] = None # Detalhe técnico (regex, campo inválido, etc.)
    parser_usado: str = ""
    valido: bool = False


class BaseParser(ABC):
    """
    Interface que todos os parsers de código documental devem implementar.

    Para adicionar suporte a um novo contrato, crie uma subclasse desta
    classe e implemente os métodos abstratos.
    """

    @property
    @abstractmethod
    def nome(self) -> str:
        """Identificador único do parser (ex: 'linha15_metro_sp')."""

    @property
    @abstractmethod
    def descricao(self) -> str:
        """Descrição humana do parser (ex: 'Linha 15 - Metrô de São Paulo')."""

    @abstractmethod
    def aceita(self, codigo: str) -> bool:
        """
        Verifica rapidamente se o código provavelmente segue o padrão
        deste parser — sem fazer o parse completo.
        """

    @abstractmethod
    def parse(self, codigo: str) -> "CodigoParseado | ErroDeparse":
        """
        Faz o parse completo do código.

        Retorna CodigoParseado em caso de sucesso,
        ou ErroDeparse com mensagem amigável em caso de falha.
        """

    @abstractmethod
    def tipos_documentais(self) -> dict:
        """
        Retorna o dicionário de tipos documentais conhecidos por este parser.
        Chave: sigla (ex: 'DE'). Valor: descrição (ex: 'Desenho').
        """
