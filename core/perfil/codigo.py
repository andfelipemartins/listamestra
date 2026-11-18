"""Interpretação e montagem de códigos a partir de um perfil declarativo."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping
import re

from .modelo import ErroPerfil, PerfilContrato, Restricao, Segmento, Separador


@dataclass(frozen=True)
class CodigoInterpretado:
    original: str
    segmentos: Mapping[str, str]
    significados: Mapping[str, str]
    identificador_base: str
    revisao: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "segmentos", MappingProxyType(dict(self.segmentos)))
        object.__setattr__(self, "significados", MappingProxyType(dict(self.significados)))


@dataclass(frozen=True)
class ErroCodigo:
    original: str
    mensagem: str
    segmento: str | None = None


def interpretar(perfil: PerfilContrato, texto: str) -> CodigoInterpretado | ErroCodigo:
    original = texto if isinstance(texto, str) else str(texto)
    if not original.strip():
        return ErroCodigo(original, "Código vazio. Informe um código documental válido.")
    valor = original.strip().upper()
    padrao = _regex_perfil(perfil)
    correspondencia = padrao.fullmatch(valor)
    if correspondencia is None:
        return _diagnosticar_formato(perfil, valor, original)

    partes = {nome: trecho for nome, trecho in correspondencia.groupdict().items() if trecho is not None}
    canonicos: dict[str, str] = {}
    significados: dict[str, str] = {}
    for segmento in perfil.codigo.campos:
        if segmento.nome not in partes:
            continue
        trecho = partes[segmento.nome]
        canonico = _valor_canonico(segmento, trecho)
        if canonico is None:
            permitidos = ", ".join(segmento.valores) if segmento.valores else segmento.padrao_regex
            return ErroCodigo(
                original,
                f"Valor inválido para {segmento.rotulo} ('{trecho}'). Esperado: {permitidos}.",
                segmento.nome,
            )
        canonicos[segmento.nome] = canonico
        if segmento.valores is not None:
            rotulo = _rotulo_valor(segmento, canonico)
            if rotulo is not None:
                significados[segmento.nome] = rotulo

    erro_restricao = _validar_restricoes(perfil, canonicos, original)
    if erro_restricao:
        return erro_restricao
    base = _montar_partes(perfil, canonicos, set(perfil.codigo.segmentos_identidade))
    revisao = (
        canonicos.get(perfil.codigo.segmento_revisao)
        if perfil.codigo.revisao_no_codigo
        else None
    )
    return CodigoInterpretado(
        original=original,
        segmentos=canonicos,
        significados=significados,
        identificador_base=base,
        revisao=revisao,
    )


def montar(perfil: PerfilContrato, segmentos: Mapping[str, str]) -> str:
    valores: dict[str, str] = {}
    definicoes = {segmento.nome: segmento for segmento in perfil.codigo.campos}
    desconhecidos = set(segmentos) - set(definicoes)
    if desconhecidos:
        raise ValueError(f"Segmentos desconhecidos: {', '.join(sorted(desconhecidos))}.")
    for nome, segmento in definicoes.items():
        valor = segmentos.get(nome)
        if valor is None:
            if segmento.obrigatorio:
                raise ValueError(f"Falta informar o segmento obrigatório '{nome}'.")
            continue
        valor = str(valor).upper()
        try:
            corresponde = re.fullmatch(segmento.padrao_regex, valor, re.IGNORECASE)
        except re.error as erro:
            raise ErroPerfil(f"Regex inválida no segmento '{nome}': {erro}.") from erro
        if corresponde is None:
            raise ValueError(
                f"Valor '{valor}' inválido para {segmento.rotulo}. Esperado: {segmento.padrao_regex}."
            )
        canonico = _valor_canonico(segmento, valor)
        if canonico is None:
            permitidos = ", ".join(segmento.valores or {})
            raise ValueError(f"Valor '{valor}' inválido para {segmento.rotulo}. Permitidos: {permitidos}.")
        valores[nome] = canonico
    erro_restricao = _validar_restricoes(perfil, valores, "")
    if erro_restricao:
        raise ValueError(erro_restricao.mensagem)
    return _montar_partes(perfil, valores, set(definicoes))


def _regex_perfil(perfil: PerfilContrato) -> re.Pattern[str]:
    partes: list[str] = ["^"]
    for parte in perfil.codigo.segmentos:
        if isinstance(parte, Separador):
            partes.append(re.escape(parte.texto))
        else:
            opcional = "?" if not parte.obrigatorio else ""
            partes.append(f"(?P<{parte.nome}>{parte.padrao_regex}){opcional}")
    partes.append("$")
    try:
        return re.compile("".join(partes), re.IGNORECASE)
    except re.error as erro:
        raise ErroPerfil(f"Regex inválida no perfil: {erro}.") from erro


def _diagnosticar_formato(
    perfil: PerfilContrato, texto: str, original: str
) -> ErroCodigo:
    posicao = 0
    ultimo_segmento: str | None = None
    for indice, parte in enumerate(perfil.codigo.segmentos):
        restante = texto[posicao:]
        if isinstance(parte, Separador):
            if not texto.startswith(parte.texto.upper(), posicao):
                nome = _proximo_nome(perfil, indice + 1) or ultimo_segmento
                return ErroCodigo(
                    original,
                    f"Separador inválido após '{ultimo_segmento or 'início'}'. Esperado: '{parte.texto}'.",
                    nome,
                )
            posicao += len(parte.texto)
            continue
        ultimo_segmento = parte.nome
        if not restante and not parte.obrigatorio:
            continue
        try:
            correspondencia = re.match(parte.padrao_regex, restante, re.IGNORECASE)
        except re.error as erro:
            return ErroCodigo(original, f"Regex inválida no segmento '{parte.nome}': {erro}.", parte.nome)
        if correspondencia is None:
            # Uma falha em separador adjacente pode apontar o primeiro campo que não casou.
            return ErroCodigo(
                original,
                f"Segmento {parte.rotulo} inválido. Valor recebido: '{_trecho_ate_separador(restante, perfil, indice)}'. Esperado: {parte.padrao_regex}.",
                parte.nome,
            )
        trecho = correspondencia.group(0)
        if not parte.obrigatorio and not trecho:
            continue
        if _valor_canonico(parte, trecho) is None:
            permitidos = ", ".join(parte.valores) if parte.valores else parte.padrao_regex
            return ErroCodigo(
                original,
                f"Valor inválido para {parte.rotulo} ('{trecho}'). Esperado: {permitidos}.",
                parte.nome,
            )
        posicao += len(trecho)
    if posicao != len(texto):
        return ErroCodigo(
            original,
            f"Valor inesperado no segmento '{ultimo_segmento}': '{texto[posicao:]}'.",
            ultimo_segmento,
        )
    return ErroCodigo(original, "Código não corresponde à estrutura configurada.")


def _trecho_ate_separador(restante: str, perfil: PerfilContrato, indice: int) -> str:
    proximo = next(
        (p.texto for p in perfil.codigo.segmentos[indice + 1 :] if isinstance(p, Separador)),
        None,
    )
    if proximo:
        local = restante.find(proximo)
        if local >= 0:
            return restante[:local]
    return restante[:12]


def _proximo_nome(perfil: PerfilContrato, inicio: int) -> str | None:
    return next(
        (parte.nome for parte in perfil.codigo.segmentos[inicio:] if isinstance(parte, Segmento)),
        None,
    )


def _valor_canonico(segmento: Segmento, valor: str) -> str | None:
    if segmento.valores is None:
        return valor.upper()
    por_chave = {chave.upper(): chave for chave in segmento.valores}
    chave = por_chave.get(valor.upper())
    return chave


def _rotulo_valor(segmento: Segmento, valor: str) -> str | None:
    if segmento.valores is None:
        return None
    return segmento.valores.get(valor)


def _validar_restricoes(
    perfil: PerfilContrato, valores: Mapping[str, str], original: str
) -> ErroCodigo | None:
    for restricao in perfil.codigo.restricoes:
        condicao = valores.get(restricao.se_segmento)
        if condicao is None or condicao.upper() != restricao.igual_a.upper():
            continue
        encontrado = valores.get(restricao.entao_segmento)
        permitidos = {valor.upper() for valor in restricao.em}
        if encontrado is None or encontrado.upper() not in permitidos:
            return ErroCodigo(
                original,
                (
                    f"Restrição: quando {restricao.se_segmento}='{restricao.igual_a}', "
                    f"{restricao.entao_segmento} deve estar entre {', '.join(restricao.em)}."
                ),
                restricao.entao_segmento,
            )
    return None


def _montar_partes(
    perfil: PerfilContrato, valores: Mapping[str, str], incluidos: set[str]
) -> str:
    resultado = ""
    ultimo_campo: str | None = None
    separador_pendente: str | None = None
    for parte in perfil.codigo.segmentos:
        if isinstance(parte, Separador):
            if ultimo_campo is not None:
                separador_pendente = parte.texto
            continue
        if parte.nome not in incluidos or parte.nome not in valores:
            continue
        if ultimo_campo is not None and separador_pendente is not None:
            resultado += separador_pendente
        resultado += valores[parte.nome]
        ultimo_campo = parte.nome
        separador_pendente = None
    return resultado
