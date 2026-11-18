"""Classificação e resumo de situações para o painel configurado no perfil."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable, Mapping

from .ciclo import _normalizar_situacao
from .modelo import Grupo, PerfilContrato


_GRUPO_NAO_MAPEADO = Grupo(id="nao_mapeado", rotulo="NÃO MAPEADO")
_GRUPO_IGNORADO = Grupo(id="ignorado", rotulo="IGNORADO", conta_no_avanco=False)


@dataclass(frozen=True)
class EstadoNaoMapeado:
    situacao: str
    contagem: int


@dataclass(frozen=True)
class ResumoPainel:
    grupos: tuple[Grupo, ...]
    contagens: Mapping[str, int]
    total_previsto: int
    percentual_avanco: float
    estados_nao_mapeados: tuple[EstadoNaoMapeado, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "grupos", tuple(self.grupos))
        object.__setattr__(self, "contagens", MappingProxyType(dict(self.contagens)))
        object.__setattr__(self, "estados_nao_mapeados", tuple(self.estados_nao_mapeados))


def classificar(perfil: PerfilContrato, situacao_vigente: str | None) -> Grupo:
    """Retorna o grupo configurado, A EMITIR, IGNORADO ou NÃO MAPEADO."""
    if situacao_vigente is None:
        return next(grupo for grupo in perfil.painel.grupos if grupo.sem_emissao)

    chave = _normalizar_situacao(situacao_vigente)
    ignoradas = {_normalizar_situacao(estado) for estado in perfil.painel.ignorar}
    if chave in ignoradas:
        return _GRUPO_IGNORADO

    for grupo in perfil.painel.grupos:
        if any(_normalizar_situacao(estado) == chave for estado in grupo.estados):
            return grupo
    return _GRUPO_NAO_MAPEADO


def resumir(
    perfil: PerfilContrato, situacoes: Iterable[str | None]
) -> ResumoPainel:
    """Conta situações e calcula o avanço sobre o escopo elegível do painel."""
    contagens = {grupo.id: 0 for grupo in perfil.painel.grupos}
    contagens[_GRUPO_NAO_MAPEADO.id] = 0
    estados_sem_mapeamento: dict[str, tuple[str, int]] = {}
    total = 0

    for situacao in situacoes:
        grupo = classificar(perfil, situacao)
        if grupo.id == _GRUPO_IGNORADO.id:
            continue
        total += 1
        contagens[grupo.id] += 1
        if grupo.id == _GRUPO_NAO_MAPEADO.id:
            texto = "" if situacao is None else situacao.strip()
            chave = _normalizar_situacao(texto)
            anterior = estados_sem_mapeamento.get(chave)
            estados_sem_mapeamento[chave] = (
                texto if anterior is None else anterior[0],
                1 if anterior is None else anterior[1] + 1,
            )

    grupos = (*perfil.painel.grupos, _GRUPO_NAO_MAPEADO)
    ids_avanco = {identificador.casefold() for identificador in perfil.painel.avanco}
    ids_nao_contam = {
        grupo.id.casefold()
        for grupo in perfil.painel.grupos
        if not grupo.conta_no_avanco
    }
    numerador = sum(
        quantidade
        for identificador, quantidade in contagens.items()
        if identificador.casefold() in ids_avanco
    )
    denominador = total - sum(
        quantidade
        for identificador, quantidade in contagens.items()
        if identificador.casefold() in ids_nao_contam
    )
    percentual = 100.0 * numerador / denominador if denominador else 0.0
    nao_mapeados = tuple(
        EstadoNaoMapeado(situacao=texto, contagem=quantidade)
        for texto, quantidade in estados_sem_mapeamento.values()
    )
    return ResumoPainel(
        grupos=grupos,
        contagens=contagens,
        total_previsto=total,
        percentual_avanco=percentual,
        estados_nao_mapeados=nao_mapeados,
    )
