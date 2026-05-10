"""
core/parsers/codigo_builder.py

Montagem e desmontagem de códigos documentais da Linha 15 — Metrô SP.
Expõe constantes públicas para a UI usar diretamente nos selectboxes.
"""

from typing import Optional

LINHA15_TIPOS: dict[str, str] = {
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
    # EX (Documento Externo) não integra a Lista Mestra Principal.
}

LINHA15_TRECHOS: dict[str, str] = {
    "00": "Geral / Linha",
    "19": "Oratório",
    "23": "São Mateus",
    "25": "Ragueb Chohfi",
}

LINHA15_CLASSES: dict[str, str] = {
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


def montar_codigo_linha15(
    tipo: str,
    trecho: str,
    subtrecho: str,
    unidade: str,
    etapa: str,
    classe: str,
    subclasse: str,
    sequencial: str,
) -> str:
    """
    Monta o código documental padrão Linha 15 a partir das partes individuais.
    Não valida entradas — a UI garante os campos antes de chamar.
    """
    t   = str(trecho).zfill(2)
    s   = str(subtrecho).zfill(2)
    u   = str(unidade).zfill(2)
    seq = str(sequencial).zfill(4)
    return f"{tipo.upper()}-15.{t}.{s}.{u}-{etapa}{classe.upper()}{subclasse}-{seq}"


def parsear_lista_codigos(texto: str, registry) -> tuple[list, list]:
    """
    Recebe texto com um ou mais códigos (um por linha).
    Retorna (validos, invalidos):
    - validos:  list of (codigo_str, CodigoParseado)
    - invalidos: list of (codigo_str, ErroDeparse)
    Ignora linhas vazias e normaliza espaços extras.
    """
    linhas = [l.strip().upper() for l in texto.splitlines() if l.strip()]
    validos, invalidos = [], []
    for codigo in linhas:
        r = registry.parse(codigo)
        if r.valido:
            validos.append((codigo, r))
        else:
            invalidos.append((codigo, r))
    return validos, invalidos


def desmontar_codigo_linha15(codigo: str, registry) -> Optional[dict]:
    """
    Desmonta um código Linha 15 em suas partes usando o registry de parsers.
    Retorna None se o código for inválido.
    """
    parsed = registry.parse(codigo)
    if not parsed.valido:
        return None
    e = parsed.extras
    return {
        "tipo":       parsed.tipo,
        "trecho":     e.get("trecho", "00"),
        "subtrecho":  e.get("subtrecho", "00"),
        "unidade":    e.get("unidade", "00"),
        "etapa":      e.get("etapa", "6"),
        "classe":     e.get("classe", "A"),
        "subclasse":  e.get("subclasse", "1"),
        "sequencial": e.get("sequencial", "0001"),
    }
