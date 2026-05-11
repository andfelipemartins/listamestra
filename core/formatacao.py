"""
core/formatacao.py

Helpers de formatação de valores para exibição nas páginas Streamlit.
Funções puras testáveis em isolamento.
"""


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


def disciplina_do_codigo(codigo: str) -> str:
    """Deriva o código de estrutura (classe + subclasse) a partir do código documental.

    Exemplo: 'DE-15.23.17.84-6B3-1004' → 'B3'
    Retorna string vazia se o código não puder ser parseado.
    """
    try:
        from core.parsers.registry import ParserRegistry
        resultado = ParserRegistry().parse(codigo)
        if hasattr(resultado, "extras"):
            classe = resultado.extras.get("classe", "")
            subclasse = resultado.extras.get("subclasse", "")
            if classe and subclasse:
                return f"{classe}{subclasse}"
    except Exception:
        pass
    return ""
