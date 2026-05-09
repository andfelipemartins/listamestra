"""
core/parsers/registry.py

Registro central de parsers de código documental.

Uso:
    from core.parsers.registry import ParserRegistry

    registry = ParserRegistry()
    resultado = registry.parse("DE-15.25.00.00-6A1-1001")
"""

from typing import Optional
from .base_parser import BaseParser, CodigoParseado, ErroDeparse
from .linha15_parser import Linha15Parser


class ParserRegistry:
    """
    Registro e seletor de parsers de código documental.

    Para registrar um novo parser de contrato:
        registry = ParserRegistry()
        registry.registrar(MeuNovoParser())
    """

    def __init__(self):
        self._parsers: dict[str, BaseParser] = {}
        self._registrar_parsers_padrão()

    def _registrar_parsers_padrão(self):
        self.registrar(Linha15Parser())

    def registrar(self, parser: BaseParser):
        self._parsers[parser.nome] = parser

    def parsers_disponiveis(self) -> list[str]:
        return list(self._parsers.keys())

    def get_parser(self, nome: str) -> Optional[BaseParser]:
        return self._parsers.get(nome)

    def detectar_parser(self, codigo: str) -> Optional[BaseParser]:
        for parser in self._parsers.values():
            if parser.aceita(codigo):
                return parser
        return None

    def parse(
        self,
        codigo: str,
        parser: Optional[str] = None,
    ) -> CodigoParseado | ErroDeparse:
        """
        Faz o parse de um código documental.

        Args:
            codigo: O código a ser interpretado (ex: 'DE-15.25.00.00-6A1-1001')
            parser: Nome do parser a usar. Se None, detecta automaticamente.
        """
        codigo = codigo.strip() if codigo else ""

        if not codigo:
            return ErroDeparse(
                codigo_original="",
                mensagem="Código vazio. Informe um código documental.",
            )

        if parser:
            p = self._parsers.get(parser)
            if p is None:
                return ErroDeparse(
                    codigo_original=codigo,
                    mensagem=(
                        f"Parser '{parser}' não encontrado. "
                        f"Parsers disponíveis: {', '.join(self.parsers_disponiveis())}"
                    ),
                )
            return p.parse(codigo)

        p = self.detectar_parser(codigo)
        if p is None:
            return ErroDeparse(
                codigo_original=codigo,
                mensagem=(
                    f"Nenhum parser reconheceu o código '{codigo}'. "
                    "Verifique se o formato está correto ou se o contrato "
                    "correspondente está registrado no sistema."
                ),
                detalhe=(
                    f"Parsers testados: {', '.join(self.parsers_disponiveis())}"
                ),
            )

        return p.parse(codigo)

    def parse_lote(
        self,
        codigos: list[str],
        parser: Optional[str] = None,
    ) -> dict[str, CodigoParseado | ErroDeparse]:
        """Parse de uma lista de códigos de uma só vez. Retorna {codigo: resultado}."""
        return {codigo: self.parse(codigo, parser=parser) for codigo in codigos}
