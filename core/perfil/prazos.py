"""Cálculos puros de vencimento e cumprimento de prazos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class AvaliacaoPrazo:
    situacao: str
    vencimento: date
    dias_atraso: int


@dataclass(frozen=True)
class ResultadoIndicadorPrazo:
    percentual_cumprido: float
    dentro: int
    fora: int
    base: int


def vencimento(
    inicio: date,
    dias: int,
    tipo_dia: str,
    feriados: Iterable[date] = (),
) -> date:
    """Calcula a data limite; a contagem começa no dia seguinte ao início."""
    if not isinstance(inicio, date):
        raise TypeError("'inicio' precisa ser uma data.")
    if isinstance(dias, bool) or not isinstance(dias, int) or dias < 0:
        raise ValueError("'dias' precisa ser inteiro não negativo.")
    if tipo_dia not in {"uteis", "corridos"}:
        raise ValueError("'tipo_dia' precisa ser 'uteis' ou 'corridos'.")
    datas_feriadas = set(feriados)
    if any(not isinstance(data, date) for data in datas_feriadas):
        raise TypeError("'feriados' deve conter somente datas.")
    if tipo_dia == "corridos":
        return inicio + timedelta(days=dias)

    atual = inicio
    contados = 0
    while contados < dias:
        atual += timedelta(days=1)
        if atual.weekday() < 5 and atual not in datas_feriadas:
            contados += 1
    return atual


def avaliar(
    regra: Any,
    data_inicio: date,
    data_fim: date | None,
    hoje: date,
    *,
    sigla: str | None = None,
    grupo: str | None = None,
    feriados: Iterable[date] = (),
) -> AvaliacaoPrazo | None:
    """Avalia prazo concluído ou em aberto; regras filtradas por grupo retornam None."""
    grupos = _valor(regra, "so_quando_grupo", ()) or ()
    if grupos and (grupo is None or grupo.casefold() not in {str(item).casefold() for item in grupos}):
        return None

    dias = _dias_da_regra(regra, sigla)
    tipo_dia = _valor(regra, "tipo_dia")
    limite = vencimento(data_inicio, dias, tipo_dia, feriados)
    if data_fim is not None:
        if not isinstance(data_fim, date):
            raise TypeError("'data_fim' precisa ser uma data ou None.")
        if data_fim <= limite:
            return AvaliacaoPrazo("no_prazo", limite, 0)
        return AvaliacaoPrazo("atrasado", limite, (data_fim - limite).days)
    if not isinstance(hoje, date):
        raise TypeError("'hoje' precisa ser uma data.")
    if hoje <= limite:
        return AvaliacaoPrazo("aberto_no_prazo", limite, 0)
    return AvaliacaoPrazo("aberto_atrasado", limite, (hoje - limite).days)


def indicador(avaliacoes: Iterable[AvaliacaoPrazo | Mapping[str, Any] | None]) -> ResultadoIndicadorPrazo:
    """Conta concluídos e abertos vencidos; abertos ainda no prazo ficam fora da base."""
    dentro = 0
    fora = 0
    for avaliacao in avaliacoes:
        if avaliacao is None:
            continue
        situacao = _valor(avaliacao, "situacao")
        if situacao == "no_prazo":
            dentro += 1
        elif situacao in {"atrasado", "aberto_atrasado"}:
            fora += 1
        elif situacao != "aberto_no_prazo":
            raise ValueError(f"Situação de prazo desconhecida: {situacao!r}.")
    base = dentro + fora
    percentual = dentro * 100.0 / base if base else 0.0
    return ResultadoIndicadorPrazo(percentual, dentro, fora, base)


def _dias_da_regra(regra: Any, sigla: str | None) -> int:
    dias = _valor(regra, "dias")
    if sigla is None:
        return dias
    for excecao in _valor(regra, "excecoes", ()) or ():
        siglas = _valor(excecao, "siglas", ()) or ()
        if sigla.casefold() in {str(valor).casefold() for valor in siglas}:
            return _valor(excecao, "dias")
    return dias


def _valor(objeto: Any, nome: str, padrao: Any = None) -> Any:
    if isinstance(objeto, Mapping):
        return objeto.get(nome, padrao)
    return getattr(objeto, nome, padrao)
