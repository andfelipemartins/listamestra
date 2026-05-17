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

LINHA15_CAMPOS_OBRIGATORIOS: tuple[str, ...] = (
    "tipo",
    "linha",
    "trecho",
    "subtrecho",
    "unidade",
    "etapa",
    "classe",
    "subclasse",
    "sequencial",
)


def _texto(val) -> str:
    return str(val or "").strip()


def _numero_com_zeros(val, tamanho: int) -> str:
    texto = _texto(val)
    return texto.zfill(tamanho) if texto else ""


def normalizar_partes_linha15(partes: dict) -> dict:
    """Normaliza partes de um codigo Linha 15 preservando zeros a esquerda."""
    return {
        "tipo": _texto(partes.get("tipo")).upper(),
        "linha": _numero_com_zeros(partes.get("linha"), 2),
        "trecho": _numero_com_zeros(partes.get("trecho"), 2),
        "subtrecho": _numero_com_zeros(partes.get("subtrecho"), 2),
        "unidade": _numero_com_zeros(partes.get("unidade"), 2),
        "etapa": _texto(partes.get("etapa")),
        "classe": _texto(partes.get("classe")).upper(),
        "subclasse": _texto(partes.get("subclasse")),
        "sequencial": _numero_com_zeros(partes.get("sequencial"), 4),
    }


def validar_partes_linha15(partes: dict) -> list[str]:
    """Retorna erros de preenchimento basico das partes do codigo."""
    normalizadas = normalizar_partes_linha15(partes)
    erros: list[str] = []

    nomes = {
        "tipo": "Tipo/Sigla",
        "linha": "Linha",
        "trecho": "Trecho",
        "subtrecho": "Subtrecho",
        "unidade": "Unidade",
        "etapa": "Etapa",
        "classe": "Classe",
        "subclasse": "Subclasse",
        "sequencial": "Sequencial",
    }

    for campo in LINHA15_CAMPOS_OBRIGATORIOS:
        if not normalizadas[campo]:
            erros.append(f"{nomes[campo]} e obrigatorio.")

    checks = (
        ("linha", 2),
        ("trecho", 2),
        ("subtrecho", 2),
        ("unidade", 2),
        ("sequencial", 4),
    )
    for campo, tamanho in checks:
        valor = normalizadas[campo]
        if valor and (not valor.isdigit() or len(valor) != tamanho):
            erros.append(f"{nomes[campo]} deve ter {tamanho} digito(s).")

    if normalizadas["etapa"] and (
        not normalizadas["etapa"].isdigit() or len(normalizadas["etapa"]) != 1
    ):
        erros.append("Etapa deve ter 1 digito.")

    if normalizadas["classe"] and (
        not normalizadas["classe"].isalpha() or len(normalizadas["classe"]) != 1
    ):
        erros.append("Classe deve ter 1 letra.")

    if normalizadas["subclasse"] and (
        not normalizadas["subclasse"].isdigit() or len(normalizadas["subclasse"]) > 2
    ):
        erros.append("Subclasse deve ter 1 ou 2 digito(s).")

    return erros


def montar_codigo_linha15(
    tipo: str,
    trecho: str,
    subtrecho: str,
    unidade: str,
    etapa: str,
    classe: str,
    subclasse: str,
    sequencial: str,
    linha: str = "15",
) -> str:
    """
    Monta o código documental padrão Linha 15 a partir das partes individuais.
    Não valida entradas — a UI garante os campos antes de chamar.
    """
    partes = normalizar_partes_linha15({
        "tipo": tipo,
        "linha": linha,
        "trecho": trecho,
        "subtrecho": subtrecho,
        "unidade": unidade,
        "etapa": etapa,
        "classe": classe,
        "subclasse": subclasse,
        "sequencial": sequencial,
    })
    return (
        f"{partes['tipo']}-{partes['linha']}.{partes['trecho']}."
        f"{partes['subtrecho']}.{partes['unidade']}-"
        f"{partes['etapa']}{partes['classe']}{partes['subclasse']}-"
        f"{partes['sequencial']}"
    )


def montar_codigo_segmentado_linha15(partes: dict) -> str:
    """Valida e monta um codigo Linha 15 a partir de um dict de partes."""
    erros = validar_partes_linha15(partes)
    if erros:
        raise ValueError("; ".join(erros))
    normalizadas = normalizar_partes_linha15(partes)
    return montar_codigo_linha15(**normalizadas)


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


def mesclar_codigos(novos: list, existentes: list) -> tuple[list, int]:
    """
    Adiciona apenas os códigos de *novos* que ainda não estão em *existentes*.
    Retorna (lista_final, num_duplicatas_ignoradas).
    A ordem dos existentes é preservada; novos são adicionados ao final.
    """
    existentes_set = {c for c, _ in existentes}
    resultado = list(existentes)
    duplicatas = 0
    for codigo, parsed in novos:
        if codigo in existentes_set:
            duplicatas += 1
        else:
            resultado.append((codigo, parsed))
            existentes_set.add(codigo)
    return resultado, duplicatas


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
        "linha":      e.get("linha", "15"),
        "trecho":     e.get("trecho", "00"),
        "subtrecho":  e.get("subtrecho", "00"),
        "unidade":    e.get("unidade", "00"),
        "etapa":      e.get("etapa", "6"),
        "classe":     e.get("classe", "A"),
        "subclasse":  e.get("subclasse", "1"),
        "sequencial": e.get("sequencial", "0001"),
    }
