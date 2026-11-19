"""Leitura de planilhas de cronograma e comparação das previsões com emissões."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from io import StringIO
from typing import BinaryIO, Iterable, Mapping
import csv
import re
import unicodedata
import warnings
from zipfile import BadZipFile

from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.utils import timezone
from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel
from openpyxl.utils.exceptions import InvalidFileException

from core.perfil.codigo import ErroCodigo, interpretar
from documentos.models import Emissao
from .models import ImportacaoCronograma, ItemPrevisto, PrevisaoEmissao


CATEGORIAS = ("validas", "codigos_invalidos", "fora_do_id", "dados_invalidos")
_CABECALHOS_CODIGO = {
    "CODIGO",
    "CODIGO DO DOCUMENTO",
    "CODIGO DOCUMENTO",
    "IDENTIFICADOR",
    "IDENTIFICADOR DO DOCUMENTO",
}
_CABECALHOS_DATA = {
    "DATA",
    "DATA PREVISTA",
    "PREVISAO",
    "DATA DE EMISSAO",
}


@dataclass(frozen=True)
class LinhaCronograma:
    numero_linha: int
    codigo: str
    identificador_base: str
    data_prevista: date | None
    categoria: str
    mensagem: str = ""


@dataclass(frozen=True)
class PreviaCronograma:
    contrato_id: int
    perfil_id: int
    arquivo_nome: str
    linhas: tuple[LinhaCronograma, ...]

    @property
    def linhas_validas(self) -> int:
        return sum(linha.categoria == "validas" for linha in self.linhas)

    @property
    def linhas_recusadas(self) -> int:
        return len(self.linhas) - self.linhas_validas

    @property
    def contagens(self) -> dict[str, int]:
        return {categoria: sum(linha.categoria == categoria for linha in self.linhas) for categoria in CATEGORIAS}


class ErroFormatoCronograma(ValueError):
    """Arquivo de cronograma sem cabeçalhos reconhecidos ou ilegível."""


class ErroAplicacaoCronograma(ValueError):
    pass


def gerar_previa_cronograma(
    arquivo: BinaryIO,
    *,
    nome_arquivo: str,
    contrato_id: int,
    perfil_id: int,
    perfil,
    documentos_previstos: Mapping[str, object] | Iterable[str],
) -> PreviaCronograma:
    """Lê XLSX ou CSV, valida os códigos pelo perfil e não grava dados."""
    cabecalho, linhas_fonte = _ler_planilha(arquivo, nome_arquivo)
    indices = _indices_cabecalho(cabecalho)
    if "codigo" not in indices or "data" not in indices:
        raise ErroFormatoCronograma(
            "A planilha precisa ter uma coluna de código e uma de data prevista."
        )

    documentos = _mapear_previstos(documentos_previstos)
    linhas = []
    for numero_linha, valores in linhas_fonte:
        if not any(not _vazio(valor) for valor in valores):
            continue
        codigo = _texto(_valor_coluna(valores, indices["codigo"]))
        data_lida = _valor_coluna(valores, indices["data"])
        interpretado = interpretar(perfil, codigo)
        if isinstance(interpretado, ErroCodigo):
            linhas.append(LinhaCronograma(
                numero_linha, codigo, "", None, "codigos_invalidos",
                f"Código inválido: {interpretado.mensagem}",
            ))
            continue
        if interpretado.identificador_base not in documentos:
            linhas.append(LinhaCronograma(
                numero_linha, codigo, interpretado.identificador_base, None, "fora_do_id",
                "Documento não consta no ID vigente do contrato.",
            ))
            continue
        data_prevista = _data(data_lida)
        if data_prevista is None:
            linhas.append(LinhaCronograma(
                numero_linha, codigo, interpretado.identificador_base, None, "dados_invalidos",
                "Informe uma data prevista válida.",
            ))
            continue
        linhas.append(LinhaCronograma(
            numero_linha, codigo, interpretado.identificador_base, data_prevista, "validas"
        ))

    if not linhas:
        raise ErroFormatoCronograma("O arquivo não contém linhas de cronograma.")
    return PreviaCronograma(contrato_id, perfil_id, nome_arquivo, tuple(linhas))


@transaction.atomic
def aplicar_previa_cronograma(
    previa: PreviaCronograma,
    *,
    contrato,
    perfil_modelo,
    usuario=None,
) -> ImportacaoCronograma:
    if previa.contrato_id != contrato.pk or perfil_modelo.contrato_id != contrato.pk:
        raise ErroAplicacaoCronograma("A prévia, o perfil e o contrato precisam ser os mesmos.")
    if previa.perfil_id != perfil_modelo.pk:
        raise ErroAplicacaoCronograma("O perfil vigente mudou. Gere uma nova prévia.")

    ids_vigentes = set(ItemPrevisto.objects.filter(
        indice__contrato=contrato,
        indice__vigente=True,
        excluido=False,
    ).values_list("documento__identificador_base", flat=True))
    linhas_validas = [linha for linha in previa.linhas if linha.categoria == "validas"]
    if any(linha.identificador_base not in ids_vigentes for linha in linhas_validas):
        raise ErroAplicacaoCronograma("O ID vigente mudou. Gere uma nova prévia do cronograma.")

    importacao = ImportacaoCronograma.objects.create(
        contrato=contrato,
        arquivo_nome=previa.arquivo_nome,
        importado_por=usuario,
        linhas_validas=len(linhas_validas),
        linhas_recusadas=previa.linhas_recusadas,
    )
    for linha in linhas_validas:
        documento = contrato.documentos.filter(
            identificador_base=linha.identificador_base
        ).first()
        if documento is None:
            raise ErroAplicacaoCronograma("O documento não pertence mais ao contrato.")
        previsao = PrevisaoEmissao.objects.filter(
            contrato=contrato,
            documento=documento,
        ).first()
        if previsao is None:
            previsao = PrevisaoEmissao(
                contrato=contrato,
                documento=documento,
                data_prevista=linha.data_prevista,
                importacao=importacao,
            )
        else:
            previsao.data_prevista = linha.data_prevista
            previsao.importacao = importacao
        previsao._history_user = usuario
        previsao.save()
    return importacao


@dataclass(frozen=True)
class ResultadoPrazoCronograma:
    previsao: PrevisaoEmissao
    data_real: date | None
    status: str


def classificar_prazo_cronograma(
    data_prevista: date,
    data_real: date | None,
    *,
    hoje: date | None = None,
) -> str:
    hoje = hoje or timezone.localdate()
    if data_real is not None:
        return "no_prazo" if data_real <= data_prevista else "atrasado"
    return "vencido_sem_emissao" if data_prevista < hoje else "futuro"


def comparar_previsoes_cronograma(
    contrato,
    *,
    hoje: date | None = None,
) -> list[ResultadoPrazoCronograma]:
    """Compara cada previsão com a primeira emissão real conhecida do documento."""
    primeira_emissao = Emissao.objects.filter(
        documento_id=OuterRef("documento_id"),
        origem=Emissao.Origem.CLIENTE,
    ).order_by("data_emissao", "pk").values("data_emissao")[:1]
    previsoes = (
        PrevisaoEmissao.objects.filter(contrato=contrato)
        .select_related("documento", "importacao")
        .annotate(data_real=Subquery(primeira_emissao))
        .order_by("data_prevista", "documento__identificador_base")
    )
    hoje = hoje or timezone.localdate()
    return [
        ResultadoPrazoCronograma(
            previsao=previsao,
            data_real=previsao.data_real,
            status=classificar_prazo_cronograma(
                previsao.data_prevista,
                previsao.data_real,
                hoje=hoje,
            ),
        )
        for previsao in previsoes
    ]


def _ler_planilha(arquivo: BinaryIO, nome_arquivo: str):
    arquivo.seek(0)
    if nome_arquivo.lower().endswith(".csv"):
        try:
            conteudo = arquivo.read()
            if isinstance(conteudo, bytes):
                try:
                    conteudo = conteudo.decode("utf-8-sig")
                except UnicodeDecodeError:
                    conteudo = conteudo.decode("cp1252")
            amostra = conteudo[:8192]
            try:
                dialeto = csv.Sniffer().sniff(amostra, delimiters=";,\t")
            except csv.Error:
                dialeto = csv.excel
            linhas = list(csv.reader(StringIO(conteudo), dialeto))
        except (OSError, UnicodeError, csv.Error, TypeError) as erro:
            raise ErroFormatoCronograma(f"Não foi possível abrir o CSV: {erro}") from erro
        return _separar_cabecalho(linhas)

    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Workbook contains no default style")
            workbook = load_workbook(arquivo, read_only=True, data_only=True)
    except (BadZipFile, InvalidFileException, OSError, ValueError) as erro:
        raise ErroFormatoCronograma(f"Não foi possível abrir o arquivo Excel: {erro}") from erro
    try:
        worksheet = workbook.active
        valores = list(worksheet.iter_rows(values_only=True))
        for indice, linha in enumerate(valores):
            if any(not _vazio(valor) for valor in linha):
                cabecalho = list(linha)
                dados = [
                    (numero + 1, list(item))
                    for numero, item in enumerate(valores[indice + 1 :], start=indice + 1)
                ]
                return cabecalho, dados
        raise ErroFormatoCronograma("A planilha está vazia.")
    finally:
        workbook.close()


def _separar_cabecalho(linhas):
    for indice, linha in enumerate(linhas):
        if any(not _vazio(valor) for valor in linha):
            return list(linha), [
                (numero + 1, list(item))
                for numero, item in enumerate(linhas[indice + 1 :], start=indice + 1)
            ]
    raise ErroFormatoCronograma("O arquivo está vazio.")


def _indices_cabecalho(cabecalho):
    indices = {}
    for indice, nome in enumerate(cabecalho):
        normalizado = _normalizar_cabecalho(nome)
        if "codigo" not in indices and normalizado in _CABECALHOS_CODIGO:
            indices["codigo"] = indice
        if "data" not in indices and normalizado in _CABECALHOS_DATA:
            indices["data"] = indice
    return indices


def _mapear_previstos(documentos_previstos):
    if isinstance(documentos_previstos, Mapping):
        return {str(codigo).strip().upper(): documento for codigo, documento in documentos_previstos.items()}
    return {str(codigo).strip().upper(): None for codigo in documentos_previstos}


def _valor_coluna(valores, indice):
    return valores[indice] if indice < len(valores) else None


def _data(valor, epoch=None):
    if valor is None or _vazio(valor):
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, (int, float)):
        try:
            convertido = from_excel(valor, epoch=epoch) if epoch else from_excel(valor)
            if isinstance(convertido, datetime):
                return convertido.date()
            return convertido if isinstance(convertido, date) else None
        except (OverflowError, TypeError, ValueError):
            return None
    texto = _texto(valor)
    for formato in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(texto).date()
    except ValueError:
        return None


def _texto(valor):
    return "" if valor is None else str(valor).strip()


def _vazio(valor):
    return valor is None or (isinstance(valor, str) and not valor.strip())


def _normalizar_cabecalho(valor):
    sem_acentos = "".join(
        caractere
        for caractere in unicodedata.normalize("NFD", str(valor or ""))
        if unicodedata.category(caractere) != "Mn"
    )
    return re.sub(r"[^A-Z0-9]+", " ", sem_acentos.upper()).strip()
