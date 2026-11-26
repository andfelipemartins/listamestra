"""Cálculos puros dos indicadores declarados no perfil do contrato."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Iterable

from .ciclo import _normalizar_situacao
from .modelo import IndicadorAprovacao, IndicadorReabertura, PerfilContrato
from .painel import classificar, resolver_situacao_oculta
from .series import criar_serie


@dataclass(frozen=True)
class EmissaoIndicador:
    fase: str
    revisao: str
    situacao: str | None
    versao: int | str | None = None
    situacoes_mais_recentes: tuple[str | None, ...] = ()
    motivo_reabertura: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "situacoes_mais_recentes", tuple(self.situacoes_mais_recentes))


@dataclass(frozen=True)
class DocumentoIndicador:
    grupo_id: str
    situacao: str | None
    emissoes: tuple[EmissaoIndicador, ...]
    recorte: str = ""
    situacoes_mais_recentes: tuple[str | None, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "emissoes", tuple(self.emissoes))
        object.__setattr__(self, "situacoes_mais_recentes", tuple(self.situacoes_mais_recentes))


@dataclass(frozen=True)
class ResultadoContagemIndicador:
    dentro_limite: int
    fora_limite: int
    distribuicao: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "distribuicao", tuple(self.distribuicao))

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


@dataclass(frozen=True)
class ResultadoIndicadorReabertura:
    total_reaberturas: int
    resolvidas_no_padrao: int
    resolvidas_fora_padrao: int
    em_aberto: int
    documentos_acima_limite: int
    por_motivo: Mapping[str, int]

    @property
    def percentual_no_padrao(self) -> float | None:
        if not self.total_reaberturas:
            return None
        return 100 * self.resolvidas_no_padrao / self.total_reaberturas


_MOTIVOS_REABERTURA = ("campo", "projeto", "cliente", "outro", "sem_motivo")


def calcular_indicador_reabertura(
    perfil: PerfilContrato,
    indicador: IndicadorReabertura,
    documentos: Iterable[DocumentoIndicador],
) -> ResultadoIndicadorReabertura:
    """Conta reaberturas pelo ciclo e pelas séries declaradas no perfil."""
    eixo = perfil.emissao.revisao
    if eixo.reabertura is None:
        raise ValueError("O indicador de reabertura exige a série reabertura do perfil.")
    serie_reabertura = criar_serie(
        eixo.reabertura.nome,
        inicio=eixo.reabertura.inicio,
        proibidas=eixo.reabertura.proibidas,
    )
    serie_original = criar_serie(
        eixo.original.nome,
        inicio=eixo.original.inicio,
        proibidas=eixo.original.proibidas,
    )
    ids_avanco = {identificador.casefold() for identificador in perfil.painel.avanco}
    total = dentro = fora = abertos = acima_limite = 0
    por_motivo = {motivo: 0 for motivo in _MOTIVOS_REABERTURA}

    for documento in documentos:
        teve_aprovacao = False
        ativa = None
        quantidade_documento = 0

        for emissao in documento.emissoes:
            fase = emissao.fase.casefold()
            revisao = str(emissao.revisao)
            grupo = classificar(perfil, emissao.situacao) if emissao.situacao else None
            if grupo and grupo.oculto_no_painel:
                situacao = resolver_situacao_oculta(
                    perfil,
                    emissao.situacoes_mais_recentes or (emissao.situacao,),
                )
                grupo = classificar(perfil, situacao)
            aprovada = bool(grupo and grupo.id.casefold() in ids_avanco)

            if fase == "original" and serie_original.valida(revisao) and aprovada:
                if ativa is not None:
                    total += 1
                    quantidade_documento += 1
                    por_motivo[ativa["motivo"]] += 1
                    if ativa["emissoes"] <= indicador.max_revisoes_por_reabertura:
                        dentro += 1
                    else:
                        fora += 1
                    ativa = None
                teve_aprovacao = True
                continue

            if (
                teve_aprovacao
                and fase == "preliminar"
                and serie_reabertura.valida(revisao)
            ):
                if ativa is None:
                    motivo = (emissao.motivo_reabertura or "").strip().casefold()
                    if motivo not in _MOTIVOS_REABERTURA[:-1]:
                        motivo = "sem_motivo"
                    ativa = {"emissoes": 0, "motivo": motivo}
                ativa["emissoes"] += 1

        if ativa is not None:
            total += 1
            quantidade_documento += 1
            por_motivo[ativa["motivo"]] += 1
            abertos += 1
        if quantidade_documento > indicador.max_reaberturas:
            acima_limite += 1

    return ResultadoIndicadorReabertura(
        total_reaberturas=total,
        resolvidas_no_padrao=dentro,
        resolvidas_fora_padrao=fora,
        em_aberto=abertos,
        documentos_acima_limite=acima_limite,
        por_motivo=por_motivo,
    )


def calcular_indicador_aprovacao(
    perfil: PerfilContrato,
    indicador: IndicadorAprovacao,
    documentos: Iterable[DocumentoIndicador],
) -> ResultadoIndicadorAprovacao:
    """Calcula aprovações no primeiro ciclo e sua distribuição por revisão."""
    ids_avanco = {identificador.casefold() for identificador in perfil.painel.avanco}
    grupos = {grupo.id.casefold(): grupo for grupo in perfil.painel.grupos}
    dentro = fora = 0
    quantidade_faixas = indicador.agrupar_a_partir + 1
    distribuicao_geral = [0] * quantidade_faixas
    por_recorte: dict[str, list] = {}

    def nova_contagem() -> list:
        return [0, 0, [0] * quantidade_faixas]

    for documento in documentos:
        grupo_id = documento.grupo_id.casefold()
        grupo = grupos.get(grupo_id)
        grupo_atual = classificar(perfil, documento.situacao) if documento.situacao else None
        if grupo_atual and grupo_atual.oculto_no_painel:
            situacao_efetiva = resolver_situacao_oculta(
                perfil,
                documento.situacoes_mais_recentes or (documento.situacao,),
            )
            grupo_atual = classificar(perfil, situacao_efetiva)
            grupo_id = grupo_atual.id.casefold()
            grupo = grupos.get(grupo_id)
        grupo_sem_emissao = bool(grupo and grupo.sem_emissao) or bool(
            grupo_atual and grupo_atual.sem_emissao
        )
        if (
            grupo_id == "ignorado"
            or (grupo_atual is not None and grupo_atual.id.casefold() == "ignorado")
            or _eh_cancelado(grupo, grupo_atual)
        ):
            continue

        contagem = por_recorte.setdefault(documento.recorte, nova_contagem())
        if grupo_sem_emissao:
            continue

        numero_revisoes, aprovado = _contar_primeiro_ciclo(perfil, documento.emissoes)
        estourou = numero_revisoes > indicador.limite_revisoes
        no_avanco = grupo_id in ids_avanco
        aprovado = aprovado or no_avanco
        if aprovado:
            faixa = min(numero_revisoes, indicador.agrupar_a_partir)
            distribuicao_geral[faixa] += 1
            contagem[2][faixa] += 1
        if aprovado:
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
        geral=ResultadoContagemIndicador(dentro, fora, tuple(distribuicao_geral)),
        por_recorte={
            valor: ResultadoContagemIndicador(
                contagem[0], contagem[1], tuple(contagem[2])
            )
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
    emissoes_preliminares = 0
    aprovado = False
    for emissao in emissoes:
        eh_preliminar_numerica = (
            emissao.fase.casefold() == "preliminar"
            and serie.valida(str(emissao.revisao))
        )
        if eh_preliminar_numerica:
            emissoes_preliminares += 1
        situacao = emissao.situacao
        grupo = classificar(perfil, situacao) if situacao else None
        if grupo and grupo.oculto_no_painel:
            situacao = resolver_situacao_oculta(
                perfil,
                emissao.situacoes_mais_recentes or (emissao.situacao,),
            )
            grupo = classificar(perfil, situacao)
        if grupo and grupo.id.casefold() in ids_avanco:
            aprovado = True
            break
    return max(emissoes_preliminares - 1, 0), aprovado


def _eh_cancelado(grupo, grupo_atual) -> bool:
    grupos = tuple(item for item in (grupo, grupo_atual) if item is not None)
    for item in grupos:
        if item.id.casefold() == "cancelado" or _normalizar_situacao(item.rotulo) == "cancelado":
            return True
        if any(_normalizar_situacao(estado) == "cancelado" for estado in item.estados):
            return True
    return False
