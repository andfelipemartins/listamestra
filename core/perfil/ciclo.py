"""Séries documentais e transições puras do ciclo de emissão."""

from __future__ import annotations

from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Mapping
import re
import unicodedata

from .series import criar_serie

if TYPE_CHECKING:
    from .modelo import PerfilContrato


ACOES = frozenset(
    {
        "nova_versao",
        "nova_revisao_preliminar",
        "emitir_original",
        "reabrir",
        "fim_de_linha",
    }
)


@dataclass(frozen=True)
class SerieConfiguracao:
    nome: str
    inicio: str | int | None = None
    proibidas: tuple[str, ...] = ()
    continua_apos_aprovacao: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "proibidas", tuple(str(v).upper() for v in self.proibidas))


@dataclass(frozen=True)
class EixoRevisao:
    preliminar: SerieConfiguracao
    original: SerieConfiguracao
    reabertura: SerieConfiguracao | None = None


@dataclass(frozen=True)
class RegraEmissao:
    revisao: EixoRevisao
    versao: SerieConfiguracao | None = None


@dataclass(frozen=True)
class Transicao:
    acao: str
    bloqueia_medicao: bool = False


@dataclass(frozen=True)
class CicloAnalise:
    inicial: str
    transicoes: Mapping[str, Transicao]

    def __post_init__(self) -> None:
        object.__setattr__(self, "transicoes", MappingProxyType(dict(self.transicoes)))


@dataclass(frozen=True)
class EstadoEmissao:
    revisao: str
    versao: str | None
    fase: str
    ultima_original: str | None = None
    ultima_preliminar: str | None = None
    bloqueia_medicao: bool = False

    def __post_init__(self) -> None:
        if self.fase not in {"preliminar", "original", "encerrado"}:
            raise ValueError("Fase de emissão inválida.")


@dataclass(frozen=True)
class ErroCiclo:
    mensagem: str
    situacao: str | None = None


def definicao_serie_de_dict(dados: Any, nome_padrao: str | None = None) -> SerieConfiguracao:
    if isinstance(dados, str):
        nome = dados
        opcoes: dict[str, Any] = {}
    elif isinstance(dados, Mapping):
        nome = dados.get("serie", dados.get("nome", nome_padrao))
        opcoes = dict(dados)
    else:
        raise ValueError("Definição de série inválida: informe o nome ou um objeto.")
    if not isinstance(nome, str) or not nome.strip():
        raise ValueError("Definição de série sem nome.")
    canonicos = {
        "0 depois letras": "zero_depois_letras",
        "letra_proposta + numero": "letra_mais_numero",
        "letra + numero": "letra_mais_numero",
        "letra_mais_numero": "letra_mais_numero",
        "zero_depois_letras": "zero_depois_letras",
        "numerica": "numerica",
        "letras": "letras",
    }
    canonico = canonicos.get(nome.strip().casefold(), nome.strip().casefold())
    inicio = opcoes.get("inicio")
    if canonico == "letra_mais_numero" and "prefixo" in opcoes and inicio is None:
        inicio = opcoes["prefixo"]
    proibidas = opcoes.get("proibidas", ()) or ()
    if isinstance(proibidas, str):
        proibidas = (proibidas,)
    return SerieConfiguracao(
        nome=canonico,
        inicio=inicio,
        proibidas=tuple(proibidas),
        continua_apos_aprovacao=bool(opcoes.get("continua_apos_aprovacao", False)),
    )


def regra_emissao_de_dict(dados: Mapping[str, Any]) -> RegraEmissao:
    eixo = dados.get("revisao", {})
    if not isinstance(eixo, Mapping):
        raise ValueError("O eixo de revisão deve ser um objeto.")
    preliminar = eixo.get("preliminar")
    original = eixo.get("original")
    if preliminar is None or original is None:
        raise ValueError("O eixo de revisão exige séries preliminar e original.")
    return RegraEmissao(
        revisao=EixoRevisao(
            preliminar=definicao_serie_de_dict(preliminar),
            original=definicao_serie_de_dict(original),
            reabertura=(
                definicao_serie_de_dict(eixo["reabertura"])
                if eixo.get("reabertura") is not None
                else None
            ),
        ),
        versao=(
            definicao_serie_de_dict(dados["versao"])
            if dados.get("versao") is not None
            else None
        ),
    )


def ciclo_analise_de_dict(dados: Mapping[str, Any]) -> CicloAnalise:
    transicoes: dict[str, Transicao] = {}
    for situacao, definicao in (dados.get("transicoes") or {}).items():
        if isinstance(definicao, str):
            acao = definicao
            bloqueia = False
        elif isinstance(definicao, Mapping):
            acao = definicao.get("acao")
            bloqueia = bool(definicao.get("bloqueia_medicao", False))
        else:
            raise ValueError(f"Transição inválida para a situação '{situacao}'.")
        if acao not in ACOES:
            raise ValueError(f"Ação inválida na situação '{situacao}': '{acao}'.")
        transicoes[str(situacao)] = Transicao(acao=acao, bloqueia_medicao=bloqueia)
    inicial = dados.get("inicial")
    if not isinstance(inicial, str) or not inicial.strip():
        raise ValueError("O ciclo de análise precisa informar a situação inicial.")
    return CicloAnalise(inicial=inicial, transicoes=transicoes)


def iniciar(perfil: PerfilContrato) -> EstadoEmissao:
    regra = perfil.emissao
    revisao = _serie(regra.revisao.preliminar).primeira()
    versao = _serie(regra.versao).primeira() if regra.versao else None
    return EstadoEmissao(
        revisao=revisao,
        versao=versao,
        fase="preliminar",
        ultima_preliminar=revisao,
    )


def aplicar(
    perfil: PerfilContrato, estado: EstadoEmissao, situacao: str
) -> EstadoEmissao | ErroCiclo:
    if estado.fase == "encerrado":
        return ErroCiclo(
            mensagem="O código foi encerrado e não aceita novas situações.",
            situacao=situacao,
        )
    chave = _normalizar_situacao(situacao)
    transicao = next(
        (regra for nome, regra in perfil.analise.transicoes.items() if _normalizar_situacao(nome) == chave),
        None,
    )
    if transicao is None:
        return ErroCiclo(
            mensagem=f"A situação '{situacao}' não possui transição configurada.",
            situacao=situacao,
        )

    base = replace(estado, bloqueia_medicao=transicao.bloqueia_medicao)
    acao = transicao.acao
    if acao == "fim_de_linha":
        return replace(base, fase="encerrado")
    if acao == "nova_versao":
        if perfil.emissao.versao is None:
            return ErroCiclo("A ação nova_versao exige uma série de versão.", situacao)
        try:
            proxima = _proxima_ou_primeira(
                perfil.emissao.versao, estado.versao
            )
        except ValueError as erro:
            return ErroCiclo(str(erro), situacao)
        return replace(base, versao=proxima, fase="preliminar")
    if acao == "nova_revisao_preliminar":
        configuracao = perfil.emissao.revisao.preliminar
        if _parece_serie(estado.revisao, perfil.emissao.revisao.reabertura):
            configuracao = perfil.emissao.revisao.reabertura or configuracao
        try:
            revisao = _proxima_ou_primeira(configuracao, estado.revisao)
            versao = _primeira_versao(perfil)
        except ValueError as erro:
            return ErroCiclo(str(erro), situacao)
        return replace(
            base,
            revisao=revisao,
            versao=versao,
            fase="preliminar",
            ultima_preliminar=revisao,
        )
    if acao == "emitir_original":
        if estado.fase != "preliminar":
            return ErroCiclo("Só uma emissão preliminar pode ser aprovada.", situacao)
        try:
            revisao = _revisao_emitida(perfil, estado)
            versao = _primeira_versao(perfil)
        except ValueError as erro:
            return ErroCiclo(str(erro), situacao)
        return replace(
            base,
            revisao=revisao,
            versao=versao,
            fase="original",
            ultima_original=revisao,
        )
    if acao == "reabrir":
        if estado.fase != "original":
            return ErroCiclo("A reabertura exige uma emissão original aprovada.", situacao)
        try:
            revisao = _revisao_reaberta(perfil, estado)
            versao = _primeira_versao(perfil)
        except ValueError as erro:
            return ErroCiclo(str(erro), situacao)
        return replace(
            base,
            revisao=revisao,
            versao=versao,
            fase="preliminar",
            ultima_preliminar=revisao,
        )
    return ErroCiclo(f"Ação não suportada: '{acao}'.", situacao)


def rotulo_cronologico(historico: Any) -> list[str]:
    """Gera um rótulo para cada evento fornecido, na ordem cronológica recebida."""
    try:
        quantidade = len(historico)
    except TypeError:
        quantidade = sum(1 for _ in historico)
    if quantidade == 0:
        return []
    return ["Emissão Inicial", *(f"Revisão {indice}" for indice in range(1, quantidade))]


def _serie(configuracao: SerieConfiguracao | None):
    if configuracao is None:
        raise ValueError("Série não configurada.")
    return criar_serie(
        configuracao.nome,
        inicio=configuracao.inicio,
        proibidas=configuracao.proibidas,
    )


def _proxima_ou_primeira(configuracao: SerieConfiguracao, atual: str | None) -> str:
    serie = _serie(configuracao)
    if atual is None:
        return serie.primeira()
    if serie.valida(atual):
        return serie.proxima(atual)
    return serie.primeira()


def _primeira_versao(perfil: PerfilContrato) -> str | None:
    return _serie(perfil.emissao.versao).primeira() if perfil.emissao.versao else None


def _parece_serie(valor: str, configuracao: SerieConfiguracao | None) -> bool:
    return bool(configuracao and _serie(configuracao).valida(valor))


def _revisao_emitida(perfil: PerfilContrato, estado: EstadoEmissao) -> str:
    eixo = perfil.emissao.revisao
    eh_reabertura = bool(
        eixo.reabertura
        and eixo.reabertura.nome != eixo.preliminar.nome
        and _serie(eixo.reabertura).valida(estado.revisao)
    )
    if eh_reabertura:
        nome = eixo.reabertura.nome
        if nome == "letra_mais_numero":
            match = re.fullmatch(r"([A-Z]+)\d+", estado.revisao.upper())
            if match:
                return match.group(1)
        return estado.revisao
    original = _serie(eixo.original)
    if eixo.original.nome == "numerica":
        return _proxima_ou_primeira(eixo.original, estado.ultima_original)
    if eixo.original.nome == "zero_depois_letras":
        if estado.ultima_original is None:
            return original.primeira()
        return _proxima_ou_primeira(eixo.original, estado.ultima_original)
    return _proxima_ou_primeira(eixo.original, estado.ultima_original)


def _revisao_reaberta(perfil: PerfilContrato, estado: EstadoEmissao) -> str:
    eixo = perfil.emissao.revisao
    reabertura = eixo.reabertura
    if reabertura is None:
        raise ValueError("A regra de emissão não define uma série de reabertura.")
    serie = _serie(reabertura)
    if reabertura.nome == "letra_mais_numero":
        original = _serie(eixo.original)
        base = estado.ultima_original or estado.revisao
        if eixo.original.nome == "zero_depois_letras":
            prefixo = original.proxima(base)
        elif eixo.original.nome == "numerica":
            if estado.ultima_preliminar and eixo.preliminar.nome == "letras":
                prefixo = estado.ultima_preliminar
            else:
                prefixo = serie.inicio_letra
        else:
            prefixo = serie.inicio_letra
        return serie.primeira_com_prefixo(prefixo)
    if reabertura.nome == "letras":
        base = estado.ultima_preliminar
        if reabertura.continua_apos_aprovacao and base and serie.valida(base):
            return serie.proxima(base)
        return serie.primeira()
    return _proxima_ou_primeira(reabertura, estado.ultima_preliminar)


def _normalizar_situacao(valor: str) -> str:
    sem_acentos = "".join(
        caractere
        for caractere in unicodedata.normalize("NFD", valor)
        if unicodedata.category(caractere) != "Mn"
    )
    return re.sub(r"[^A-Z0-9]+", "_", sem_acentos.upper()).strip("_")
