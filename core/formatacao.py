"""
core/formatacao.py

Helpers de formatação de valores para exibição nas páginas Streamlit.
Funções puras testáveis em isolamento.
"""

import unicodedata

_CAMPOS_BUSCA_PADRAO = [
    "codigo", "titulo", "tipo", "trecho", "nome_trecho",
    "modalidade", "disciplina_display", "disciplina_desc",
]

_registry_singleton = None


def _get_registry():
    global _registry_singleton
    if _registry_singleton is None:
        from core.parsers.registry import ParserRegistry
        _registry_singleton = ParserRegistry()
    return _registry_singleton


def fmt_inteiro(val) -> str:
    """Converte valores numéricos com decimal desnecessário (ex: 1.0 → '1').

    Cobre o caso comum em que o pandas/SQLite retorna um campo inteiro como
    float (fase=1.0, revisao=2.0, etc.).
    """
    if val is None:
        return "—"
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return "—"
    try:
        f = float(s)
        if f == int(f):
            return str(int(f))
        return s
    except (ValueError, TypeError):
        return s or "—"


def fmt_data(val) -> str:
    """Remove horário zerado de strings de data (ex: '2025-06-09 00:00:00' → '2025-06-09').

    Preserva valores que já são apenas datas ou que contêm hora significativa.
    """
    if not val:
        return "—"
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return "—"
    if " 00:00:00" in s:
        s = s.replace(" 00:00:00", "")
    return s or "—"


def normalizar_busca(texto: str) -> str:
    """Remove acentos e converte para minúsculas para busca insensível a acentuação.

    Exemplo: 'ORATÓRIO' → 'oratorio', 'São Mateus' → 'sao mateus'.
    """
    return (
        unicodedata.normalize("NFD", str(texto).lower())
        .encode("ascii", "ignore")
        .decode()
    )


def filtrar_documentos(
    docs: list[dict],
    termo: str,
    campos: list[str] | None = None,
) -> list[dict]:
    """Retorna documentos cujos campos contêm o termo de busca.

    Busca case-insensitive, ignorando acentos.
    Termos com múltiplas palavras usam semântica AND: todos os fragmentos
    devem aparecer (em qualquer campo) para o documento ser incluído.
    Se termo estiver vazio, retorna todos os documentos sem filtrar.
    """
    if not termo.strip():
        return docs
    palavras = [normalizar_busca(p) for p in termo.split() if p.strip()]
    campos_efetivos = campos if campos is not None else _CAMPOS_BUSCA_PADRAO
    return [
        doc for doc in docs
        if all(
            any(p in normalizar_busca(doc.get(c) or "") for c in campos_efetivos)
            for p in palavras
        )
    ]


def disciplina_do_codigo(codigo: str) -> str:
    """Deriva o código de estrutura (classe + subclasse) a partir do código documental.

    Exemplo: 'DE-15.23.17.84-6B3-1004' → 'B3'
    Retorna string vazia se o código não puder ser parseado.
    """
    try:
        resultado = _get_registry().parse(codigo)
        if hasattr(resultado, "extras"):
            classe = resultado.extras.get("classe", "")
            subclasse = resultado.extras.get("subclasse", "")
            if classe and subclasse:
                return f"{classe}{subclasse}"
    except Exception:
        pass
    return ""
