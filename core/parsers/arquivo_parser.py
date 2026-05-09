"""
core/parsers/arquivo_parser.py

Parseia nomes de arquivo de documentos técnicos da Linha 15 — Metrô SP.

Formato novo  (com versão):  CODIGO-REVISAO-VERSAO.ext
Formato antigo (sem versão): CODIGO-REVISAO.ext

REVISAO pode ser:
  - Numérico pré-aprovação : 1, 2, 3...
  - Numérico aprovado      : 0
  - Letra sub-revisão      : A1, A2, B1...
  - Letra aprovado         : A, B, C...
"""

import os
import re
from dataclasses import dataclass
from typing import Optional, Union

# Código: TIPO-15.TRECHO.SUBTRECHO.UNIDADE-ETAPACLS-SEQUENCIAL
# Após o código: -REVISAO[-VERSAO].ext
_PATTERN = re.compile(
    r'^([A-Z]{2,4}-15\.\d{2}\.\d{2}\.\d{2}-\d[A-Z]\d{1,2}-\d{4})'
    r'-(0|[1-9]\d*|[A-Z]\d*)'
    r'(?:-(\d+))?'
    r'\.([^./\\]+)$',
    re.IGNORECASE,
)


@dataclass
class ArquivoParseado:
    nome_arquivo:  str            # só o nome, sem path
    codigo:        str            # código do documento (maiúsculas)
    label_revisao: str            # "1", "0", "A1", "A" etc.
    versao:        Optional[int]  # None = formato antigo (sem versão no nome)
    extensao:      str            # minúsculas: "pdf", "dwg"


@dataclass
class ErroParsearArquivo:
    nome_arquivo: str
    motivo:       str


def parsear_arquivo(linha: str) -> Union[ArquivoParseado, ErroParsearArquivo]:
    """
    Parseia uma linha de nomes.txt.

    Aceita tanto nome puro ('DE-15.25.00.00-6A1-1001-1-1.pdf')
    quanto caminho completo ('C:\\...\\DE-15.25.00.00-6A1-1001-1-1.pdf').
    """
    nome = os.path.basename(linha.strip())
    if not nome:
        return ErroParsearArquivo(linha.strip(), "linha vazia ou apenas caminho de pasta")

    m = _PATTERN.match(nome)
    if not m:
        return ErroParsearArquivo(nome, "nome não segue o padrão CODIGO-REVISAO[-VERSAO].ext")

    codigo, label_revisao, versao_str, ext = m.groups()
    return ArquivoParseado(
        nome_arquivo=nome,
        codigo=codigo.upper(),
        label_revisao=label_revisao,
        versao=int(versao_str) if versao_str else None,
        extensao=ext.lower(),
    )
