"""Leitura e aplicação da planilha genérica de situação documental."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO, StringIO
from pathlib import Path
from typing import Mapping
import csv
import re
import unicodedata
import warnings
from zipfile import BadZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.utils.datetime import from_excel
from openpyxl.utils.exceptions import InvalidFileException

from core.perfil.codigo import ErroCodigo, interpretar


CABECALHOS = {
    "codigo": "Código",
    "revisao": "Revisão",
    "situacao": "Situação",
    "data": "Data",
    "observacao": "Observação",
    "grd": "GRD",
    "data_envio": "Data de envio",
    "data_retorno": "Data de retorno",
}
CAMPOS_SEM_DESTINO = {
    "grd": "GRD",
    "data_envio": "Data de envio",
}


@dataclass(frozen=True)
class CampoIgnorado:
    nome: str
    valor: str


@dataclass(frozen=True)
class LinhaSituacaoPadrao:
    numero_linha: int
    codigo: str
    revisao: str
    situacao: str
    data_analise: date | None
    documento_id: int | None = None
    emissao_id: int | None = None
    observacao: str = ""
    observacao_informada: bool = False
    data_informada: bool = False
    situacao_antes: str = ""
    situacao_depois: str = ""
    categoria: str = ""
    mensagem: str = ""
    aviso: str = ""
    campos_ignorados: tuple[CampoIgnorado, ...] = ()

    @property
    def valida(self) -> bool:
        return not self.categoria


@dataclass(frozen=True)
class PreviaSituacaoPadrao:
    contrato_id: int
    perfil_id: int
    data_importacao: date
    arquivo_nome: str
    cabecalhos: tuple[str, ...]
    linhas: tuple[LinhaSituacaoPadrao, ...]
    documentos_encontrados: int
    documentos_nao_encontrados: int
    codigos_invalidos: int
    situacoes_invalidas: int

    @property
    def total_linhas(self) -> int:
        return len(self.linhas)

    @property
    def linhas_invalidas(self) -> int:
        return sum(not linha.valida for linha in self.linhas)

    @property
    def linhas_validas(self) -> int:
        return sum(linha.valida for linha in self.linhas)

    @property
    def mudancas_situacao(self) -> int:
        return sum(
            linha.valida
            and linha.situacao
            and _normalizar(linha.situacao_antes) != _normalizar(linha.situacao_depois)
            for linha in self.linhas
        )


class ErroFormatoSituacaoPadrao(ValueError):
    """Arquivo ilegível ou sem a coluna obrigatória de código."""


def gerar_modelo_situacao_padrao() -> bytes:
    workbook = Workbook()
    planilha = workbook.active
    planilha.title = "Situação"
    planilha.append(list(CABECALHOS.values()))
    instrucoes = workbook.create_sheet("Instruções")
    instrucoes.append(["Planilha padrão de situação"])
    instrucoes.append(["Preencha o código do documento. As demais colunas são opcionais."])
    instrucoes.append(["Revisão vazia usa a última revisão; Data vazia usa a data de retorno, se preenchida, ou a data da importação."])
    instrucoes.append(["Se Data e Data de retorno forem diferentes, vale Data e a prévia avisa. GRD e Data de envio são aceitas, mas ignoradas."])
    conteudo = BytesIO()
    workbook.save(conteudo)
    workbook.close()
    return conteudo.getvalue()


def gerar_previa_situacao_padrao(
    arquivo,
    *,
    nome_arquivo: str,
    contrato_id: int,
    perfil_id: int,
    perfil,
    documentos_existentes: Mapping[str, Mapping[str, object]],
    data_importacao: date | None = None,
) -> PreviaSituacaoPadrao:
    data_importacao = data_importacao or date.today()
    cabecalho, registros = _ler_registros(arquivo, nome_arquivo)
    existentes = {_normalizar_codigo(chave): valor for chave, valor in documentos_existentes.items()}
    vocabulario = _vocabulario_situacoes(perfil)
    encontrados: set[int] = set()
    nao_encontrados: set[str] = set()
    linhas: list[LinhaSituacaoPadrao] = []
    situacoes_simuladas: dict[int, str] = {}

    for numero, valores in registros:
        codigo = _texto(_valor_coluna(valores, cabecalho, "codigo"))
        revisao_informada = _texto(_valor_coluna(valores, cabecalho, "revisao")).upper()
        situacao_bruta = _texto(_valor_coluna(valores, cabecalho, "situacao"))
        data_bruta = _valor_coluna(valores, cabecalho, "data")
        data_retorno_bruta = _valor_coluna(valores, cabecalho, "data_retorno")
        observacao_bruta = _valor_coluna(valores, cabecalho, "observacao")
        dados_ignorados = tuple(
            CampoIgnorado(CABECALHOS[chave], _texto(_valor_coluna(valores, cabecalho, chave)))
            for chave in CAMPOS_SEM_DESTINO
            if chave in cabecalho and not _vazio(_valor_coluna(valores, cabecalho, chave))
        )

        base = {
            "numero_linha": numero,
            "codigo": codigo,
            "revisao": revisao_informada,
            "situacao": situacao_bruta,
            "data_analise": None,
            "campos_ignorados": dados_ignorados,
        }
        if not codigo:
            linhas.append(LinhaSituacaoPadrao(**base, categoria="codigo_ausente", mensagem="Código vazio."))
            continue

        interpretado = interpretar(perfil, codigo)
        if isinstance(interpretado, ErroCodigo):
            linhas.append(
                LinhaSituacaoPadrao(
                    **base,
                    categoria="codigos_invalidos",
                    mensagem=interpretado.mensagem,
                )
            )
            continue

        registro = existentes.get(_normalizar_codigo(interpretado.identificador_base))
        if registro is None:
            nao_encontrados.add(_normalizar_codigo(interpretado.identificador_base))
            linhas.append(
                LinhaSituacaoPadrao(
                    **base,
                    categoria="documento_nao_encontrado",
                    mensagem="Documento não encontrado neste contrato.",
                )
            )
            continue

        documento_id = int(registro["id"])
        encontrados.add(documento_id)
        emissoes = list(registro.get("emissoes", ()))
        emissao = _selecionar_emissao(emissoes, revisao_informada)
        if emissao is None:
            mensagem = (
                f"A revisão {revisao_informada} não existe para este documento."
                if revisao_informada
                else "O documento não tem revisão registrada."
            )
            linhas.append(
                LinhaSituacaoPadrao(
                    **base,
                    categoria="revisao_nao_encontrada",
                    mensagem=mensagem,
                    documento_id=documento_id,
                )
            )
            continue

        situacao = ""
        if situacao_bruta:
            situacao = vocabulario.get(_normalizar(situacao_bruta), "")
            if not situacao:
                linhas.append(
                    LinhaSituacaoPadrao(
                        **base,
                        categoria="situacoes_invalidas",
                        mensagem=f"A situação '{situacao_bruta}' não existe no perfil deste contrato.",
                        documento_id=documento_id,
                    )
                )
                continue

        data_informada = not _vazio(data_bruta) or not _vazio(data_retorno_bruta)
        aviso = ""
        try:
            if not _vazio(data_bruta):
                data_analise = _data(data_bruta)
                if not _vazio(data_retorno_bruta):
                    try:
                        data_retorno = _data(data_retorno_bruta)
                    except ValueError:
                        aviso = "Data de retorno inválida; foi considerada a coluna Data."
                    else:
                        if data_retorno != data_analise:
                            aviso = "Data e Data de retorno são diferentes; foi considerada a coluna Data."
            elif not _vazio(data_retorno_bruta):
                data_analise = _data(data_retorno_bruta)
            else:
                data_analise = data_importacao
        except ValueError as erro:
            linhas.append(
                LinhaSituacaoPadrao(
                    **base,
                    categoria="data_invalida",
                    mensagem=str(erro),
                    documento_id=documento_id,
                )
            )
            continue

        observacao_informada = not _vazio(observacao_bruta)
        observacao = _texto(observacao_bruta) if observacao_informada else ""
        analises = list(emissao.get("analises", ()))
        analise_atual = _ultima_analise(analises)
        if not situacao and (data_informada or observacao_informada) and analise_atual is None:
            linhas.append(
                LinhaSituacaoPadrao(
                    **base,
                    categoria="analise_nao_encontrada",
                    mensagem="Não há situação registrada nesta revisão para atualizar data ou observação.",
                    documento_id=documento_id,
                    emissao_id=int(emissao["id"]),
                )
            )
            continue

        chave_emissao = int(emissao["id"])
        antes = situacoes_simuladas.get(
            chave_emissao,
            str(analise_atual.get("situacao", "")) if analise_atual else "",
        )
        depois = situacao or antes
        linhas.append(
            LinhaSituacaoPadrao(
                **{
                    **base,
                    "revisao": str(emissao["revisao"]),
                    "situacao": situacao,
                    "data_analise": data_analise,
                    "documento_id": documento_id,
                    "emissao_id": chave_emissao,
                    "observacao": observacao,
                    "observacao_informada": observacao_informada,
                    "data_informada": data_informada,
                    "situacao_antes": antes,
                    "situacao_depois": depois,
                    "aviso": aviso,
                }
            )
        )
        if situacao:
            situacoes_simuladas[chave_emissao] = situacao

    return PreviaSituacaoPadrao(
        contrato_id=contrato_id,
        perfil_id=perfil_id,
        data_importacao=data_importacao,
        arquivo_nome=Path(nome_arquivo).name,
        cabecalhos=tuple(CABECALHOS[chave] for chave in CABECALHOS if chave in cabecalho),
        linhas=tuple(linhas),
        documentos_encontrados=len(encontrados),
        documentos_nao_encontrados=len(nao_encontrados),
        codigos_invalidos=sum(linha.categoria == "codigos_invalidos" for linha in linhas),
        situacoes_invalidas=sum(linha.categoria == "situacoes_invalidas" for linha in linhas),
    )


def aplicar_previa_situacao_padrao(
    previa: PreviaSituacaoPadrao,
    *,
    contrato,
    perfil_modelo,
    usuario=None,
):
    from django.db import transaction

    from documentos.models import Analise, Emissao
    from .models import ImportacaoSituacao

    if previa.contrato_id != contrato.pk or perfil_modelo.contrato_id != contrato.pk:
        raise ValueError("A prévia, o perfil e o contrato precisam ser os mesmos.")
    if previa.perfil_id != perfil_modelo.pk:
        raise ValueError("O perfil vigente mudou. Gere outra prévia antes de aplicar.")

    with transaction.atomic():
        linhas_validas = [linha for linha in previa.linhas if linha.valida]
        documentos = {linha.documento_id for linha in linhas_validas if linha.documento_id}
        importacao = ImportacaoSituacao.objects.create(
            contrato=contrato,
            data_extracao=previa.data_importacao,
            arquivo_nome=f"[Planilha padrão] {previa.arquivo_nome}",
            importado_por=usuario,
            documentos=len(documentos),
            emissoes=0,
            analises_explicitas=sum(bool(linha.situacao) for linha in linhas_validas),
            analises_deduzidas=0,
            historicos_truncados=0,
            fora_do_id=0,
            linhas_invalidas=previa.linhas_invalidas,
        )
        motivo_historico = f"importacao_situacao_padrao:{importacao.pk}"

        for linha in linhas_validas:
            if not linha.emissao_id or not linha.documento_id:
                continue
            emissao = Emissao.objects.filter(
                pk=linha.emissao_id,
                documento_id=linha.documento_id,
                documento__contrato=contrato,
            ).first()
            if emissao is None:
                raise ValueError("Uma revisão da prévia não pertence mais ao documento. Gere outra prévia.")

            analises = list(emissao.analises.all().order_by("data_analise", "registrado_em", "pk"))
            analise_alvo = None
            if linha.situacao:
                analise_alvo = next(
                    (
                        item
                        for item in reversed(analises)
                        if _normalizar(item.situacao) == _normalizar(linha.situacao)
                        and item.data_analise == linha.data_analise
                    ),
                    None,
                )
            elif analises:
                analise_alvo = analises[-1]

            alterados = []
            if analise_alvo is None and linha.situacao:
                analise_alvo = Analise(
                    emissao=emissao,
                    etapa="Situação importada",
                    situacao=linha.situacao,
                    origem=Analise.Origem.MANUAL,
                    data_analise=linha.data_analise,
                    observacao=linha.observacao if linha.observacao_informada else "",
                    registrado_por=usuario,
                )
                _marcar_historico(analise_alvo, usuario, motivo_historico)
                analise_alvo.save()
                continue

            if analise_alvo is None:
                continue
            if linha.situacao and analise_alvo.situacao != linha.situacao:
                analise_alvo.situacao = linha.situacao
                alterados.append("situacao")
            if linha.situacao and analise_alvo.data_analise != linha.data_analise:
                analise_alvo.data_analise = linha.data_analise
                alterados.append("data_analise")
            if not linha.situacao and linha.data_informada and analise_alvo.data_analise != linha.data_analise:
                analise_alvo.data_analise = linha.data_analise
                alterados.append("data_analise")
            if linha.observacao_informada and analise_alvo.observacao != linha.observacao:
                analise_alvo.observacao = linha.observacao
                alterados.append("observacao")
            if alterados:
                if usuario:
                    analise_alvo.registrado_por = usuario
                    alterados.append("registrado_por")
                _marcar_historico(analise_alvo, usuario, motivo_historico)
                analise_alvo.save(update_fields=tuple(alterados))
        return importacao


def _ler_registros(arquivo, nome_arquivo):
    nome = Path(nome_arquivo).name.lower()
    try:
        arquivo.seek(0)
        conteudo = arquivo.read()
        if nome.endswith(".csv"):
            texto = _decodificar_csv(conteudo)
            amostra = texto[:4096]
            try:
                delimitador = csv.Sniffer().sniff(amostra, delimiters=",;\t|").delimiter
            except csv.Error:
                delimitador = ";" if amostra.count(";") > amostra.count(",") else ","
            linhas = list(csv.reader(StringIO(texto), delimiter=delimitador))
            cabecalho, numero_cabecalho = _encontrar_cabecalho(linhas)
            indices = cabecalho
            dados = []
            for numero, linha in enumerate(linhas[numero_cabecalho + 1 :], start=numero_cabecalho + 2):
                if any(not _vazio(valor) for valor in linha):
                    dados.append((numero, linha))
            return indices, dados

        if not nome.endswith(".xlsx"):
            raise ErroFormatoSituacaoPadrao("Envie um arquivo .xlsx ou .csv.")
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Workbook contains no default style")
            workbook = load_workbook(BytesIO(conteudo), read_only=True, data_only=True)
        try:
            for worksheet in workbook.worksheets:
                linhas = list(worksheet.iter_rows(values_only=True))
                try:
                    cabecalho, indice = _encontrar_cabecalho(linhas[:10])
                except ErroFormatoSituacaoPadrao:
                    continue
                dados = [
                    (numero, linha)
                    for numero, linha in enumerate(linhas[indice + 1 :], start=indice + 2)
                    if any(not _vazio(valor) for valor in linha)
                ]
                return cabecalho, dados
        finally:
            workbook.close()
    except ErroFormatoSituacaoPadrao:
        raise
    except (BadZipFile, InvalidFileException, OSError, ValueError, csv.Error) as erro:
        raise ErroFormatoSituacaoPadrao(f"Não foi possível ler o arquivo: {erro}") from erro
    raise ErroFormatoSituacaoPadrao("Não foi encontrado o cabeçalho obrigatório Código.")


def _encontrar_cabecalho(linhas):
    por_nome = {_normalizar_cabecalho(rotulo): chave for chave, rotulo in CABECALHOS.items()}
    for indice, linha in enumerate(linhas):
        mapeamento = {}
        for posicao, valor in enumerate(linha):
            chave = por_nome.get(_normalizar_cabecalho(valor))
            if chave:
                mapeamento.setdefault(chave, posicao)
        if "codigo" in mapeamento:
            return mapeamento, indice
    raise ErroFormatoSituacaoPadrao("Não foi encontrado o cabeçalho obrigatório Código.")


def _vocabulario_situacoes(perfil):
    resultado = {}
    for grupo in perfil.painel.grupos:
        for estado in grupo.estados:
            resultado.setdefault(_normalizar(estado), estado)
    for estado in perfil.painel.ignorar:
        resultado.setdefault(_normalizar(estado), estado)
    for estado in perfil.analise.transicoes:
        resultado.setdefault(_normalizar(estado), estado)
    resultado.setdefault(_normalizar(perfil.analise.inicial), perfil.analise.inicial)
    return resultado


def _selecionar_emissao(emissoes, revisao):
    ordenadas = sorted(emissoes, key=lambda item: (str(item.get("data_emissao") or ""), int(item["id"])))
    if revisao:
        correspondentes = [
            emissao for emissao in ordenadas
            if _normalizar(emissao.get("revisao", "")) == _normalizar(revisao)
        ]
        return correspondentes[-1] if correspondentes else None
    return ordenadas[-1] if ordenadas else None


def _ultima_analise(analises):
    ordenadas = sorted(
        analises,
        key=lambda item: (str(item.get("data_analise") or ""), str(item.get("registrado_em") or ""), int(item["id"])),
    )
    return ordenadas[-1] if ordenadas else None


def _valor_coluna(valores, indices, nome):
    posicao = indices.get(nome)
    return valores[posicao] if posicao is not None and posicao < len(valores) else None


def _data(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        convertido = from_excel(valor)
        if isinstance(convertido, datetime):
            return convertido.date()
        if isinstance(convertido, date):
            return convertido
        raise ValueError(f"Data inválida: '{valor}'. Use uma data completa.")
    texto = _texto(valor)
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(texto).date()
    except ValueError as erro:
        raise ValueError(f"Data inválida: '{texto}'. Use DD/MM/AAAA ou AAAA-MM-DD.") from erro


def _decodificar_csv(conteudo):
    if isinstance(conteudo, str):
        return conteudo.lstrip("\ufeff")
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return conteudo.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ErroFormatoSituacaoPadrao("O CSV deve usar codificação UTF-8 ou Windows-1252.")


def _normalizar_cabecalho(valor):
    texto = "".join(
        caractere
        for caractere in unicodedata.normalize("NFD", _texto(valor))
        if unicodedata.category(caractere) != "Mn"
    )
    return re.sub(r"[^a-z0-9]+", "_", texto.casefold()).strip("_")


def _normalizar(valor):
    texto = "".join(
        caractere
        for caractere in unicodedata.normalize("NFD", str(valor or ""))
        if unicodedata.category(caractere) != "Mn"
    )
    return re.sub(r"[^A-Z0-9]+", "_", texto.upper()).strip("_")


def _normalizar_codigo(valor):
    return re.sub(r"\s+", "", _texto(valor)).upper()


def _texto(valor):
    if valor is None:
        return ""
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    texto = str(valor).strip()
    return "" if texto.casefold() == "<empty value>" else texto


def _vazio(valor):
    return valor is None or (isinstance(valor, str) and not _texto(valor))


def _marcar_historico(instancia, usuario, motivo):
    instancia._history_user = usuario
    instancia._change_reason = motivo
