"""Cálculos puros dos indicadores declarados no perfil do contrato."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .ciclo import _normalizar_situacao
from .modelo import IndicadorAprovacao, PerfilContrato
from .painel import classificar
from .series import criar_serie


@dataclass(frozen=True)
class EmissaoIndicador:
    fase: str
    revisao: str
    situacao: str | None


@dataclass(frozen=True)
class DocumentoIndicador:
    grupo_id: str
    situacao: str | None
    emissoes: tuple[EmissaoIndicador, ...]
    recorte: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "emissoes", tuple(self.emissoes))


@dataclass(frozen=True)
class ResultadoContagemIndicador:
    dentro_limite: int
    fora_limite: int

    @property
    def base(self) -> int:
        return self.dentro_limite + self.fora_limite

    @property
    def percentual(self) -> float | None:
        if not self.base:
            return None
        return 100 * self.dentro_limite / self.base


@dataclass(frozen=True)
class ResultadoIndicadorAprovacao:
    geral: ResultadoContagemIndicador
    por_recorte: Mapping[str, ResultadoContagemIndicador]


def calcular_indicador_aprovacao(
    perfil: PerfilContrato,
    indicador: IndicadorAprovacao,
    documentos: Iterable[DocumentoIndicador],
) -> ResultadoIndicadorAprovacao:
    """Calcula o percentual do primeiro ciclo e as mesmas métricas por recorte."""
    ids_avanco = {identificador.casefold() for identificador in perfil.painel.avanco}
    grupos = {grupo.id.casefold(): grupo for grupo in perfil.painel.grupos}
    dentro = fora = 0
    por_recorte: dict[str, list[int]] = {}

    for documento in documentos:
        grupo_id = documento.grupo_id.casefold()
        grupo = grupos.get(grupo_id)
        grupo_atual = classificar(perfil, documento.situacao) if documento.situacao else None
        grupo_sem_emissao = bool(grupo and grupo.sem_emissao) or bool(
            grupo_atual and grupo_atual.sem_emissao
        )
        if (
            grupo_id == "ignorado"
            or (grupo_atual is not None and grupo_atual.id.casefold() == "ignorado")
            or _eh_cancelado(grupo, grupo_atual)
        ):
            continue

        contagem = por_recorte.setdefault(documento.recorte, [0, 0])
        if grupo_sem_emissao:
            continue

        numero_revisoes, aprovado = _contar_primeiro_ciclo(perfil, documento.emissoes)
        estourou = numero_revisoes > indicador.limite_revisoes
        no_avanco = grupo_id in ids_avanco
        if no_avanco:
            if estourou:
                fora += 1
                contagem[1] += 1
            else:
                dentro += 1
                contagem[0] += 1
        elif (
            indicador.contar_estourados_sem_aprovacao
            and not aprovado
            and estourou
        ):
            fora += 1
            contagem[1] += 1

    return ResultadoIndicadorAprovacao(
        geral=ResultadoContagemIndicador(dentro, fora),
        por_recorte={
            valor: ResultadoContagemIndicador(contagem[0], contagem[1])
            for valor, contagem in por_recorte.items()
        },
    )


def _contar_primeiro_ciclo(
    perfil: PerfilContrato,
    emissoes: Iterable[EmissaoIndicador],
) -> tuple[int, bool]:
    configuracao = perfil.emissao.revisao.preliminar
    if configuracao.nome != "numerica":
        return 0, False
    serie = criar_serie(configuracao.nome, inicio=configuracao.inicio)
    ids_avanco = {identificador.casefold() for identificador in perfil.painel.avanco}
    revisoes = 0
    aprovado = False
    for emissao in emissoes:
        eh_preliminar_numerica = (
            emissao.fase.casefold() == "preliminar"
            and serie.valida(str(emissao.revisao))
        )
        if eh_preliminar_numerica:
            revisoes += 1
        if classificar(perfil, emissao.situacao).id.casefold() in ids_avanco:
            aprovado = True
            break
    return revisoes, aprovado


def _eh_cancelado(grupo, grupo_atual) -> bool:
    grupos = tuple(item for item in (grupo, grupo_atual) if item is not None)
    for item in grupos:
        if item.id.casefold() == "cancelado" or _normalizar_situacao(item.rotulo) == "cancelado":
            return True
        if any(_normalizar_situacao(estado) == "cancelado" for estado in item.estados):
            return True
    return False
