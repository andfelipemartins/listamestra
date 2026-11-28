from dataclasses import dataclass
import unicodedata

from django.db import transaction
from openpyxl import load_workbook

from documentos.models import Documento, EmpresaElaboradora


class ErroFormatoElaboracao(ValueError):
    pass


@dataclass
class PreviaElaboracao:
    contrato_id: int
    arquivo_nome: str
    documentos: list
    empresas_novas: list
    codigos_inexistentes: list
    conflitos_planilha: list
    conflitos_existentes: list
    pares: list


def normalizar_cabecalho(valor):
    texto = unicodedata.normalize("NFD", str(valor or ""))
    texto = "".join(caractere for caractere in texto if not unicodedata.combining(caractere))
    return "".join(caractere for caractere in texto.casefold() if caractere.isalnum())


def gerar_previa_elaboracao(arquivo, contrato, *, nome_arquivo=None):
    pares, conflitos_planilha = _ler_planilha(arquivo)
    return _classificar_pares(
        contrato,
        nome_arquivo or getattr(arquivo, "name", "planilha.xlsx"),
        pares,
        conflitos_planilha,
    )


def previa_da_sessao(dados, contrato):
    if int(dados["contrato_id"]) != contrato.pk:
        raise ValueError("A prévia pertence a outro contrato. Envie o arquivo novamente.")
    pares = dados.get("pares", [])
    return _classificar_pares(
        contrato,
        dados.get("arquivo_nome", "planilha.xlsx"),
        pares,
        dados.get("conflitos_planilha", []),
    )


def serializar_previa(previa):
    return {
        "contrato_id": previa.contrato_id,
        "arquivo_nome": previa.arquivo_nome,
        "pares": previa.pares,
        "conflitos_planilha": previa.conflitos_planilha,
    }


@transaction.atomic
def aplicar_previa_elaboracao(previa, contrato, usuario):
    if previa.contrato_id != contrato.pk:
        raise ValueError("A prévia pertence a outro contrato. Gere uma nova prévia.")

    atualizada = _classificar_pares(
        contrato,
        previa.arquivo_nome,
        previa.pares,
        previa.conflitos_planilha,
    )
    empresas_por_nome = {
        empresa.nome_normalizado: empresa
        for empresa in EmpresaElaboradora.objects.filter(contrato=contrato)
    }
    empresas_criadas = 0
    documentos_vinculados = 0
    ja_vinculados = 0
    conflitos = list(atualizada.conflitos_existentes)

    for linha in atualizada.documentos:
        documento = linha["_documento"]
        if documento.elaborado_por_id:
            ja_vinculados += 1
            continue
        nome = linha["empresa"]
        nome_normalizado = EmpresaElaboradora.normalizar_nome(nome)
        empresa = empresas_por_nome.get(nome_normalizado)
        if empresa is None:
            empresa = EmpresaElaboradora.objects.create(contrato=contrato, nome=nome)
            empresas_por_nome[empresa.nome_normalizado] = empresa
            empresas_criadas += 1

        documento.elaborado_por = empresa
        documento._history_user = usuario
        documento._change_reason = f"Importação da elaboração: {previa.arquivo_nome}"
        documento.save(update_fields=("elaborado_por",))
        documentos_vinculados += 1

    return {
        "previa": atualizada,
        "empresas_criadas": empresas_criadas,
        "documentos_vinculados": documentos_vinculados,
        "ja_vinculados": ja_vinculados,
        "conflitos": conflitos,
    }


def _ler_planilha(arquivo):
    try:
        if hasattr(arquivo, "seek"):
            arquivo.seek(0)
        workbook = load_workbook(arquivo, read_only=True, data_only=True)
    except Exception as erro:
        raise ErroFormatoElaboracao("Não foi possível abrir a planilha Excel.") from erro

    try:
        worksheet = next(
            (folha for folha in workbook.worksheets if normalizar_cabecalho(folha.title) == "listadedocumentos"),
            None,
        )
        if worksheet is None:
            raise ErroFormatoElaboracao('A planilha precisa ter a aba "Lista de documentos".')

        colunas = _localizar_colunas(worksheet)
        por_codigo = {}
        for linha in worksheet.iter_rows(min_row=colunas["linha"] + 1, values_only=True):
            codigo = _texto(_valor_coluna(linha, colunas["codigo"]))
            empresa = _texto(_valor_coluna(linha, colunas["elaboracao"]))
            if not codigo or not empresa:
                continue
            codigo_chave = codigo.casefold()
            empresa_normalizada = EmpresaElaboradora.normalizar_nome(empresa)
            if codigo_chave not in por_codigo:
                por_codigo[codigo_chave] = {"codigo": codigo, "empresas": {}}
            por_codigo[codigo_chave]["empresas"].setdefault(empresa_normalizada, empresa)

        pares = []
        conflitos_planilha = []
        for registro in por_codigo.values():
            empresas = registro["empresas"]
            if len(empresas) > 1:
                conflitos_planilha.append(
                    {"codigo": registro["codigo"], "empresas": sorted(empresas.values(), key=str.casefold)}
                )
            else:
                nome = next(iter(empresas.values()))
                pares.append({"codigo": registro["codigo"], "empresa": nome})
        return pares, conflitos_planilha
    finally:
        workbook.close()


def _localizar_colunas(worksheet):
    for numero_linha, valores in enumerate(worksheet.iter_rows(min_row=1, max_row=20, values_only=True), start=1):
        normalizados = [normalizar_cabecalho(valor) for valor in valores]
        if "codigo" in normalizados and "elaboracao" in normalizados:
            return {
                "linha": numero_linha,
                "codigo": normalizados.index("codigo"),
                "elaboracao": normalizados.index("elaboracao"),
            }
    raise ErroFormatoElaboracao(
        'Não encontrei as colunas "CÓDIGO" e "ELABORAÇÃO" nas primeiras 20 linhas da aba.'
    )


def _classificar_pares(contrato, arquivo_nome, pares, conflitos_planilha):
    documentos = {
        documento.identificador_base.casefold(): documento
        for documento in Documento.objects.filter(contrato=contrato).select_related("elaborado_por")
    }
    empresas_por_nome = {
        empresa.nome_normalizado: empresa
        for empresa in EmpresaElaboradora.objects.filter(contrato=contrato)
    }

    resultado_documentos = []
    empresas_novas = set()
    codigos_inexistentes = []
    conflitos_existentes = []
    for par in pares:
        codigo = _texto(par.get("codigo"))
        nome = _texto(par.get("empresa"))
        if not codigo or not nome:
            continue
        documento = documentos.get(codigo.casefold())
        if documento is None:
            codigos_inexistentes.append(codigo)
            continue
        nome_normalizado = EmpresaElaboradora.normalizar_nome(nome)
        empresa_existente = empresas_por_nome.get(nome_normalizado)
        if documento.elaborado_por_id and documento.elaborado_por.nome_normalizado != nome_normalizado:
            conflitos_existentes.append(
                {
                    "codigo": codigo,
                    "empresa_atual": documento.elaborado_por.nome,
                    "empresa_planilha": nome,
                }
            )
            continue
        resultado_documentos.append(
            {
                "codigo": documento.identificador_base,
                "empresa": empresa_existente.nome if empresa_existente else nome,
                "acao": "Já vinculado" if documento.elaborado_por_id else "Vincular",
                "_documento": documento,
            }
        )
        if not empresa_existente and not documento.elaborado_por_id:
            empresas_novas.add(nome)

    return PreviaElaboracao(
        contrato_id=contrato.pk,
        arquivo_nome=arquivo_nome,
        documentos=resultado_documentos,
        empresas_novas=sorted(empresas_novas, key=str.casefold),
        codigos_inexistentes=sorted(set(codigos_inexistentes), key=str.casefold),
        conflitos_planilha=conflitos_planilha,
        conflitos_existentes=conflitos_existentes,
        pares=pares,
    )


def _valor_coluna(linha, indice):
    return linha[indice] if indice < len(linha) else None


def _texto(valor):
    if valor is None:
        return ""
    return " ".join(str(valor).split())
