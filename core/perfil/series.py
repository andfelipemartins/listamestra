"""Séries finitas de revisão usadas pelos perfis de contrato."""

from __future__ import annotations

from dataclasses import dataclass
import re


class SerieRevisao:
    def primeira(self) -> str:
        raise NotImplementedError

    def proxima(self, atual: str) -> str:
        raise NotImplementedError

    def valida(self, valor: str) -> bool:
        raise NotImplementedError


@dataclass(frozen=True)
class SerieNumerica(SerieRevisao):
    inicio: int = 1

    def primeira(self) -> str:
        return str(self.inicio)

    def proxima(self, atual: str) -> str:
        if not self.valida(atual):
            raise ValueError(f"Revisão numérica inválida: '{atual}'.")
        return str(int(atual) + 1)

    def valida(self, valor: str) -> bool:
        return bool(re.fullmatch(r"\d+", str(valor))) and int(valor) >= self.inicio


@dataclass(frozen=True)
class SerieLetras(SerieRevisao):
    proibidas: tuple[str, ...] = ()
    inicio: str = "A"

    def __post_init__(self) -> None:
        object.__setattr__(self, "proibidas", tuple(letra.upper() for letra in self.proibidas))
        object.__setattr__(self, "inicio", self.inicio.upper())
        if not self.valida(self.inicio):
            raise ValueError(f"Início inválido para série de letras: '{self.inicio}'.")

    @property
    def alfabeto(self) -> str:
        return "".join(letra for letra in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if letra not in self.proibidas)

    def primeira(self) -> str:
        return self.inicio

    def proxima(self, atual: str) -> str:
        atual = str(atual).upper()
        if not self.valida(atual):
            raise ValueError(f"Revisão alfabética inválida: '{atual}'.")
        indice = _para_indice(atual, self.alfabeto) + 1
        return _de_indice(indice, self.alfabeto)

    def valida(self, valor: str) -> bool:
        valor = str(valor).upper()
        return bool(valor) and all(letra in self.alfabeto for letra in valor)


@dataclass(frozen=True)
class SerieZeroDepoisLetras(SerieRevisao):
    proibidas: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "proibidas", tuple(letra.upper() for letra in self.proibidas))

    @property
    def letras(self) -> SerieLetras:
        return SerieLetras(proibidas=self.proibidas)

    def primeira(self) -> str:
        return "0"

    def proxima(self, atual: str) -> str:
        atual = str(atual).upper()
        if atual == "0":
            return self.letras.primeira()
        if not self.valida(atual):
            raise ValueError(f"Revisão inválida para série 0 e letras: '{atual}'.")
        return self.letras.proxima(atual)

    def valida(self, valor: str) -> bool:
        return str(valor) == "0" or self.letras.valida(str(valor))


@dataclass(frozen=True)
class SerieLetraMaisNumero(SerieRevisao):
    proibidas: tuple[str, ...] = ()
    inicio: str = "A"
    inicio_numero: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "proibidas", tuple(letra.upper() for letra in self.proibidas))
        object.__setattr__(self, "inicio", self.inicio.upper())
        if not SerieLetras(self.proibidas).valida(self.inicio):
            raise ValueError(f"Prefixo inválido para série letra + número: '{self.inicio}'.")

    @property
    def inicio_letra(self) -> str:
        return self.inicio

    def primeira(self) -> str:
        return f"{self.inicio}{self.inicio_numero}"

    def primeira_com_prefixo(self, prefixo: str) -> str:
        prefixo = str(prefixo).upper()
        if not SerieLetras(self.proibidas).valida(prefixo):
            raise ValueError(f"Prefixo inválido para reabertura: '{prefixo}'.")
        return f"{prefixo}{self.inicio_numero}"

    def proxima(self, atual: str) -> str:
        atual = str(atual).upper()
        match = re.fullmatch(r"([A-Z]+)(\d+)", atual)
        if not match or not self.valida(atual):
            raise ValueError(f"Revisão letra + número inválida: '{atual}'.")
        return f"{match.group(1)}{int(match.group(2)) + 1}"

    def valida(self, valor: str) -> bool:
        match = re.fullmatch(r"([A-Z]+)(\d+)", str(valor).upper())
        return bool(
            match
            and SerieLetras(self.proibidas).valida(match.group(1))
            and int(match.group(2)) >= self.inicio_numero
        )


def criar_serie(
    nome: str,
    *,
    inicio: str | int | None = None,
    proibidas: tuple[str, ...] = (),
) -> SerieRevisao:
    canonico = nome.strip().casefold()
    if canonico == "numerica":
        return SerieNumerica(inicio=int(inicio if inicio is not None else 1))
    if canonico == "letras":
        return SerieLetras(proibidas=proibidas, inicio=str(inicio or "A"))
    if canonico == "zero_depois_letras":
        return SerieZeroDepoisLetras(proibidas=proibidas)
    if canonico == "letra_mais_numero":
        valor = str(inicio or "A")
        match = re.fullmatch(r"([A-Z]+)(\d+)?", valor.upper())
        if not match:
            raise ValueError(f"Início inválido para série letra + número: '{valor}'.")
        return SerieLetraMaisNumero(
            proibidas=proibidas,
            inicio=match.group(1),
            inicio_numero=int(match.group(2) or 1),
        )
    raise ValueError(f"Série de revisão desconhecida: '{nome}'.")


def _para_indice(valor: str, alfabeto: str) -> int:
    base = len(alfabeto)
    resultado = 0
    for letra in valor:
        resultado = resultado * base + alfabeto.index(letra) + 1
    return resultado


def _de_indice(indice: int, alfabeto: str) -> str:
    base = len(alfabeto)
    resultado = ""
    while indice:
        indice, resto = divmod(indice - 1, base)
        resultado = alfabeto[resto] + resultado
    return resultado
