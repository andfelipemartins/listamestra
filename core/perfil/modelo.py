"""Modelo imutável e validação dos perfis declarativos de contrato."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping
import re

from .ciclo import (
    CicloAnalise,
    RegraEmissao,
    _normalizar_situacao,
    ciclo_analise_de_dict,
    regra_emissao_de_dict,
)
from .feriados import FeriadoExtra
from .series import criar_serie


class ErroPerfil(ValueError):
    """Perfil ausente ou inválido, com mensagem própria para apresentação ao usuário."""


@dataclass(frozen=True)
class Segmento:
    nome: str
    rotulo: str
    padrao_regex: str
    valores: Mapping[str, str] | None = None
    obrigatorio: bool = True

    def __post_init__(self) -> None:
        if self.valores is not None:
            object.__setattr__(
                self,
                "valores",
                MappingProxyType({str(chave): str(rotulo) for chave, rotulo in self.valores.items()}),
            )


@dataclass(frozen=True)
class Separador:
    texto: str


ParteCodigo = Segmento | Separador


@dataclass(frozen=True)
class Restricao:
    se_segmento: str
    igual_a: str
    entao_segmento: str
    em: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "em", tuple(str(valor) for valor in self.em))


@dataclass(frozen=True)
class EstruturaCodigo:
    segmentos: tuple[ParteCodigo, ...]
    revisao_no_codigo: bool = False
    segmento_revisao: str | None = None
    segmentos_identidade: tuple[str, ...] = ()
    restricoes: tuple[Restricao, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "segmentos", tuple(self.segmentos))
        object.__setattr__(self, "segmentos_identidade", tuple(self.segmentos_identidade))
        object.__setattr__(self, "restricoes", tuple(self.restricoes))

    @property
    def campos(self) -> tuple[Segmento, ...]:
        return tuple(parte for parte in self.segmentos if isinstance(parte, Segmento))


@dataclass(frozen=True)
class Grupo:
    id: str
    rotulo: str
    cor: str | None = None
    estados: tuple[str, ...] = ()
    sem_emissao: bool = False
    conta_no_avanco: bool = True
    oculto_no_painel: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "estados", tuple(str(estado) for estado in self.estados))


@dataclass(frozen=True)
class RegraCategoria:
    valores: Mapping[str, tuple[str, ...]]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "valores",
            MappingProxyType(
                {str(caixa): tuple(str(valor) for valor in valores) for caixa, valores in self.valores.items()}
            ),
        )


@dataclass(frozen=True)
class Categoria:
    id: str
    rotulo: str
    regras: tuple[RegraCategoria, ...] = ()
    padrao: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "regras", tuple(self.regras))


@dataclass(frozen=True)
class PacotePainel:
    segmentos: tuple[str, ...]
    nome_de: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "segmentos", tuple(self.segmentos))


@dataclass(frozen=True)
class PainelPerfil:
    grupos: tuple[Grupo, ...]
    ignorar: tuple[str, ...] = ()
    avanco: tuple[str, ...] = ()
    indicadores: tuple[IndicadorAprovacao, ...] = ()
    categorias: tuple[Categoria, ...] = ()
    pacote: PacotePainel | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "grupos", tuple(self.grupos))
        object.__setattr__(self, "ignorar", tuple(self.ignorar))
        object.__setattr__(self, "avanco", tuple(self.avanco))
        object.__setattr__(self, "indicadores", tuple(self.indicadores))
        object.__setattr__(self, "categorias", tuple(self.categorias))


@dataclass(frozen=True)
class IndicadorAprovacao:
    id: str
    rotulo: str
    limite_revisoes: int
    meta_percentual: float | None
    rotulo_meta: str
    contar_estourados_sem_aprovacao: bool
    ciclos: str
    agrupar_a_partir: int = 5


@dataclass(frozen=True)
class ExcecaoPrazo:
    siglas: tuple[str, ...]
    dias: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "siglas", tuple(self.siglas))


@dataclass(frozen=True)
class FaixaAtraso:
    ate_dias: int | None
    rotulo: str


@dataclass(frozen=True)
class RegraPrazo:
    id: str
    rotulo: str
    dias: int
    tipo_dia: str
    inicio: str
    fim: str
    excecoes: tuple[ExcecaoPrazo, ...] = ()
    so_quando_grupo: tuple[str, ...] = ()
    meta_percentual: float | None = None
    faixas_atraso: tuple[FaixaAtraso, ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "excecoes", tuple(self.excecoes))
        object.__setattr__(self, "so_quando_grupo", tuple(self.so_quando_grupo))
        if self.faixas_atraso is not None:
            object.__setattr__(self, "faixas_atraso", tuple(self.faixas_atraso))


@dataclass(frozen=True)
class RegiaoFeriados:
    uf: str
    municipio: str


@dataclass(frozen=True)
class FeriadosPerfil:
    nacionais: bool = True
    extras: tuple[FeriadoExtra, ...] = ()
    regiao: RegiaoFeriados | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "extras", tuple(self.extras))


@dataclass(frozen=True)
class PrazosPerfil:
    feriados: FeriadosPerfil
    meta_percentual: float
    regras: tuple[RegraPrazo, ...]
    meta_cronograma: float | None = None
    faixas_atraso: tuple[FaixaAtraso, ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "regras", tuple(self.regras))
        if self.faixas_atraso is not None:
            object.__setattr__(self, "faixas_atraso", tuple(self.faixas_atraso))


def _painel_minimo() -> PainelPerfil:
    return PainelPerfil(
        grupos=(
            Grupo(id="a_emitir", rotulo="A EMITIR", sem_emissao=True),
            Grupo(id="em_analise", rotulo="EM ANÁLISE"),
            Grupo(id="outros", rotulo="OUTROS"),
        )
    )


@dataclass(frozen=True)
class PerfilContrato:
    nome: str
    versao: str
    vigencia_inicio: date
    codigo: EstruturaCodigo
    emissao: RegraEmissao
    analise: CicloAnalise
    painel: PainelPerfil = field(default_factory=_painel_minimo)
    prazos: PrazosPerfil | None = None


def perfil_de_dict(dados: Mapping[str, Any]) -> PerfilContrato:
    """Converte um objeto simples em perfil validado; erros são ErroPerfil em português."""
    try:
        if not isinstance(dados, Mapping):
            raise ErroPerfil("O perfil deve ser um objeto/dicionário.")
        nome = _texto_obrigatorio(dados.get("nome"), "nome")
        versao = _texto_obrigatorio(dados.get("versao"), "versão")
        vigencia = _data(dados.get("vigencia_inicio"))
        codigo = _estrutura_de_dict(dados.get("codigo"))
        emissao = regra_emissao_de_dict(dados.get("emissao") or {})
        _validar_series(emissao)
        analise = ciclo_analise_de_dict(dados.get("analise") or {})
        painel = _painel_de_dict(dados.get("painel"), codigo)
        prazos = _prazos_de_dict(dados.get("prazos"))
        return PerfilContrato(nome, versao, vigencia, codigo, emissao, analise, painel, prazos)
    except ErroPerfil:
        raise
    except (KeyError, TypeError, ValueError, re.error) as erro:
        mensagem = str(erro).strip() or "Estrutura inválida."
        raise ErroPerfil(f"Perfil inválido: {mensagem}") from erro


def carregar_perfil(dados: Mapping[str, Any]) -> PerfilContrato:
    """Alias explícito para carregamento a partir de dict."""
    return perfil_de_dict(dados)


def carregar_yaml(caminho: str | Path) -> PerfilContrato:
    try:
        import yaml
    except ImportError as erro:
        raise ErroPerfil("A dependência PyYAML é necessária para carregar perfis YAML.") from erro
    try:
        with Path(caminho).open("r", encoding="utf-8") as arquivo:
            dados = yaml.safe_load(arquivo)
    except (OSError, yaml.YAMLError) as erro:
        raise ErroPerfil(f"Não foi possível carregar o YAML do perfil: {erro}") from erro
    return perfil_de_dict(dados)


def _painel_de_dict(dados: Any, codigo: EstruturaCodigo) -> PainelPerfil:
    if dados is None:
        return _painel_minimo()
    if not isinstance(dados, Mapping):
        raise ErroPerfil("'painel' precisa ser um objeto.")

    grupos_brutos = dados.get("grupos")
    if not isinstance(grupos_brutos, (list, tuple)):
        raise ErroPerfil("'painel.grupos' precisa ser uma lista.")

    grupos: list[Grupo] = []
    ids: set[str] = set()
    estados: dict[str, str] = {}
    for posicao, item in enumerate(grupos_brutos, start=1):
        if not isinstance(item, Mapping):
            raise ErroPerfil(f"Grupo {posicao} de 'painel.grupos' precisa ser um objeto.")
        identificador = _texto_obrigatorio(item.get("id"), f"id do grupo {posicao}")
        chave_id = identificador.casefold()
        if chave_id in {"nao_mapeado", "ignorado"}:
            raise ErroPerfil(f"O id '{identificador}' é reservado para uso interno do painel.")
        if chave_id in ids:
            raise ErroPerfil(f"Id de grupo repetido em 'painel.grupos': '{identificador}'.")
        ids.add(chave_id)

        rotulo = _texto_obrigatorio(item.get("rotulo"), f"rótulo do grupo '{identificador}'")
        cor = item.get("cor")
        if cor is not None and (not isinstance(cor, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", cor)):
            raise ErroPerfil(f"A cor do grupo '{identificador}' precisa estar no formato #RRGGBB.")

        estados_brutos = item.get("estados", ())
        if not isinstance(estados_brutos, (list, tuple)):
            raise ErroPerfil(f"'estados' do grupo '{identificador}' precisa ser uma lista.")
        estados_grupo = tuple(
            _texto_obrigatorio(estado, f"estado do grupo '{identificador}'")
            for estado in estados_brutos
        )
        sem_emissao = item.get("sem_emissao", False)
        conta_no_avanco = item.get("conta_no_avanco", True)
        oculto_no_painel = item.get("oculto_no_painel", False)
        if not isinstance(sem_emissao, bool):
            raise ErroPerfil(f"'sem_emissao' do grupo '{identificador}' precisa ser booleano.")
        if not isinstance(conta_no_avanco, bool):
            raise ErroPerfil(f"'conta_no_avanco' do grupo '{identificador}' precisa ser booleano.")
        if not isinstance(oculto_no_painel, bool):
            raise ErroPerfil(f"'oculto_no_painel' do grupo '{identificador}' precisa ser booleano.")

        for estado in estados_grupo:
            chave_estado = _normalizar_situacao(estado)
            grupo_anterior = estados.get(chave_estado)
            if grupo_anterior is not None:
                raise ErroPerfil(
                    f"A situação '{estado}' aparece em mais de um grupo: "
                    f"'{grupo_anterior}' e '{identificador}'."
                )
            estados[chave_estado] = identificador
        grupos.append(
            Grupo(
                id=identificador,
                rotulo=rotulo,
                cor=cor,
                estados=estados_grupo,
                sem_emissao=sem_emissao,
                conta_no_avanco=conta_no_avanco,
                oculto_no_painel=oculto_no_painel,
            )
        )

    sem_emissao = [grupo for grupo in grupos if grupo.sem_emissao]
    if not sem_emissao:
        raise ErroPerfil("'painel.grupos' precisa ter ao menos um grupo com 'sem_emissao: true'.")
    if len(sem_emissao) > 1:
        raise ErroPerfil("'painel.grupos' não pode ter mais de um grupo com 'sem_emissao: true'.")

    ignorar_bruto = dados.get("ignorar", ()) or ()
    if not isinstance(ignorar_bruto, (list, tuple)):
        raise ErroPerfil("'painel.ignorar' precisa ser uma lista de situações.")
    ignorar = tuple(
        _texto_obrigatorio(estado, "situação em 'painel.ignorar'")
        for estado in ignorar_bruto
    )
    estados_ignorados: set[str] = set()
    for estado in ignorar:
        chave_estado = _normalizar_situacao(estado)
        if chave_estado in estados:
            raise ErroPerfil(
                f"A situação '{estado}' está em 'painel.ignorar' e também no grupo "
                f"'{estados[chave_estado]}'."
            )
        estados_ignorados.add(chave_estado)

    avanco_bruto = dados.get("avanco", ()) or ()
    if not isinstance(avanco_bruto, (list, tuple)):
        raise ErroPerfil("'painel.avanco' precisa ser uma lista de ids de grupo.")
    avanco = tuple(
        _texto_obrigatorio(identificador, "id em 'painel.avanco'")
        for identificador in avanco_bruto
    )
    grupos_por_id = {grupo.id.casefold(): grupo for grupo in grupos}
    ids_avanco: set[str] = set()
    for identificador in avanco:
        chave_id = identificador.casefold()
        grupo = grupos_por_id.get(chave_id)
        if grupo is None:
            raise ErroPerfil(
                f"'painel.avanco' referencia o grupo inexistente '{identificador}'."
            )
        if chave_id in ids_avanco:
            raise ErroPerfil(f"Id de grupo repetido em 'painel.avanco': '{identificador}'.")
        if not grupo.conta_no_avanco:
            raise ErroPerfil(
                f"O grupo '{identificador}' está em 'painel.avanco', mas não conta no avanço."
            )
        ids_avanco.add(chave_id)

    indicadores = _indicadores_de_dict(dados.get("indicadores", ()))
    categorias = _categorias_de_dict(dados.get("categorias"), codigo)
    pacote = _pacote_de_dict(dados.get("pacote"), codigo)
    return PainelPerfil(
        grupos=tuple(grupos),
        ignorar=ignorar,
        avanco=avanco,
        indicadores=indicadores,
        categorias=categorias,
        pacote=pacote,
    )


def _pacote_de_dict(dados: Any, codigo: EstruturaCodigo) -> PacotePainel | None:
    if dados is None:
        return None
    if not isinstance(dados, Mapping):
        raise ErroPerfil("'painel.pacote' precisa ser um objeto.")

    caixas = {campo.nome.casefold(): campo.nome for campo in codigo.campos}
    segmentos_brutos = dados.get("segmentos")
    if not isinstance(segmentos_brutos, (list, tuple)) or not segmentos_brutos:
        raise ErroPerfil("'painel.pacote.segmentos' precisa ser uma lista não vazia de caixas do código.")

    segmentos: list[str] = []
    vistos: set[str] = set()
    for nome_caixa in segmentos_brutos:
        if not isinstance(nome_caixa, str) or nome_caixa.casefold() not in caixas:
            raise ErroPerfil(
                f"'painel.pacote.segmentos' referencia a caixa inexistente '{nome_caixa}'."
            )
        nome = caixas[nome_caixa.casefold()]
        if nome.casefold() in vistos:
            raise ErroPerfil(f"Caixa repetida em 'painel.pacote.segmentos': '{nome}'.")
        vistos.add(nome.casefold())
        segmentos.append(nome)

    nome_de_bruto = dados.get("nome_de")
    nome_de = None
    if nome_de_bruto is not None:
        if not isinstance(nome_de_bruto, str) or nome_de_bruto.casefold() not in caixas:
            raise ErroPerfil(
                f"'painel.pacote.nome_de' referencia a caixa inexistente '{nome_de_bruto}'."
            )
        nome_de = caixas[nome_de_bruto.casefold()]

    return PacotePainel(segmentos=tuple(segmentos), nome_de=nome_de)


def _categorias_de_dict(dados: Any, codigo: EstruturaCodigo) -> tuple[Categoria, ...]:
    if dados is None:
        return ()
    if not isinstance(dados, (list, tuple)):
        raise ErroPerfil("'painel.categorias' precisa ser uma lista.")

    caixas = {campo.nome.casefold(): campo.nome for campo in codigo.campos}
    categorias: list[Categoria] = []
    ids: set[str] = set()
    padroes = 0
    for posicao, item in enumerate(dados, start=1):
        campo = f"painel.categorias[{posicao}]"
        if not isinstance(item, Mapping):
            raise ErroPerfil(f"{campo} precisa ser um objeto.")
        identificador = _texto_obrigatorio(item.get("id"), f"id em {campo}")
        chave_id = identificador.casefold()
        if chave_id in ids:
            raise ErroPerfil(f"Id de categoria repetido em 'painel.categorias': '{identificador}'.")
        ids.add(chave_id)
        rotulo = _texto_obrigatorio(item.get("rotulo"), f"rótulo da categoria '{identificador}'")
        padrao = item.get("padrao", False)
        if not isinstance(padrao, bool):
            raise ErroPerfil(f"'padrao' da categoria '{identificador}' precisa ser booleano.")
        padroes += int(padrao)

        regras_brutas = item.get("regras", ())
        if not isinstance(regras_brutas, (list, tuple)):
            raise ErroPerfil(f"'regras' da categoria '{identificador}' precisa ser uma lista.")
        regras: list[RegraCategoria] = []
        for indice, regra_bruta in enumerate(regras_brutas, start=1):
            campo_regra = f"{campo}.regras[{indice}]"
            if not isinstance(regra_bruta, Mapping) or not regra_bruta:
                raise ErroPerfil(f"{campo_regra} precisa ser um objeto com ao menos uma caixa.")
            valores_regra: dict[str, tuple[str, ...]] = {}
            caixas_regra: set[str] = set()
            for nome_caixa, valores_brutos in regra_bruta.items():
                if not isinstance(nome_caixa, str) or nome_caixa.casefold() not in caixas:
                    raise ErroPerfil(
                        f"A regra {campo_regra} referencia a caixa inexistente '{nome_caixa}'."
                    )
                nome = caixas[nome_caixa.casefold()]
                chave_caixa = nome.casefold()
                if chave_caixa in caixas_regra:
                    raise ErroPerfil(f"Caixa repetida em {campo_regra}: '{nome}'.")
                caixas_regra.add(chave_caixa)
                if not isinstance(valores_brutos, (list, tuple)) or not valores_brutos:
                    raise ErroPerfil(
                        f"Os valores da caixa '{nome}' em {campo_regra} precisam ser uma lista não vazia."
                    )
                valores_regra[nome] = tuple(
                    _texto_obrigatorio(valor, f"valor da caixa '{nome}' em {campo_regra}")
                    for valor in valores_brutos
                )
            regras.append(RegraCategoria(valores=valores_regra))
        categorias.append(Categoria(identificador, rotulo, tuple(regras), padrao))

    if padroes > 1:
        raise ErroPerfil("'painel.categorias' não pode ter mais de uma categoria com 'padrao: true'.")
    return tuple(categorias)


def _indicadores_de_dict(dados: Any) -> tuple[IndicadorAprovacao, ...]:
    if not isinstance(dados, (list, tuple)):
        raise ErroPerfil("'painel.indicadores' precisa ser uma lista.")

    indicadores: list[IndicadorAprovacao] = []
    ids: set[str] = set()
    for posicao, item in enumerate(dados, start=1):
        campo = f"painel.indicadores[{posicao}]"
        if not isinstance(item, Mapping):
            raise ErroPerfil(f"{campo} precisa ser um objeto.")
        tipo = item.get("tipo")
        if tipo != "aprovacao_em_ate_n_revisoes":
            raise ErroPerfil(
                f"Tipo de indicador inválido em {campo}: '{tipo}'. "
                "O tipo suportado é 'aprovacao_em_ate_n_revisoes'."
            )

        identificador = _texto_obrigatorio(item.get("id"), f"id em {campo}")
        chave_id = identificador.casefold()
        if chave_id in ids:
            raise ErroPerfil(f"Id de indicador repetido em 'painel.indicadores': '{identificador}'.")
        ids.add(chave_id)

        limite = item.get("limite_revisoes")
        if isinstance(limite, bool) or not isinstance(limite, int) or limite < 1:
            raise ErroPerfil(f"'limite_revisoes' de '{identificador}' precisa ser inteiro maior ou igual a 1.")
        meta = item.get("meta_percentual")
        if meta is not None and (
            isinstance(meta, bool)
            or not isinstance(meta, (int, float))
            or not 0 <= meta <= 100
        ):
            raise ErroPerfil(f"'meta_percentual' de '{identificador}' precisa ser um número entre 0 e 100.")
        agrupar_a_partir = item.get("agrupar_a_partir", 5)
        if (
            isinstance(agrupar_a_partir, bool)
            or not isinstance(agrupar_a_partir, int)
            or agrupar_a_partir < 1
        ):
            raise ErroPerfil(f"'agrupar_a_partir' de '{identificador}' precisa ser inteiro maior ou igual a 1.")
        if agrupar_a_partir <= limite:
            raise ErroPerfil(
                f"'agrupar_a_partir' de '{identificador}' precisa ser maior que 'limite_revisoes'."
            )
        contar_estourados = item.get("contar_estourados_sem_aprovacao")
        if not isinstance(contar_estourados, bool):
            raise ErroPerfil(
                f"'contar_estourados_sem_aprovacao' de '{identificador}' precisa ser booleano."
            )

        ciclos = item.get("ciclos")
        if ciclos == "cada_ciclo":
            raise ErroPerfil("O modo de ciclos 'cada_ciclo' ainda não suportado.")
        if ciclos != "primeira_aprovacao":
            raise ErroPerfil(
                f"'ciclos' de '{identificador}' precisa ser 'primeira_aprovacao'."
            )

        indicadores.append(
            IndicadorAprovacao(
                id=identificador,
                rotulo=_texto_obrigatorio(
                    item.get("rotulo", f"Aprovados até a Revisão {limite}"),
                    f"rótulo do indicador '{identificador}'",
                ),
                limite_revisoes=limite,
                meta_percentual=float(meta) if meta is not None else None,
                rotulo_meta=_texto_obrigatorio(
                    item.get("rotulo_meta"), f"rótulo da meta do indicador '{identificador}'"
                ),
                contar_estourados_sem_aprovacao=contar_estourados,
                ciclos=ciclos,
                agrupar_a_partir=agrupar_a_partir,
            )
        )
    return tuple(indicadores)


def _prazos_de_dict(dados: Any) -> PrazosPerfil | None:
    if dados is None:
        return None
    if not isinstance(dados, Mapping):
        raise ErroPerfil("'prazos' precisa ser um objeto.")

    feriados_dados = dados.get("feriados", {})
    if not isinstance(feriados_dados, Mapping):
        raise ErroPerfil("'prazos.feriados' precisa ser um objeto.")
    nacionais = feriados_dados.get("nacionais", True)
    if not isinstance(nacionais, bool):
        raise ErroPerfil("'prazos.feriados.nacionais' precisa ser booleano.")
    regiao_dados = feriados_dados.get("regiao")
    regiao = None
    if regiao_dados is not None:
        if not isinstance(regiao_dados, Mapping):
            raise ErroPerfil("'prazos.feriados.regiao' precisa ser um objeto.")
        uf = _texto_obrigatorio(regiao_dados.get("uf"), "prazos.feriados.regiao.uf")
        municipio = _texto_obrigatorio(
            regiao_dados.get("municipio"), "prazos.feriados.regiao.municipio"
        )
        if not re.fullmatch(r"[A-Za-z]{2}", uf):
            raise ErroPerfil("'prazos.feriados.regiao.uf' precisa ter duas letras.")
        regiao = RegiaoFeriados(uf=uf.upper(), municipio=municipio)
    extras_dados = feriados_dados.get("extras", ())
    if not isinstance(extras_dados, (list, tuple)):
        raise ErroPerfil("'prazos.feriados.extras' precisa ser uma lista.")
    extras: list[FeriadoExtra] = []
    for posicao, item in enumerate(extras_dados, start=1):
        campo = f"prazos.feriados.extras[{posicao}]"
        if not isinstance(item, Mapping):
            raise ErroPerfil(f"{campo} precisa ser um objeto.")
        try:
            data = _data_prazo(item.get("data"), campo)
        except ValueError as erro:
            raise ErroPerfil(str(erro)) from erro
        extras.append(FeriadoExtra(data, _texto_obrigatorio(item.get("nome"), f"nome em {campo}")))

    meta = _meta_percentual_prazo(dados.get("meta_percentual"), "prazos.meta_percentual")
    meta_cronograma = _meta_percentual_prazo(
        dados.get("meta_cronograma", meta), "prazos.meta_cronograma", permite_none=True
    )
    faixas_atraso = _faixas_atraso_prazo(dados.get("faixas_atraso"), "prazos.faixas_atraso")

    regras_dados = dados.get("regras")
    if not isinstance(regras_dados, (list, tuple)):
        raise ErroPerfil("'prazos.regras' precisa ser uma lista.")
    regras: list[RegraPrazo] = []
    ids: set[str] = set()
    for posicao, item in enumerate(regras_dados, start=1):
        campo = f"prazos.regras[{posicao}]"
        if not isinstance(item, Mapping):
            raise ErroPerfil(f"{campo} precisa ser um objeto.")
        identificador = _texto_obrigatorio(item.get("id"), f"id em {campo}")
        meta_regra = _meta_percentual_prazo(
            item.get("meta_percentual", meta),
            f"meta_percentual de '{identificador}'",
            permite_none=True,
        )
        faixas_atraso_regra = _faixas_atraso_prazo(
            item.get("faixas_atraso"), f"faixas_atraso de '{identificador}'"
        )
        chave_id = identificador.casefold()
        if chave_id in ids:
            raise ErroPerfil(f"Id de regra repetido em 'prazos.regras': '{identificador}'.")
        ids.add(chave_id)
        dias = item.get("dias")
        if isinstance(dias, bool) or not isinstance(dias, int) or dias < 1:
            raise ErroPerfil(f"'dias' de '{identificador}' precisa ser inteiro maior ou igual a 1.")
        tipo_dia = item.get("tipo_dia")
        if tipo_dia not in {"uteis", "corridos"}:
            raise ErroPerfil(f"'tipo_dia' de '{identificador}' precisa ser 'uteis' ou 'corridos'.")
        excecoes = _excecoes_prazo(item.get("excecoes", ()), identificador)
        grupos_dados = item.get("so_quando_grupo", ())
        if not isinstance(grupos_dados, (list, tuple)):
            raise ErroPerfil(f"'so_quando_grupo' de '{identificador}' precisa ser uma lista.")
        grupos = tuple(
            _texto_obrigatorio(grupo, f"grupo em 'so_quando_grupo' de '{identificador}'")
            for grupo in grupos_dados
        )
        regras.append(
            RegraPrazo(
                id=identificador,
                rotulo=_texto_obrigatorio(item.get("rotulo"), f"rótulo da regra '{identificador}'"),
                dias=dias,
                tipo_dia=tipo_dia,
                inicio=_texto_obrigatorio(item.get("inicio"), f"início da regra '{identificador}'"),
                fim=_texto_obrigatorio(item.get("fim"), f"fim da regra '{identificador}'"),
                excecoes=excecoes,
                so_quando_grupo=grupos,
                meta_percentual=meta_regra,
                faixas_atraso=faixas_atraso_regra,
            )
        )
    return PrazosPerfil(
        FeriadosPerfil(nacionais=nacionais, extras=tuple(extras), regiao=regiao),
        meta,
        tuple(regras),
        meta_cronograma,
        faixas_atraso,
    )


def _faixas_atraso_prazo(dados: Any, campo: str) -> tuple[FaixaAtraso, ...] | None:
    if dados is None:
        return None
    if not isinstance(dados, (list, tuple)):
        raise ErroPerfil(f"'{campo}' precisa ser uma lista.")

    faixas: list[FaixaAtraso] = []
    ultimo_limite = 0
    limite_sem_fim_visto = False
    for posicao, item in enumerate(dados, start=1):
        campo_faixa = f"{campo}[{posicao}]"
        if not isinstance(item, Mapping):
            raise ErroPerfil(f"{campo_faixa} precisa ser um objeto.")
        if "ate_dias" not in item:
            raise ErroPerfil(f"{campo_faixa} precisa informar 'ate_dias'.")
        ate_dias = item.get("ate_dias")
        if ate_dias is None:
            if posicao != len(dados):
                raise ErroPerfil(f"'ate_dias: null' só pode aparecer na última faixa de '{campo}'.")
            limite_sem_fim_visto = True
        else:
            if isinstance(ate_dias, bool) or not isinstance(ate_dias, int) or ate_dias < 1:
                raise ErroPerfil(f"'ate_dias' em {campo_faixa} precisa ser inteiro maior ou igual a 1 ou null.")
            if limite_sem_fim_visto or ate_dias <= ultimo_limite:
                raise ErroPerfil(f"Os limites de '{campo}' precisam ser crescentes.")
            ultimo_limite = ate_dias
        faixas.append(
            FaixaAtraso(
                ate_dias=ate_dias,
                rotulo=_texto_obrigatorio(item.get("rotulo"), f"rótulo em {campo_faixa}"),
            )
        )
    return tuple(faixas)


def _meta_percentual_prazo(valor: Any, campo: str, *, permite_none: bool = False) -> float | None:
    if permite_none and valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not 0 <= valor <= 100:
        raise ErroPerfil(f"'{campo}' precisa ser um número entre 0 e 100.")
    return float(valor)


def _excecoes_prazo(dados: Any, identificador: str) -> tuple[ExcecaoPrazo, ...]:
    if not isinstance(dados, (list, tuple)):
        raise ErroPerfil(f"'excecoes' de '{identificador}' precisa ser uma lista.")
    excecoes: list[ExcecaoPrazo] = []
    siglas_vistas: set[str] = set()
    for posicao, item in enumerate(dados, start=1):
        campo = f"excecoes[{posicao}] de '{identificador}'"
        if not isinstance(item, Mapping):
            raise ErroPerfil(f"{campo} precisa ser um objeto.")
        siglas_dados = item.get("siglas")
        if not isinstance(siglas_dados, (list, tuple)) or not siglas_dados:
            raise ErroPerfil(f"'siglas' em {campo} precisa ser uma lista não vazia.")
        siglas = tuple(_texto_obrigatorio(sigla, f"sigla em {campo}") for sigla in siglas_dados)
        dias = item.get("dias")
        if isinstance(dias, bool) or not isinstance(dias, int) or dias < 1:
            raise ErroPerfil(f"'dias' em {campo} precisa ser inteiro maior ou igual a 1.")
        for sigla in siglas:
            chave = sigla.casefold()
            if chave in siglas_vistas:
                raise ErroPerfil(f"Sigla repetida ou ambígua em exceções de '{identificador}': '{sigla}'.")
            siglas_vistas.add(chave)
        excecoes.append(ExcecaoPrazo(siglas=siglas, dias=dias))
    return tuple(excecoes)


def _data_prazo(valor: Any, campo: str) -> date:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor)
        except ValueError as erro:
            raise ValueError(f"'data' em {campo} precisa estar no formato AAAA-MM-DD.") from erro
    raise ValueError(f"'data' em {campo} precisa estar no formato AAAA-MM-DD.")


def _estrutura_de_dict(dados: Any) -> EstruturaCodigo:
    if not isinstance(dados, Mapping):
        raise ErroPerfil("O perfil precisa definir 'codigo' como objeto.")
    partes_brutas = dados.get("segmentos")
    if not isinstance(partes_brutas, (list, tuple)) or not partes_brutas:
        raise ErroPerfil("'codigo.segmentos' precisa conter segmentos e separadores.")
    partes: list[ParteCodigo] = []
    for posicao, parte in enumerate(partes_brutas, start=1):
        if not isinstance(parte, Mapping):
            raise ErroPerfil(f"Item {posicao} de 'codigo.segmentos' precisa ser um objeto.")
        if "sep" in parte or "separador" in parte:
            texto = parte.get("sep", parte.get("separador"))
            if not isinstance(texto, str) or not texto:
                raise ErroPerfil(f"Separador inválido na posição {posicao}.")
            partes.append(Separador(texto))
            continue
        nome = _texto_obrigatorio(parte.get("nome"), f"nome do segmento {posicao}")
        rotulo = str(parte.get("rotulo") or nome)
        padrao = parte.get("padrao_regex", parte.get("formato", parte.get("regex")))
        if not isinstance(padrao, str) or not padrao:
            raise ErroPerfil(f"Segmento '{nome}' precisa informar 'padrao_regex'.")
        try:
            re.compile(padrao, re.IGNORECASE)
        except re.error as erro:
            raise ErroPerfil(f"Regex inválida no segmento '{nome}': {erro}.") from erro
        valores_brutos = parte.get("valores")
        if valores_brutos is not None and not isinstance(valores_brutos, Mapping):
            raise ErroPerfil(f"'valores' do segmento '{nome}' precisa ser um objeto.")
        obrigatorio = parte.get("obrigatorio", True)
        if not isinstance(obrigatorio, bool):
            raise ErroPerfil(f"'obrigatorio' do segmento '{nome}' precisa ser booleano.")
        partes.append(
            Segmento(
                nome=nome,
                rotulo=rotulo,
                padrao_regex=padrao,
                valores=(valores_brutos if valores_brutos is None else {
                    str(chave): str(valor) for chave, valor in valores_brutos.items()
                }),
                obrigatorio=obrigatorio,
            )
        )
    campos = [parte for parte in partes if isinstance(parte, Segmento)]
    nomes = [campo.nome for campo in campos]
    duplicados = sorted({nome for nome in nomes if nomes.count(nome) > 1})
    if duplicados:
        raise ErroPerfil(f"Nomes de segmento repetidos: {', '.join(duplicados)}.")
    if not campos:
        raise ErroPerfil("O código precisa ter pelo menos um segmento.")
    if isinstance(partes[0], Separador) or isinstance(partes[-1], Separador):
        raise ErroPerfil("A lista de código não pode começar nem terminar com separador.")
    for anterior, atual in zip(partes, partes[1:]):
        if isinstance(anterior, Separador) and isinstance(atual, Separador):
            raise ErroPerfil("A lista de código não pode ter separadores consecutivos.")

    revisao_no_codigo = bool(dados.get("revisao_no_codigo", False))
    segmento_revisao = dados.get(
        "segmento_revisao", dados.get("revisao_segmento")
    )
    if revisao_no_codigo:
        segmento_revisao = segmento_revisao or ("revisao" if "revisao" in nomes else None)
        if segmento_revisao not in nomes:
            raise ErroPerfil("Revisão no código exige um segmento de revisão existente.")
    elif segmento_revisao is not None:
        raise ErroPerfil("Informe 'segmento_revisao' apenas quando revisao_no_codigo for verdadeiro.")

    identidade_bruta = dados.get("segmentos_identidade")
    if identidade_bruta is None:
        identidade = [nome for nome in nomes if nome != segmento_revisao]
    elif isinstance(identidade_bruta, (list, tuple)):
        identidade = [str(nome) for nome in identidade_bruta]
    else:
        raise ErroPerfil("'segmentos_identidade' precisa ser uma lista de nomes.")
    desconhecidos = [nome for nome in identidade if nome not in nomes]
    if desconhecidos:
        raise ErroPerfil(f"Segmentos de identidade desconhecidos: {', '.join(desconhecidos)}.")
    if len(set(identidade)) != len(identidade):
        raise ErroPerfil("'segmentos_identidade' contém nomes repetidos.")
    if segmento_revisao in identidade:
        raise ErroPerfil("O segmento de revisão não pode fazer parte da identidade-base.")
    if not identidade:
        raise ErroPerfil("Informe ao menos um segmento para formar a identidade-base.")

    restricoes = _restricoes_de_dict(dados.get("restricoes", dados.get("restricoes_segmentos", ())))
    conhecidos = set(nomes)
    for regra in restricoes:
        if regra.se_segmento not in conhecidos or regra.entao_segmento not in conhecidos:
            raise ErroPerfil(
                f"Restrição referencia segmento inexistente: '{regra.se_segmento}' ou '{regra.entao_segmento}'."
            )
        if not regra.em:
            raise ErroPerfil("Restrição precisa informar ao menos um valor permitido em 'em'.")
    return EstruturaCodigo(
        segmentos=tuple(partes),
        revisao_no_codigo=revisao_no_codigo,
        segmento_revisao=segmento_revisao,
        segmentos_identidade=tuple(identidade),
        restricoes=restricoes,
    )


def _restricoes_de_dict(dados: Any) -> tuple[Restricao, ...]:
    if dados is None:
        return ()
    if not isinstance(dados, (list, tuple)):
        raise ErroPerfil("'restricoes' precisa ser uma lista.")
    regras: list[Restricao] = []
    for posicao, regra in enumerate(dados, start=1):
        if not isinstance(regra, Mapping):
            raise ErroPerfil(f"Restrição {posicao} precisa ser um objeto.")
        condicionais = ["se_segmento", "igual_a", "entao_segmento", "em"]
        ausentes = [campo for campo in condicionais if campo not in regra]
        if ausentes:
            raise ErroPerfil(f"Restrição {posicao} sem campos: {', '.join(ausentes)}.")
        permitidos = regra["em"]
        if not isinstance(permitidos, (list, tuple)):
            raise ErroPerfil(f"O campo 'em' da restrição {posicao} precisa ser uma lista.")
        regras.append(
            Restricao(
                se_segmento=str(regra["se_segmento"]),
                igual_a=str(regra["igual_a"]),
                entao_segmento=str(regra["entao_segmento"]),
                em=tuple(str(valor) for valor in permitidos),
            )
        )
    return tuple(regras)


def _validar_series(emissao: RegraEmissao) -> None:
    definicoes = [emissao.revisao.preliminar, emissao.revisao.original]
    if emissao.revisao.reabertura:
        definicoes.append(emissao.revisao.reabertura)
    if emissao.versao:
        definicoes.append(emissao.versao)
    for definicao in definicoes:
        try:
            criar_serie(
                definicao.nome,
                inicio=definicao.inicio,
                proibidas=definicao.proibidas,
            )
        except (TypeError, ValueError) as erro:
            raise ErroPerfil(f"Série inválida '{definicao.nome}': {erro}") from erro


def _data(valor: Any) -> date:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor)
        except ValueError as erro:
            raise ErroPerfil("'vigencia_inicio' deve estar no formato AAAA-MM-DD.") from erro
    raise ErroPerfil("O perfil precisa informar 'vigencia_inicio' como data AAAA-MM-DD.")


def _texto_obrigatorio(valor: Any, campo: str) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise ErroPerfil(f"O perfil precisa informar '{campo}'.")
    return valor.strip()
