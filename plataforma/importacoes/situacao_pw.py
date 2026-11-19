"""Prévia pura da extração de situação do ProjectWise."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Iterable, Mapping
import re
import unicodedata
import warnings
from zipfile import BadZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.utils.datetime import from_excel
from openpyxl.utils.exceptions import InvalidFileException

from core.perfil.ciclo import EstadoEmissao, ErroCiclo, aplicar
from core.perfil.codigo import ErroCodigo, interpretar
from core.perfil.series import criar_serie


ESTADOS_CONHECIDOS = {
    "EM_DESENVOLVIMENTO",
    "EM_ANALISE",
    "PARA_APROVACAO",
    "EM_COLETA_DE_ASSINATURAS",
    "APROVADO",
    "NAO APROVADO",
    "NAO CONFORME",
    "INCONSISTENTE",
    "ERRO_DE_ASSINATURA",
    "CANCELADO",
    "REVISAO_SUPERADA",
}
RESULTADOS = {
    "APROVADO",
    "NAO APROVADO",
    "INCONSISTENTE",
    "NAO CONFORME",
    "CANCELADO",
}
ESTADOS_TRAMITE = ESTADOS_CONHECIDOS - RESULTADOS - {"REVISAO SUPERADA"}
ACOES_POR_ESTADO = {
    "NOVA_VERSAO": "nova_versao",
    "NOVA_REVISAO_PRELIMINAR": "nova_revisao_preliminar",
    "EMITIR_ORIGINAL": "emitir_original",
    "REABRIR": "reabrir",
}
COLUNAS_OBRIGATORIAS = {
    "revisao": "Revisão",
    "versao": "Version",
    "situacao": "Current State Name",
    "data_emissao": "Data Real da Emissão",
    "data_resposta": "Data Resposta",
    "titulo": "Título",
    "codigo": "Código Base",
    "arquivo": "File Name",
    "historico": "Histórico do Workflow",
}
COLUNAS_CAIXAS = {
    "tipo": "Document Type Hierarchy - Document Type",
    "linha": "Document Type Hierarchy - Document Subtype",
    "trecho": "Location Hierarchy - Location",
    "subtrecho": "Location Hierarchy - Sublocation",
    "unidade": "Discipline Hierarchy - Discipline",
    "etapa": "Discipline Hierarchy - Subdiscipline",
    "classe": "Classe",
    "sequencial": "Sequencial",
}
PADRAO_EVENTO = re.compile(
    r"^\s*(?P<data>\d{1,2}/\d{1,2}/\d{4})\s*-\s*"
    r"\((?P<revisao>[^.)]+)\.(?P<versao>[^)]+)\)\s*(?P<situacao>.+?)\s*$"
)
PADRAO_SEPARADOR_EVENTO = re.compile(r",\s*(?=\d{1,2}/\d{1,2}/\d{4}\s*-\s*\()")


@dataclass(frozen=True)
class AnalisePreviaPW:
    situacao: str
    data_analise: date | None
    origem: str
    observacao: str = ""
    nova: bool = True


@dataclass(frozen=True)
class EmissaoPreviaPW:
    revisao: str
    versao: int | None
    fase: str
    data_emissao: date
    analises: tuple[AnalisePreviaPW, ...] = ()
    nome_arquivo: str = ""
    nova: bool = True


@dataclass(frozen=True)
class DocumentoPreviaPW:
    codigo_base: str
    identificador_base: str
    segmentos: dict[str, str]
    titulo: str
    emissoes: tuple[EmissaoPreviaPW, ...]
    fora_do_id: bool
    situacao_vigente: str = ""
    emissao_mais_recente: tuple[str, int | None] | None = None


@dataclass(frozen=True)
class LinhaInvalidaPW:
    numero_linha: int
    codigo: str
    caixa_falhou: str
    mensagem: str
    fora_do_id: bool = False
    categoria: str = "dados_invalidos"
    dados_linha: dict | None = None


@dataclass(frozen=True)
class HistoricoTruncadoPW:
    numero_linha: int
    codigo: str
    trecho_descartado: str


@dataclass(frozen=True)
class MudancaSituacaoPW:
    codigo_base: str
    antes: str
    depois: str


@dataclass(frozen=True)
class PreviaSituacaoPW:
    contrato_id: int
    perfil_id: int
    data_extracao: date
    arquivo_nome: str
    documentos: tuple[DocumentoPreviaPW, ...]
    linhas_invalidas: tuple[LinhaInvalidaPW, ...] = ()
    historicos_truncados: tuple[HistoricoTruncadoPW, ...] = ()
    mudancas_situacao: tuple[MudancaSituacaoPW, ...] = ()

    @property
    def emissoes_novas(self) -> int:
        return sum(emissao.nova for documento in self.documentos for emissao in documento.emissoes)

    @property
    def analises_explicitas(self) -> int:
        return sum(
            analise.origem == "importado_pw" and analise.nova
            for documento in self.documentos
            for emissao in documento.emissoes
            for analise in emissao.analises
        )

    @property
    def analises_deduzidas(self) -> int:
        return sum(
            analise.origem == "deduzido_pw" and analise.nova
            for documento in self.documentos
            for emissao in documento.emissoes
            for analise in emissao.analises
        )

    @property
    def analises_novas(self) -> int:
        return self.analises_explicitas + self.analises_deduzidas

    @property
    def documentos_fora_do_id(self) -> int:
        fora = {documento.codigo_base for documento in self.documentos if documento.fora_do_id}
        fora.update(
            linha.codigo
            for linha in self.linhas_invalidas
            if linha.fora_do_id and linha.codigo
        )
        return len(fora)

    @property
    def situacoes_alteradas(self) -> int:
        return len(self.mudancas_situacao)


class ErroFormatoSituacaoPW(ValueError):
    """Arquivo sem o conjunto esperado de cabeçalhos ou ilegível."""


def gerar_previa_situacao_pw(
    arquivo: BinaryIO,
    *,
    nome_arquivo: str,
    contrato_id: int,
    perfil_id: int,
    perfil,
    data_extracao: date | None = None,
    documentos_existentes: Mapping[str, Mapping[str, object]] | None = None,
    identificadores_previstos: Iterable[str] = (),
    emissoes_existentes: Iterable[tuple[str, str, int | None]] = (),
    analises_existentes: Iterable[tuple[str, str, int | None, str, date | None, str]] = (),
    situacoes_vigentes: Mapping[str, str] | None = None,
) -> PreviaSituacaoPW:
    """Lê a extração e compõe uma prévia sem acessar o banco ou gravar dados."""
    arquivo.seek(0)
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Workbook contains no default style")
            workbook = load_workbook(arquivo, read_only=True, data_only=True)
    except (BadZipFile, InvalidFileException, OSError, ValueError) as erro:
        raise ErroFormatoSituacaoPW(f"Não foi possível abrir o arquivo Excel: {erro}") from erro

    try:
        worksheet, header_row, indices = _localizar_cabecalho(workbook)
        previstos = {_normalizar_codigo(valor) for valor in identificadores_previstos}
        linhas_invalidas: list[LinhaInvalidaPW] = []
        truncated: list[HistoricoTruncadoPW] = []
        registros: dict[str, dict[str, object]] = {}
        for numero_linha, valores in enumerate(
            worksheet.iter_rows(min_row=header_row + 1, values_only=True),
            start=header_row + 1,
        ):
            if not any(not _vazio(valor) for valor in valores):
                continue
            if _texto(valores[0]).casefold().startswith("applied filters:"):
                continue
            dados = {
                nome: _valor_coluna(valores, indices, cabecalho)
                for nome, cabecalho in COLUNAS_OBRIGATORIAS.items()
            }
            partes = {
                nome: _valor_coluna(valores, indices, cabecalho)
                for nome, cabecalho in COLUNAS_CAIXAS.items()
            }
            codigo = _texto(dados["codigo"])
            if not codigo:
                codigo = _codigo_de_arquivo(_texto(dados["arquivo"]), _texto(dados["revisao"]))
            if not codigo:
                codigo = _montar_codigo(perfil, partes)
            interpretado = interpretar(perfil, codigo)
            if isinstance(interpretado, ErroCodigo):
                codigo_arquivo = _codigo_de_arquivo(
                    _texto(dados["arquivo"]), _texto(dados["revisao"])
                )
                if codigo_arquivo and codigo_arquivo != codigo:
                    interpretado_arquivo = interpretar(perfil, codigo_arquivo)
                    codigo = codigo_arquivo
                    interpretado = interpretado_arquivo
            if isinstance(interpretado, ErroCodigo):
                caixa = next(
                    (campo.rotulo for campo in perfil.codigo.campos if campo.nome == interpretado.segmento),
                    interpretado.segmento or "Código Base",
                )
                linhas_invalidas.append(
                    LinhaInvalidaPW(
                        numero_linha,
                        codigo,
                        caixa,
                        interpretado.mensagem,
                        fora_do_id=_normalizar_codigo(codigo) not in previstos,
                        categoria="codigos_invalidos",
                        dados_linha=_dados_linha_recusada(dados, partes),
                    )
                )
                continue

            revisao = _texto(dados["revisao"]).upper()
            versao = _inteiro_ou_none(dados["versao"])
            if not revisao or versao is None:
                caixa = "Revisão" if not revisao else "Version"
                linhas_invalidas.append(
                    LinhaInvalidaPW(
                        numero_linha,
                        codigo,
                        caixa,
                        f"{caixa} vazio ou inválido.",
                        fora_do_id=_normalizar_codigo(codigo) not in previstos,
                        categoria="dados_invalidos",
                        dados_linha=_dados_linha_recusada(dados, partes),
                    )
                )
                continue
            emissao = _data(dados["data_emissao"])
            if emissao is None:
                linhas_invalidas.append(
                    LinhaInvalidaPW(
                        numero_linha,
                        codigo,
                        "Data Real da Emissão",
                        "A data de emissão está vazia ou inválida.",
                        fora_do_id=_normalizar_codigo(codigo) not in previstos,
                        categoria="dados_invalidos",
                        dados_linha=_dados_linha_recusada(dados, partes),
                    )
                )
                continue

            chave_documento = interpretado.identificador_base
            registro = registros.setdefault(
                chave_documento,
                {
                    "codigo": codigo,
                    "segmentos": dict(interpretado.segmentos),
                    "titulo": _texto(dados["titulo"]),
                    "emissoes": {},
                    "eventos": [],
                    "truncados": [],
                    "linhas": [],
                },
            )
            registro["linhas"].append(numero_linha)
            chave_emissao = (revisao, versao)
            estado_atual = _texto(dados["situacao"])
            atual_data = _data(dados["data_resposta"])
            registro["emissoes"][chave_emissao] = {
                "revisao": revisao,
                "versao": versao,
                "data_emissao": emissao,
                "data_resposta": atual_data,
                "estado_atual": estado_atual,
                "nome_arquivo": _texto(dados["arquivo"]),
                "numero_linha": numero_linha,
            }
            eventos, truncado = _ler_historico(_texto(dados["historico"]), perfil)
            registro["eventos"].extend(eventos)
            if truncado:
                registro["truncados"].append((numero_linha, codigo, truncado))

        documentos_existentes = documentos_existentes or {}
        emissoes_existentes = set(emissoes_existentes)
        analises_existentes = set(analises_existentes)
        situacoes_vigentes = situacoes_vigentes or {}
        documentos: list[DocumentoPreviaPW] = []
        mudancas: list[MudancaSituacaoPW] = []

        for identificador, registro in registros.items():
            emissoes = _montar_emissoes(perfil, registro)
            emissoes_atualizadas = []
            for emissao_item in emissoes:
                chave_emissao = (identificador, emissao_item.revisao, emissao_item.versao)
                emissao_existe = chave_emissao in emissoes_existentes
                analises_atualizadas = tuple(
                    replace(
                        analise,
                        nova=(
                            identificador,
                            emissao_item.revisao,
                            emissao_item.versao,
                            analise.situacao,
                            analise.data_analise,
                            analise.origem,
                        ) not in analises_existentes,
                    )
                    for analise in emissao_item.analises
                )
                emissoes_atualizadas.append(
                    replace(emissao_item, analises=analises_atualizadas, nova=not emissao_existe)
                )
            emissoes = emissoes_atualizadas
            existente = documentos_existentes.get(identificador, {})
            titulo = str(existente.get("titulo") or registro["titulo"] or "")
            fora_do_id = _normalizar_codigo(identificador) not in previstos
            situacao_vigente = _situacao_da_ultima_emissao(emissoes)
            if emissoes:
                emissao_mais_recente = max(
                    emissoes,
                    key=lambda item: (item.data_emissao, _ordem_versao(item.versao)),
                )
                chave_recente = (emissao_mais_recente.revisao, emissao_mais_recente.versao)
            else:
                emissao_mais_recente = None
                chave_recente = None
            documento = DocumentoPreviaPW(
                codigo_base=str(registro["codigo"]),
                identificador_base=identificador,
                segmentos=dict(registro["segmentos"]),
                titulo=titulo,
                emissoes=tuple(emissoes),
                fora_do_id=fora_do_id,
                situacao_vigente=situacao_vigente,
                emissao_mais_recente=chave_recente,
            )
            documentos.append(documento)
            antes = str(situacoes_vigentes.get(identificador, ""))
            if situacao_vigente and antes != situacao_vigente:
                mudancas.append(MudancaSituacaoPW(str(registro["codigo"]), antes, situacao_vigente))

        for registro in registros.values():
            truncated.extend(
                HistoricoTruncadoPW(numero, codigo, trecho)
                for numero, codigo, trecho in registro["truncados"]
            )
        unique_truncated = {
            (item.numero_linha, item.codigo, item.trecho_descartado): item
            for item in truncated
        }
        return PreviaSituacaoPW(
            contrato_id=contrato_id,
            perfil_id=perfil_id,
            data_extracao=data_extracao or date.today(),
            arquivo_nome=Path(nome_arquivo).name,
            documentos=tuple(documentos),
            linhas_invalidas=tuple(linhas_invalidas),
            historicos_truncados=tuple(unique_truncated.values()),
            mudancas_situacao=tuple(mudancas),
        )
    except ErroFormatoSituacaoPW:
        raise
    except (BadZipFile, InvalidFileException, OSError, ValueError, KeyError) as erro:
        raise ErroFormatoSituacaoPW(f"Não foi possível interpretar a extração do PW: {erro}") from erro
    finally:
        workbook.close()


def gerar_previa_linhas_recusadas_situacao_pw(
    inconsistencias,
    *,
    nome_arquivo: str,
    contrato_id: int,
    perfil_id: int,
    perfil,
    data_extracao: date,
    documentos_existentes: Mapping[str, Mapping[str, object]] | None = None,
    identificadores_previstos: Iterable[str] = (),
    emissoes_existentes: Iterable[tuple[str, str, int | None]] = (),
    analises_existentes: Iterable[tuple[str, str, int | None, str, date | None, str]] = (),
    situacoes_vigentes: Mapping[str, str] | None = None,
) -> PreviaSituacaoPW:
    """Reinterpreta linhas recusadas do PW com os valores guardados na importação."""
    inconsistencias = list(inconsistencias)
    linhas = [
        inconsistencia.dados_linha
        for inconsistencia in inconsistencias
        if inconsistencia.dados_linha
    ]
    if not linhas:
        raise ErroFormatoSituacaoPW("As linhas antigas não guardam dados suficientes para reprocessar.")

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append([*COLUNAS_CAIXAS.values(), *COLUNAS_OBRIGATORIAS.values()])
    for dados in linhas:
        worksheet.append([
            dados.get(nome)
            for nome in (*COLUNAS_CAIXAS.keys(), *COLUNAS_OBRIGATORIAS.keys())
        ])
    arquivo = BytesIO()
    workbook.save(arquivo)
    workbook.close()
    arquivo.seek(0)
    previa = gerar_previa_situacao_pw(
        arquivo,
        nome_arquivo=nome_arquivo,
        contrato_id=contrato_id,
        perfil_id=perfil_id,
        perfil=perfil,
        data_extracao=data_extracao,
        documentos_existentes=documentos_existentes,
        identificadores_previstos=identificadores_previstos,
        emissoes_existentes=emissoes_existentes,
        analises_existentes=analises_existentes,
        situacoes_vigentes=situacoes_vigentes,
    )
    numeros_originais = [
        inconsistencia.numero_linha
        for inconsistencia in inconsistencias
        if inconsistencia.dados_linha
    ]
    numeros_reprocessados = {
        indice + 2: numero
        for indice, numero in enumerate(numeros_originais)
    }
    return replace(
        previa,
        linhas_invalidas=tuple(
            replace(
                linha,
                numero_linha=numeros_reprocessados.get(linha.numero_linha, linha.numero_linha),
            )
            for linha in previa.linhas_invalidas
        ),
    )


def _dados_linha_recusada(dados, partes):
    return {
        nome: _valor_json(valor)
        for nome, valor in {**partes, **dados}.items()
    }


def _valor_json(valor):
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    return str(valor)


def aplicar_previa_situacao_pw(
    previa: PreviaSituacaoPW,
    *,
    contrato,
    perfil_modelo,
    usuario=None,
    inconsistencias_existentes=None,
    codigos_reprocessados=(),
):
    """Grava a prévia, com transação, emissão/analise idempotentes e inconsistências rastreáveis."""
    from django.db import transaction
    from django.utils import timezone

    from documentos.models import Analise, CodigoDocumento, Documento, Emissao
    from .models import ImportacaoSituacao, InconsistenciaImportacao

    reprocessamento = inconsistencias_existentes is not None
    inconsistencias_existentes = list(inconsistencias_existentes or ())
    if previa.contrato_id != contrato.pk or perfil_modelo.contrato_id != contrato.pk:
        raise ValueError("A prévia, o perfil e o contrato precisam ser os mesmos.")
    if previa.perfil_id != perfil_modelo.pk:
        raise ValueError("O perfil vigente mudou. Gere uma nova prévia antes de confirmar.")

    with transaction.atomic():
        chave_importacao = {
            "contrato": contrato,
            "data_extracao": previa.data_extracao,
            "arquivo_nome": previa.arquivo_nome,
        }
        if reprocessamento:
            importacao = ImportacaoSituacao.objects.filter(**chave_importacao).first()
            if importacao is None or any(
                item.importacao_situacao_id != importacao.pk
                for item in inconsistencias_existentes
            ):
                raise ValueError("As linhas recusadas não pertencem à importação de situação desta prévia.")
        else:
            importacao, _ = ImportacaoSituacao.objects.update_or_create(
                **chave_importacao,
                defaults={
                    "importado_por": usuario,
                    "importado_em": timezone.now(),
                    "documentos": len(previa.documentos),
                    "emissoes": previa.emissoes_novas,
                    "analises_explicitas": previa.analises_explicitas,
                    "analises_deduzidas": previa.analises_deduzidas,
                    "historicos_truncados": len(previa.historicos_truncados),
                    "fora_do_id": previa.documentos_fora_do_id,
                    "linhas_invalidas": len(previa.linhas_invalidas),
                },
            )

        codigos_validos = {
            _normalizar_codigo(codigo)
            for codigo in codigos_reprocessados
            if _normalizar_codigo(codigo)
        }
        for documento in previa.documentos:
            codigos_validos.add(_normalizar_codigo(documento.codigo_base))
            codigos_validos.add(_normalizar_codigo(documento.identificador_base))
        if codigos_validos:
            abertas = InconsistenciaImportacao.objects.filter(
                importacao_situacao__contrato=contrato,
                resolvida_em__isnull=True,
            )
            agora = timezone.now()
            for inconsistencia in abertas:
                if _normalizar_codigo(inconsistencia.codigo_lido) in codigos_validos:
                    inconsistencia.resolvida_em = agora
                    inconsistencia.save(update_fields=("resolvida_em",))

        if reprocessamento:
            linhas_invalidas = {
                _normalizar_codigo(linha.codigo): linha
                for linha in previa.linhas_invalidas
                if _normalizar_codigo(linha.codigo)
            }
            for inconsistencia in inconsistencias_existentes:
                if inconsistencia.resolvida_em is not None:
                    continue
                linha = linhas_invalidas.get(_normalizar_codigo(inconsistencia.codigo_lido))
                if linha is None:
                    continue
                campos = {
                    "categoria": linha.categoria,
                    "caixa_falhou": linha.caixa_falhou,
                    "mensagem": linha.mensagem,
                    "dados_linha": linha.dados_linha or {},
                }
                alterados = []
                for nome, valor in campos.items():
                    if getattr(inconsistencia, nome) != valor:
                        setattr(inconsistencia, nome, valor)
                        alterados.append(nome)
                if alterados:
                    inconsistencia.save(update_fields=alterados)

        if not reprocessamento:
            existentes_abertas = {
                (item.numero_linha, _normalizar_codigo(item.codigo_lido)): item
                for item in importacao.inconsistencias.filter(resolvida_em__isnull=True)
            }
            for linha in previa.linhas_invalidas:
                chave = (linha.numero_linha, _normalizar_codigo(linha.codigo))
                inconsistencia = existentes_abertas.pop(chave, None)
                if inconsistencia is None:
                    InconsistenciaImportacao.objects.create(
                        importacao_situacao=importacao,
                        numero_linha=linha.numero_linha,
                        codigo_lido=linha.codigo,
                        categoria=linha.categoria,
                        caixa_falhou=linha.caixa_falhou,
                        mensagem=linha.mensagem,
                        dados_linha=linha.dados_linha or {},
                    )
                    continue
                inconsistencia.categoria = linha.categoria
                inconsistencia.caixa_falhou = linha.caixa_falhou
                inconsistencia.mensagem = linha.mensagem
                inconsistencia.dados_linha = linha.dados_linha or {}
                inconsistencia.save(update_fields=("categoria", "caixa_falhou", "mensagem", "dados_linha"))

        for item in previa.documentos:
            documento = Documento.objects.filter(
                contrato=contrato,
                identificador_base=item.identificador_base,
            ).first()
            if documento is None:
                documento = Documento(
                    contrato=contrato,
                    identificador_base=item.identificador_base,
                    tipo=item.segmentos.get("tipo", ""),
                    titulo=item.titulo,
                    disciplina=item.segmentos.get("classe", ""),
                    trecho=item.segmentos.get("trecho", ""),
                    atributos=dict(item.segmentos),
                    fora_do_id=item.fora_do_id,
                )
                documento._history_user = usuario
                documento.save()
            else:
                campos = {
                    "fora_do_id": item.fora_do_id,
                }
                if not documento.titulo and item.titulo:
                    campos["titulo"] = item.titulo
                alterados = [nome for nome, valor in campos.items() if getattr(documento, nome) != valor]
                if alterados:
                    for nome in alterados:
                        setattr(documento, nome, campos[nome])
                    documento._history_user = usuario
                    documento.save(update_fields=alterados)

            codigo = CodigoDocumento.objects.filter(documento=documento, perfil=perfil_modelo).first()
            if codigo is None:
                codigo = CodigoDocumento(documento=documento, perfil=perfil_modelo, codigo=item.codigo_base)
                codigo._history_user = usuario
                codigo.save()
            elif codigo.codigo != item.codigo_base:
                codigo.codigo = item.codigo_base
                codigo._history_user = usuario
                codigo.save(update_fields=("codigo",))

            for emissao_item in item.emissoes:
                emissao, criada = Emissao.objects.get_or_create(
                    documento=documento,
                    revisao=emissao_item.revisao,
                    versao=emissao_item.versao,
                    defaults={
                        "fase": emissao_item.fase,
                        "data_emissao": emissao_item.data_emissao,
                        "origem": Emissao.Origem.CLIENTE,
                        "criado_por": usuario,
                    },
                )
                if not criada:
                    alterados = []
                    for nome, valor in (("fase", emissao_item.fase), ("data_emissao", emissao_item.data_emissao)):
                        if getattr(emissao, nome) != valor:
                            setattr(emissao, nome, valor)
                            alterados.append(nome)
                    if alterados:
                        emissao._history_user = usuario
                        emissao.save(update_fields=alterados)

                analises_deduzidas = [a for a in emissao_item.analises if a.origem == "deduzido_pw"]
                analises_importadas = [a for a in emissao_item.analises if a.origem == "importado_pw"]
                for analise_item in analises_importadas:
                    if _normalizar(analise_item.situacao) in RESULTADOS:
                        existentes_deduzidas = Analise.objects.filter(
                            emissao=emissao,
                            origem=Analise.Origem.DEDUZIDO_PW,
                        )
                        igual = existentes_deduzidas.filter(
                            situacao=analise_item.situacao,
                            data_analise=analise_item.data_analise,
                        ).first()
                        if igual:
                            igual.origem = Analise.Origem.IMPORTADO_PW
                            igual.observacao = analise_item.observacao
                            igual.registrado_por = usuario
                            igual._history_user = usuario
                            igual.save(update_fields=("origem", "observacao", "registrado_por"))
                        else:
                            existentes_deduzidas.delete()
                    Analise.objects.get_or_create(
                        emissao=emissao,
                        etapa="Análise do cliente",
                        situacao=analise_item.situacao,
                        data_analise=analise_item.data_analise,
                        origem=Analise.Origem.IMPORTADO_PW,
                        defaults={
                            "observacao": analise_item.observacao,
                            "registrado_por": usuario,
                        },
                    )
                for analise_item in analises_deduzidas:
                    if Analise.objects.filter(
                        emissao=emissao,
                        situacao=analise_item.situacao,
                        data_analise=analise_item.data_analise,
                        origem=Analise.Origem.IMPORTADO_PW,
                    ).exists():
                        continue
                    Analise.objects.get_or_create(
                        emissao=emissao,
                        etapa="Análise do cliente",
                        situacao=analise_item.situacao,
                        data_analise=analise_item.data_analise,
                        origem=Analise.Origem.DEDUZIDO_PW,
                        defaults={
                            "observacao": analise_item.observacao,
                            "registrado_por": usuario,
                        },
                    )
        return importacao


def _localizar_cabecalho(workbook):
    exigidos = {_normalizar(cabecalho) for cabecalho in COLUNAS_OBRIGATORIAS.values()}
    for worksheet in workbook.worksheets:
        for numero, row in enumerate(worksheet.iter_rows(min_row=1, max_row=10, values_only=True), start=1):
            if row and _texto(row[0]).casefold().startswith("applied filters:"):
                continue
            indices = {}
            for indice, valor in enumerate(row):
                if not _vazio(valor):
                    indices.setdefault(_normalizar(valor), indice)
            if exigidos.issubset(indices):
                return worksheet, numero, indices
    raise ErroFormatoSituacaoPW(
        "Não foi encontrado o cabeçalho esperado da extração do PW. Verifique as colunas de revisão, versão, situação e código."
    )


def _ler_historico(texto: str, perfil):
    if not texto:
        return [], ""
    pedaços = PADRAO_SEPARADOR_EVENTO.split(texto)
    eventos = []
    truncado = ""
    estados_perfil = {_normalizar(nome) for nome in perfil.analise.transicoes}
    estados_validos = ESTADOS_CONHECIDOS | estados_perfil
    for indice, pedaço in enumerate(pedaços):
        correspondencia = PADRAO_EVENTO.fullmatch(pedaço)
        if correspondencia is None:
            if indice == len(pedaços) - 1:
                truncado = pedaço.strip()
            continue
        situacao = correspondencia.group("situacao").strip()
        if _normalizar(situacao) not in estados_validos:
            if indice == len(pedaços) - 1:
                truncado = pedaço.strip()
            continue
        eventos.append(
            {
                "revisao": correspondencia.group("revisao").strip().upper(),
                "versao": _inteiro_ou_none(correspondencia.group("versao")),
                "situacao": situacao,
                "data": _data(correspondencia.group("data")),
            }
        )
    return eventos, truncado


def _montar_emissoes(perfil, registro):
    fontes = registro["emissoes"]
    ordenadas = sorted(
        fontes.values(),
        key=lambda item: (item["data_emissao"], _ordem_revisao(perfil, item["revisao"]), _ordem_versao(item["versao"])),
    )
    emissoes: list[EmissaoPreviaPW] = []
    ultima_original = None
    ultima_preliminar = None
    eventos_por_chave: dict[tuple[str, int | None], list[dict[str, object]]] = {}
    for evento in registro["eventos"]:
        eventos_por_chave.setdefault((evento["revisao"], evento["versao"]), []).append(evento)

    for indice, fonte in enumerate(ordenadas):
        chave = (fonte["revisao"], fonte["versao"])
        fase = _fase_emissao(perfil, fonte["revisao"])
        if fase == "original":
            ultima_original = fonte["revisao"]
        else:
            ultima_preliminar = fonte["revisao"]
        estado = EstadoEmissao(
            revisao=fonte["revisao"],
            versao=str(fonte["versao"]) if fonte["versao"] is not None else None,
            fase=fase,
            ultima_original=ultima_original,
            ultima_preliminar=ultima_preliminar,
        )
        eventos = eventos_por_chave.get(chave, [])
        analises: list[AnalisePreviaPW] = []
        vistos = set()
        for evento in eventos:
            situacao = evento["situacao"]
            if _normalizar(situacao) == "REVISAO_SUPERADA":
                continue
            chave_analise = (_normalizar(situacao), evento["data"])
            if chave_analise in vistos:
                continue
            vistos.add(chave_analise)
            analises.append(AnalisePreviaPW(situacao, evento["data"], "importado_pw"))

        estado_atual = fonte["estado_atual"]
        estado_atual_norm = _normalizar(estado_atual)
        ultima_evento = eventos[-1] if eventos else None
        status_resultado = ""
        if estado_atual_norm in RESULTADOS:
            status_resultado = estado_atual
        elif ultima_evento and _normalizar(ultima_evento["situacao"]) in RESULTADOS:
            status_resultado = str(ultima_evento["situacao"])

        estado_ja_no_historico = bool(
            ultima_evento and _normalizar(ultima_evento["situacao"]) == estado_atual_norm
        )
        if estado_atual and estado_atual_norm != "REVISAO_SUPERADA" and not estado_ja_no_historico:
            chave_analise = (estado_atual_norm, fonte["data_resposta"])
            if chave_analise not in vistos:
                vistos.add(chave_analise)
                analises.append(AnalisePreviaPW(estado_atual, fonte["data_resposta"], "importado_pw"))

        superada = estado_atual_norm == "REVISAO_SUPERADA" or bool(
            ultima_evento and _normalizar(ultima_evento["situacao"]) == "REVISAO_SUPERADA"
        )
        if not status_resultado and superada and indice + 1 < len(ordenadas):
            proxima = ordenadas[indice + 1]
            proxima_fase = _fase_emissao(perfil, proxima["revisao"])
            inferida = _deduzir_resultado(perfil, estado, proxima, proxima_fase)
            if inferida:
                nome_transicao, transicao = inferida
                situacao = _rotulo_situacao(nome_transicao)
                data_analise = fonte["data_resposta"]
                motivo = (
                    f"Deduzido pelo ciclo do perfil: a emissão seguinte é Rev {proxima['revisao']} "
                    f"Ver {proxima['versao']}; a transição '{transicao}' corresponde a '{situacao}'."
                )
                analises.append(AnalisePreviaPW(situacao, data_analise, "deduzido_pw", motivo))

        emissoes.append(
            EmissaoPreviaPW(
                revisao=fonte["revisao"],
                versao=fonte["versao"],
                fase=fase,
                data_emissao=fonte["data_emissao"],
                analises=tuple(analises),
                nome_arquivo=fonte["nome_arquivo"],
            )
        )
    return emissoes


def _deduzir_resultado(perfil, estado, proxima, proxima_fase):
    alvo = (proxima["revisao"], str(proxima["versao"]) if proxima["versao"] is not None else None, proxima_fase)
    candidatos = []
    for nome, transicao in perfil.analise.transicoes.items():
        if transicao.acao not in ACOES_POR_ESTADO.values():
            continue
        resultado = aplicar(perfil, estado, nome)
        if isinstance(resultado, ErroCiclo):
            continue
        obtido = (resultado.revisao, resultado.versao, resultado.fase)
        if obtido == alvo:
            candidatos.append((nome, transicao.acao))
    if not candidatos:
        return None
    preferido = "NAO_CONFORME" if estado.fase == "original" else "INCONSISTENTE"
    candidatos.sort(
        key=lambda par: (0 if _normalizar(par[0]) == preferido else 1, _normalizar(par[0]))
    )
    return candidatos[0]


def _rotulo_situacao(nome):
    rotulos = {
        "APROVADO": "Aprovado",
        "NAO_APROVADO": "Não Aprovado",
        "INCONSISTENTE": "Inconsistente",
        "NAO_CONFORME": "Não Conforme",
        "CANCELADO": "Cancelado",
    }
    return rotulos.get(_normalizar(nome), nome)


def _fase_emissao(perfil, revisao):
    eixo = perfil.emissao.revisao
    for configuracao in (eixo.reabertura,):
        if configuracao and _serie(configuracao).valida(revisao):
            return "preliminar"
    if _serie(eixo.preliminar).valida(revisao):
        return "preliminar"
    if _serie(eixo.original).valida(revisao):
        return "original"
    # O perfil é a autoridade; códigos válidos podem usar uma revisão fora das séries conhecidas.
    return "preliminar"


def _ordem_revisao(perfil, revisao):
    eixo = perfil.emissao.revisao
    if eixo.preliminar.nome == "numerica" and str(revisao).isdigit():
        return (0, int(revisao))
    if eixo.reabertura and _serie(eixo.reabertura).valida(revisao):
        return (1, str(revisao))
    if _serie(eixo.original).valida(revisao):
        return (2, str(revisao))
    return (3, str(revisao))


def _serie(configuracao):
    return criar_serie(configuracao.nome, inicio=configuracao.inicio, proibidas=configuracao.proibidas)


def _montar_codigo(perfil, partes):
    segmentos = {}
    for campo in perfil.codigo.campos:
        cabecalho = COLUNAS_CAIXAS.get(campo.nome)
        valor = partes.get(campo.nome) if cabecalho else None
        texto = _texto(valor)
        if texto:
            segmentos[campo.nome] = texto.upper()
    try:
        from core.perfil.codigo import montar

        return montar(perfil, segmentos)
    except (ValueError, TypeError):
        return ""


def _codigo_de_arquivo(nome, revisao):
    if not nome:
        return ""
    base = Path(nome).stem
    if revisao:
        sufixo = f"-{revisao}".upper()
        if base.upper().endswith(sufixo):
            return base[: -len(sufixo)]
    return re.sub(r"-(?:[A-Z]+\d*|\d+)$", "", base, flags=re.IGNORECASE)


def _situacao_da_ultima_emissao(emissoes):
    if not emissoes:
        return ""
    ultima = max(emissoes, key=lambda item: (item.data_emissao, _ordem_versao(item.versao)))
    return ultima.analises[-1].situacao if ultima.analises else ""


def _ordem_versao(versao):
    return versao if versao is not None else -1


def _valor_coluna(valores, indices, cabecalho):
    indice = indices.get(_normalizar(cabecalho))
    if indice is None or indice >= len(valores):
        return None
    return valores[indice]


def _data(valor):
    if valor is None or _vazio(valor):
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, (int, float)):
        try:
            convertido = from_excel(valor)
            return convertido.date() if isinstance(convertido, datetime) else convertido
        except (OverflowError, ValueError):
            return None
    texto = _texto(valor)
    for formato in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def _inteiro_ou_none(valor):
    if valor is None or _vazio(valor):
        return None
    try:
        numero = int(float(str(valor).strip()))
        if numero < 0 or str(float(str(valor).strip())) not in {str(float(numero)), str(numero)}:
            return None
        return numero
    except (TypeError, ValueError, OverflowError):
        return None


def _texto(valor):
    if valor is None:
        return ""
    texto = str(valor).strip()
    return "" if texto.casefold() == "<empty value>" else texto


def _vazio(valor):
    return valor is None or (isinstance(valor, str) and (not valor.strip() or valor.strip().casefold() == "<empty value>"))


def _normalizar(valor):
    sem_acentos = "".join(
        caractere
        for caractere in unicodedata.normalize("NFD", str(valor))
        if unicodedata.category(caractere) != "Mn"
    )
    return re.sub(r"[^A-Z0-9]+", "_", sem_acentos.upper()).strip("_")


def _normalizar_codigo(valor):
    return re.sub(r"\s+", "", _texto(valor)).upper()
