"""Calendário de feriados para as regras de prazo dos perfis."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
import csv
import io
import unicodedata


@dataclass(frozen=True)
class FeriadoExtra:
    data: date
    nome: str


@dataclass(frozen=True)
class FeriadoCalculado:
    data: date
    nome: str
    abrangencia: str
    uf: str
    municipio: str


@dataclass(frozen=True)
class ErroLinhaFeriado:
    linha: int
    mensagem: str


@dataclass(frozen=True)
class ResultadoLeituraFeriados:
    feriados: tuple[FeriadoExtra, ...]
    erros: tuple[ErroLinhaFeriado, ...]


def feriados_nacionais(ano: int) -> tuple[date, ...]:
    """Retorna feriados nacionais obrigatórios, sem pontos facultativos."""
    if isinstance(ano, bool) or not isinstance(ano, int) or not 1 <= ano <= 9999:
        raise ValueError("O ano precisa ser um inteiro entre 1 e 9999.")

    fixos = [
        date(ano, 1, 1),
        date(ano, 4, 21),
        date(ano, 5, 1),
        date(ano, 9, 7),
        date(ano, 10, 12),
        date(ano, 11, 2),
        date(ano, 11, 15),
        date(ano, 12, 25),
    ]
    if ano >= 2024:
        fixos.append(date(ano, 11, 20))
    pascoa = _pascoa(ano)
    fixos.append(pascoa - timedelta(days=2))
    return tuple(sorted(fixos))


def feriados_acervo(
    ano: int,
    regras: Iterable[Mapping[str, Any]],
    *,
    uf: str,
    municipio: str,
) -> tuple[date, ...]:
    """Retorna as datas do acervo que se aplicam à região no ano informado."""
    return tuple(
        item.data
        for item in feriados_acervo_detalhados(
            ano, regras, uf=uf, municipio=municipio
        )
    )


def feriados_acervo_detalhados(
    ano: int,
    regras: Iterable[Mapping[str, Any]],
    *,
    uf: str,
    municipio: str,
) -> tuple[FeriadoCalculado, ...]:
    """Calcula datas e metadados do acervo sem depender de modelos Django."""
    _validar_ano(ano)
    uf_normalizada = _normalizar_regiao(uf)
    municipio_normalizado = _normalizar_regiao(municipio)
    if not uf_normalizada or not municipio_normalizado:
        return ()

    calculados: list[FeriadoCalculado] = []
    for posicao, regra in enumerate(regras, start=1):
        if not isinstance(regra, Mapping):
            raise ValueError(f"A regra {posicao} do acervo precisa ser um objeto.")
        abrangencia = regra.get("abrangencia")
        uf_regra = regra.get("uf")
        municipio_regra = regra.get("municipio", "") or ""
        if _normalizar_regiao(uf_regra) != uf_normalizada:
            continue
        if abrangencia == "estadual":
            if str(municipio_regra).strip():
                continue
        elif abrangencia == "municipal":
            if _normalizar_regiao(municipio_regra) != municipio_normalizado:
                continue
        else:
            raise ValueError(f"Abrangência inválida na regra {posicao} do acervo.")

        inicio = regra.get("vigencia_de")
        fim = regra.get("vigencia_ate")
        if inicio is not None and (isinstance(inicio, bool) or not isinstance(inicio, int)):
            raise ValueError(f"'vigencia_de' inválida na regra {posicao} do acervo.")
        if fim is not None and (isinstance(fim, bool) or not isinstance(fim, int)):
            raise ValueError(f"'vigencia_ate' inválida na regra {posicao} do acervo.")
        if (inicio is not None and ano < inicio) or (fim is not None and ano > fim):
            continue

        data = data_feriado_acervo(regra, ano)
        if data is not None:
            calculados.append(
                FeriadoCalculado(
                    data=data,
                    nome=str(regra.get("nome", "")).strip(),
                    abrangencia=abrangencia,
                    uf=str(uf_regra).strip().upper(),
                    municipio=str(municipio_regra).strip(),
                )
            )
    return tuple(sorted(calculados, key=lambda item: (item.data, item.nome.casefold())))


def data_feriado_acervo(regra: Mapping[str, Any], ano: int) -> date | None:
    """Calcula uma ocorrência anual; uma regra fixa em 29/02 só ocorre em anos bissextos."""
    _validar_ano(ano)
    tipo = regra.get("tipo_regra")
    if tipo == "fixa":
        dia = regra.get("dia")
        mes = regra.get("mes")
        if any(isinstance(valor, bool) or not isinstance(valor, int) for valor in (dia, mes)):
            raise ValueError("Uma regra fixa precisa informar dia e mês inteiros.")
        try:
            return date(ano, mes, dia)
        except ValueError:
            if mes == 2 and dia == 29:
                return None
            raise ValueError("A data fixa do acervo é inválida.") from None
    if tipo == "pascoa":
        deslocamento = regra.get("deslocamento_pascoa")
        if isinstance(deslocamento, bool) or not isinstance(deslocamento, int):
            raise ValueError("Uma regra móvel precisa informar deslocamento_pascoa inteiro.")
        return _pascoa(ano) + timedelta(days=deslocamento)
    raise ValueError("'tipo_regra' do acervo precisa ser 'fixa' ou 'pascoa'.")


def _validar_ano(ano: int) -> None:
    if isinstance(ano, bool) or not isinstance(ano, int) or not 1 <= ano <= 9999:
        raise ValueError("O ano precisa ser um inteiro entre 1 e 9999.")


def _normalizar_regiao(valor: Any) -> str:
    if not isinstance(valor, str):
        return ""
    sem_acentos = unicodedata.normalize("NFKD", valor.strip().casefold())
    sem_marcas = "".join(
        caractere
        for caractere in sem_acentos
        if not unicodedata.combining(caractere)
    )
    return " ".join(sem_marcas.split())


def ler_feriados_extras(caminho: str | Path) -> ResultadoLeituraFeriados:
    """Lê CSV ou XLSX com data e nome; erros de arquivo/linha retornam como dados."""
    arquivo = Path(caminho)
    try:
        if arquivo.suffix.casefold() == ".csv":
            linhas = _ler_csv(arquivo)
        elif arquivo.suffix.casefold() == ".xlsx":
            linhas = _ler_xlsx(arquivo)
        else:
            return ResultadoLeituraFeriados(
                (), (ErroLinhaFeriado(0, "Formato não suportado; use CSV ou XLSX."),)
            )
    except Exception as erro:
        return ResultadoLeituraFeriados(
            (), (ErroLinhaFeriado(0, f"Não foi possível ler o arquivo: {erro}"),)
        )

    feriados: list[FeriadoExtra] = []
    erros: list[ErroLinhaFeriado] = []
    for numero, linha in enumerate(linhas, start=1):
        if not linha or all(valor is None or str(valor).strip() == "" for valor in linha):
            continue
        data_bruta = linha[0] if len(linha) > 0 else None
        nome_bruto = linha[1] if len(linha) > 1 else None
        if numero == 1 and isinstance(data_bruta, str) and data_bruta.strip().casefold() in {
            "data", "date"
        }:
            continue
        try:
            data = _converter_data(data_bruta)
            nome = str(nome_bruto).strip() if nome_bruto is not None else ""
            if not nome:
                raise ValueError("nome vazio")
        except (TypeError, ValueError) as erro:
            detalhe = "data ou nome inválido" if not str(erro) else str(erro)
            erros.append(ErroLinhaFeriado(numero, detalhe))
            continue
        feriados.append(FeriadoExtra(data, nome))
    return ResultadoLeituraFeriados(tuple(feriados), tuple(erros))


def _ler_csv(caminho: Path) -> list[list[Any]]:
    try:
        conteudo = caminho.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        conteudo = caminho.read_text(encoding="cp1252")
    amostra = conteudo[:2048]
    try:
        delimitador = csv.Sniffer().sniff(amostra, delimiters=",;	").delimiter
    except csv.Error:
        delimitador = ","
    return [list(linha) for linha in csv.reader(io.StringIO(conteudo), delimiter=delimitador)]


def _ler_xlsx(caminho: Path) -> list[list[Any]]:
    from openpyxl import load_workbook

    pasta = load_workbook(caminho, read_only=True, data_only=True)
    try:
        planilha = pasta.active
        return [list(linha) for linha in planilha.iter_rows(values_only=True)]
    finally:
        pasta.close()


def _converter_data(valor: Any) -> date:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if not isinstance(valor, str):
        raise ValueError("data inválida")
    texto = valor.strip()
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            pass
    raise ValueError("data inválida; use dd/mm/aaaa ou AAAA-MM-DD")


def _pascoa(ano: int) -> date:
    """Calcula a data gregoriana da Páscoa pelo algoritmo de Meeus/Jones/Butcher."""
    a = ano % 19
    b, c = divmod(ano, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return date(ano, mes, dia)
