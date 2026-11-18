"""Modelo imutável e validação dos perfis declarativos de contrato."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping
import re

from .ciclo import (
    CicloAnalise,
    RegraEmissao,
    ciclo_analise_de_dict,
    regra_emissao_de_dict,
)
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
class PerfilContrato:
    nome: str
    versao: str
    vigencia_inicio: date
    codigo: EstruturaCodigo
    emissao: RegraEmissao
    analise: CicloAnalise


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
        return PerfilContrato(nome, versao, vigencia, codigo, emissao, analise)
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
