"""
core/parsers/linha15_parser.py

Parser para o padrão de código documental da Linha 15 — Metrô de São Paulo.

Formato:  TIPO-LINHA.TRECHO.SUBTRECHO.UNIDADE-ETAPACLS-SEQUENCIAL
Exemplo:  DE-15.25.00.00-6A1-1001
"""

import re
from .base_parser import BaseParser, CodigoParseado, ErroDeparse


_PATTERN = re.compile(
    r"^(?P<tipo>[A-Z]{2,4})"
    r"-"
    r"(?P<linha>\d{2})"
    r"\."
    r"(?P<trecho>\d{2})"
    r"\."
    r"(?P<subtrecho>\d{2})"
    r"\."
    r"(?P<unidade>\d{2})"
    r"-"
    r"(?P<etapa>\d)"
    r"(?P<classe>[A-Z])"
    r"(?P<subclasse>\d{1,2})"
    r"-"
    r"(?P<sequencial>\d{4})$",
    re.IGNORECASE,
)

_PREFIX_PATTERN = re.compile(r"^[A-Z]{2,4}-15\.", re.IGNORECASE)

_TIPOS_DOCUMENTAIS = {
    "DE":  "Desenho",
    "MC":  "Memorial de Cálculo",
    "MD":  "Memorial Descritivo",
    "RT":  "Relatório Técnico",
    "ID":  "Índice de Documentos",
    "IC":  "Instrução de Serviço / Construção",
    "PE":  "Procedimento Específico",
    "MQ":  "Manual da Qualidade / Plano de Gestão",
    "LM":  "Lista de Materiais",
    "NS":  "Notas de Serviço",
    "TC":  "Tabela de Coordenadas",
    "CQ":  "Controle de Qualidade",
    "EQ":  "Especificação de Qualidade",
    "AT":  "Anotação Técnica",
    "CR":  "Croqui",
    "EX":  "Documento Externo",
}

_NOMES_TRECHO = {
    "19": "Oratório",
    "23": "São Mateus",
    "25": "Ragueb Chohfi",
    "00": "Geral / Linha",
}

_CLASSES = {
    "A": "Gerenciamento / Diversos",
    "B": "Arquitetura e Sistemas",
    "C": "Geotecnia e Topografia",
    "D": "Utilidades e Interferências",
    "E": "Estruturas",
    "F": "Viário e Pavimentação",
    "G": "Hidráulica e Drenagem",
    "H": "Eletromecânico",
    "I": "Instalações",
}


class Linha15Parser(BaseParser):
    """Parser para códigos documentais do contrato Linha 15 — Metrô de SP."""

    @property
    def nome(self) -> str:
        return "linha15_metro_sp"

    @property
    def descricao(self) -> str:
        return "Linha 15 — Metrô de São Paulo"

    def tipos_documentais(self) -> dict:
        return dict(_TIPOS_DOCUMENTAIS)

    def aceita(self, codigo: str) -> bool:
        return bool(_PREFIX_PATTERN.match(codigo.strip()))

    def parse(self, codigo: str) -> CodigoParseado | ErroDeparse:
        codigo = codigo.strip()

        if not codigo:
            return ErroDeparse(
                codigo_original=codigo,
                mensagem="Código vazio. Informe um código documental válido.",
                parser_usado=self.nome,
            )

        match = _PATTERN.match(codigo.upper())

        if not match:
            return self._erro_formato(codigo)

        partes = match.groupdict()

        if partes["linha"] != "15":
            return ErroDeparse(
                codigo_original=codigo,
                mensagem=(
                    f"Linha inválida: '{partes['linha']}'. "
                    "Este parser é específico para a Linha 15 — Metrô de SP."
                ),
                parser_usado=self.nome,
            )

        tipo = partes["tipo"].upper()
        classe = partes["classe"].upper()
        trecho = partes["trecho"]

        descricao_tipo = _TIPOS_DOCUMENTAIS.get(tipo)
        if descricao_tipo is None:
            tipos_permitidos = ", ".join(sorted(_TIPOS_DOCUMENTAIS))
            return ErroDeparse(
                codigo_original=codigo,
                mensagem=(
                    f"Tipo documental '{tipo}' não está catalogado para este contrato. "
                    f"Tipos permitidos: {tipos_permitidos}."
                ),
                parser_usado=self.nome,
            )

        avisos = []

        descricao_classe = _CLASSES.get(classe, f"Classe não catalogada ({classe})")
        nome_trecho = _NOMES_TRECHO.get(trecho, f"Trecho {trecho}")

        identificador_base = (
            f"{tipo}-{partes['linha']}.{partes['trecho']}."
            f"{partes['subtrecho']}.{partes['unidade']}-"
            f"{partes['etapa']}{classe}{partes['subclasse']}-"
            f"{partes['sequencial']}"
        ).upper()

        return CodigoParseado(
            codigo_original=codigo,
            tipo=tipo,
            descricao_tipo=descricao_tipo,
            identificador_base=identificador_base,
            valido=True,
            parser_usado=self.nome,
            extras={
                "linha":            partes["linha"],
                "trecho":           trecho,
                "nome_trecho":      nome_trecho,
                "subtrecho":        partes["subtrecho"],
                "unidade":          partes["unidade"],
                "etapa":            partes["etapa"],
                "classe":           classe,
                "descricao_classe": descricao_classe,
                "subclasse":        partes["subclasse"],
                "sequencial":       partes["sequencial"],
                "avisos":           avisos,
            },
        )

    def _erro_formato(self, codigo: str) -> ErroDeparse:
        partes = codigo.upper().split("-")

        if len(partes) < 4:
            return ErroDeparse(
                codigo_original=codigo,
                mensagem=(
                    f"Formato inválido: '{codigo}'. "
                    "O código deve ter 4 segmentos separados por hífen. "
                    "Exemplo correto: DE-15.25.00.00-6A1-1001"
                ),
                detalhe=f"Segmentos encontrados: {len(partes)} (esperado: 4)",
                parser_usado=self.nome,
            )

        tipo = partes[0]
        if not re.match(r"^[A-Z]{2,4}$", tipo):
            return ErroDeparse(
                codigo_original=codigo,
                mensagem=(
                    f"Tipo documental inválido: '{tipo}'. "
                    "Deve conter 2 a 4 letras maiúsculas (ex: DE, MC, IC)."
                ),
                parser_usado=self.nome,
            )

        bloco_numerico = partes[1] if len(partes) > 1 else ""
        if not re.match(r"^\d{2}\.\d{2}\.\d{2}\.\d{2}$", bloco_numerico):
            return ErroDeparse(
                codigo_original=codigo,
                mensagem=(
                    f"Bloco numérico inválido: '{bloco_numerico}'. "
                    "Formato esperado: LINHA.TRECHO.SUBTRECHO.UNIDADE "
                    "(ex: 15.25.00.00)."
                ),
                parser_usado=self.nome,
            )

        return ErroDeparse(
            codigo_original=codigo,
            mensagem=(
                f"Código '{codigo}' não segue o padrão da Linha 15. "
                "Formato esperado: TIPO-LL.TT.SS.UU-ECLS-SSSS "
                "(ex: DE-15.25.00.00-6A1-1001)."
            ),
            detalhe=f"Regex não correspondeu: {_PATTERN.pattern}",
            parser_usado=self.nome,
        )
