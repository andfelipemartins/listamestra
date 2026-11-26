"""Leitura declarativa dos formatos de ID, sem escrita no banco de dados."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from typing import BinaryIO, Iterable
import re
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from core.perfil import PerfilContrato, Separador
from core.perfil.codigo import ErroCodigo, interpretar


FORMATOS_ID = {
    "excel_id": {
        "planilha": "Planilha1",
        "cabecalho_codigo": "Name",
        "cabecalho_titulo": "[Título:]",
        "cabecalho_excluido": "[Excluído]",
        "cabecalhos_segmentos": {
            "tipo": "[Sigla:]",
            "linha": "[Linha:]",
            "trecho": "[Trecho \\ Sistema \\ Escopo:]",
            "subtrecho": "[Subtrecho \\ Subsistema \\ Campo1:]",
            "unidade": "[UC \\  Loc. Geográfica \\ Campo2:]",
            "etapa": "[Etapa do Projeto:]",
            "classe": "[Classe e Subclasse \\ Componente:]",
            "sequencial": "[Sequencial:]",
        },
    },
    "extracao_pw": {
        "planilha": "ID",
        "cabecalho_codigo": "Name",
        "cabecalho_titulo": "Título:",
        "cabecalho_excluido": "Excluído",
        "cabecalhos_segmentos": {
            "tipo": "Sigla:",
            "linha": "Linha:",
            "trecho": "Trecho \\ Sistema \\ Escopo:",
            "subtrecho": "Subtrecho \\ Subsistema \\ Campo1:",
            "unidade": "UC \\  Loc. Geográfica \\ Campo2:",
            "etapa": "Etapa do Projeto:",
            "classe": "Classe e Subclasse \\ Componente:",
            "sequencial": "Sequencial:",
        },
    },
}

CATEGORIAS = (
    "novos",
    "ja_existentes",
    "titulos_divergentes",
    "codigos_invalidos",
    "atributos_divergentes",
    "linhas_ilegiveis",
    "excluidos",
)
ROTULOS_CATEGORIA = {
    "novos": "Novo",
    "ja_existentes": "Já existente",
    "titulos_divergentes": "Título divergente",
    "codigos_invalidos": "Código inválido",
    "atributos_divergentes": "Atributo divergente do Name",
    "linhas_ilegiveis": "Linha ilegível",
    "excluidos": "Excluído",
}


@dataclass(frozen=True)
class LinhaPrevia:
    numero_linha: int
    codigo: str
    titulo: str
    excluido: bool
    categoria: str
    identificador_base: str = ""
    segmentos: dict[str, str] | None = None
    campo_falhou: str = ""
    caixa_falhou: str = ""
    mensagem: str = ""
    dados_linha: dict | None = None

    @property
    def categoria_display(self):
        return ROTULOS_CATEGORIA[self.categoria]


@dataclass(frozen=True)
class PreviaID:
    contrato_id: int
    perfil_id: int
    fonte: str
    codigo_indice: str
    revisao: str
    arquivo_nome: str
    formato: str
    linhas: tuple[LinhaPrevia, ...]

    @property
    def contagens(self) -> dict[str, int]:
        return {categoria: sum(linha.categoria == categoria for linha in self.linhas) for categoria in CATEGORIAS}

    @property
    def linhas_validas(self) -> int:
        return sum(bool(linha.identificador_base) for linha in self.linhas)

    @property
    def linhas_fora(self) -> int:
        return len(self.linhas) - self.linhas_validas


class ErroFormatoID(ValueError):
    """Arquivo sem cabeçalho reconhecido ou sem metadados suficientes."""


def gerar_previa_id(
    arquivo: BinaryIO,
    *,
    nome_arquivo: str,
    contrato_id: int,
    perfil_id: int,
    perfil: PerfilContrato,
    documentos_existentes: Iterable[tuple[str, str]] = (),
    codigo_indice: str = "",
    revisao: str = "",
    data_importacao: date | None = None,
) -> PreviaID:
    """Lê e classifica as linhas; não executa operações no banco."""
    arquivo.seek(0)
    try:
        workbook = load_workbook(arquivo, read_only=True, data_only=True)
    except (BadZipFile, InvalidFileException, OSError, ValueError) as erro:
        raise ErroFormatoID(f"Não foi possível abrir o arquivo Excel: {erro}") from erro
    try:
        formato_id, worksheet, cabecalho, indices = _detectar_formato(workbook)
        formato = FORMATOS_ID[formato_id]
        campos_relevantes = {
            formato["cabecalho_codigo"],
            formato["cabecalho_titulo"],
            formato["cabecalho_excluido"],
            *formato["cabecalhos_segmentos"].values(),
        }
        colunas_relevantes = sorted(
            {
                indices[_normalizar_cabecalho(nome)]
                for nome in campos_relevantes
                if _normalizar_cabecalho(nome) in indices
            }
        )
        intervalos = _intervalos_contiguos(colunas_relevantes)
        iteradores = [
            worksheet.iter_rows(min_row=2, min_col=inicio + 1, max_col=fim + 1)
            for inicio, fim in intervalos
        ]
        existentes = {identificador: titulo for identificador, titulo in documentos_existentes}
        linhas: list[LinhaPrevia] = []
        for numero_linha, grupos in enumerate(zip(*iteradores), start=2):
            celulas = {}
            for (inicio, fim), grupo in zip(intervalos, grupos):
                celulas.update(zip(range(inicio, fim + 1), grupo))
            dados = {
                _normalizar_cabecalho(nome): _valor_coluna(celulas, indices, nome)
                for nome in campos_relevantes
            }
            if all(_vazio(valor) for valor in dados.values()):
                continue
            linha = _classificar_linha(
                numero_linha=numero_linha,
                dados=dados,
                formato=formato,
                indices=indices,
                perfil=perfil,
                existentes=existentes,
                formato_id=formato_id,
            )
            dados_linha = {
                nome: _valor_json(dados[_normalizar_cabecalho(nome)])
                for nome in campos_relevantes
                if _normalizar_cabecalho(nome) in indices
            }
            linhas.append(replace(linha, dados_linha=dados_linha))
            item = linhas[-1]
            if item.identificador_base:
                existentes.setdefault(item.identificador_base, item.titulo)

        if formato_id == "extracao_pw":
            codigo_indice = "EXTRACAO-PW"
            revisao = (data_importacao or date.today()).isoformat()
            fonte = "extracao_pw"
        else:
            fonte = "excel_id"
            codigo_por_nome, revisao_por_nome = _metadados_do_nome(nome_arquivo)
            codigo_indice = codigo_indice.strip() or codigo_por_nome
            revisao = revisao.strip() or revisao_por_nome
        if not codigo_indice or not revisao:
            raise ErroFormatoID("Informe o código e a revisão do ID.")
        return PreviaID(
            contrato_id=contrato_id,
            perfil_id=perfil_id,
            fonte=fonte,
            codigo_indice=codigo_indice,
            revisao=revisao,
            arquivo_nome=Path(nome_arquivo).name,
            formato=formato_id,
            linhas=tuple(linhas),
        )
    except ErroFormatoID:
        raise
    except (BadZipFile, InvalidFileException, OSError, ValueError) as erro:
        raise ErroFormatoID(f"Não foi possível ler o arquivo Excel: {erro}") from erro
    finally:
        workbook.close()


def gerar_previa_linhas_recusadas(
    inconsistencias,
    *,
    contrato_id: int,
    perfil_id: int,
    perfil: PerfilContrato,
    documentos_existentes: Iterable[tuple[str, str]] = (),
) -> PreviaID:
    """Reinterpreta linhas persistidas sem abrir novamente o arquivo de origem."""
    inconsistencias = list(inconsistencias)
    if not inconsistencias:
        raise ErroFormatoID("Esta importação não tem linhas recusadas para reprocessar.")
    importacao = inconsistencias[0].importacao_id
    if importacao is None or any(item.importacao_id_id != importacao.pk for item in inconsistencias):
        raise ErroFormatoID("As linhas precisam pertencer à mesma importação de ID.")
    indice = importacao.indice
    formato_id = indice.fonte
    if formato_id not in FORMATOS_ID:
        raise ErroFormatoID("A fonte da importação não corresponde a um formato conhecido de ID.")

    existentes = {identificador: titulo for identificador, titulo in documentos_existentes}
    linhas = []
    for inconsistencia in inconsistencias:
        dados_linha = inconsistencia.dados_linha or {}
        dados = {
            _normalizar_cabecalho(nome): valor
            for nome, valor in dados_linha.items()
        }
        indices = {nome: posicao for posicao, nome in enumerate(dados)}
        linha = _classificar_linha(
            numero_linha=inconsistencia.numero_linha,
            dados=dados,
            formato=FORMATOS_ID[formato_id],
            indices=indices,
            perfil=perfil,
            existentes=existentes,
            formato_id=formato_id,
        )
        linhas.append(replace(linha, dados_linha=dados_linha))
        if linha.identificador_base:
            existentes.setdefault(linha.identificador_base, linha.titulo)

    return PreviaID(
        contrato_id=contrato_id,
        perfil_id=perfil_id,
        fonte=indice.fonte,
        codigo_indice=indice.codigo,
        revisao=indice.revisao,
        arquivo_nome=indice.arquivo_nome,
        formato=formato_id,
        linhas=tuple(linhas),
    )


def _detectar_formato(workbook):
    encontrados = []
    for worksheet in workbook.worksheets:
        cabecalho = next(
            worksheet.iter_rows(min_row=1, max_row=1, values_only=True),
            (),
        )
        indices: dict[str, int] = {}
        duplicados: set[str] = set()
        for indice, valor in enumerate(cabecalho):
            if valor is None:
                continue
            chave = _normalizar_cabecalho(valor)
            if chave in indices:
                duplicados.add(chave)
            else:
                indices[chave] = indice
        for chave, formato in FORMATOS_ID.items():
            obrigatorios = (
                formato["cabecalho_codigo"],
                formato["cabecalho_titulo"],
                formato["cabecalho_excluido"],
            )
            chaves = [_normalizar_cabecalho(nome) for nome in obrigatorios]
            if all(nome in indices and nome not in duplicados for nome in chaves):
                encontrados.append((chave, worksheet, cabecalho, indices))
    if len(encontrados) != 1:
        raise ErroFormatoID(
            "Não foi possível identificar um formato único de ID pelos cabeçalhos. "
            "O arquivo deve conter Name, título e marca de excluído de um formato conhecido."
        )
    return encontrados[0]


def _classificar_linha(*, numero_linha, dados, formato, indices, perfil, existentes, formato_id):
    codigo_coluna = _normalizar_cabecalho(formato["cabecalho_codigo"])
    titulo_coluna = _normalizar_cabecalho(formato["cabecalho_titulo"])
    excluido_coluna = _normalizar_cabecalho(formato["cabecalho_excluido"])
    codigo_bruto = dados.get(codigo_coluna)
    titulo_bruto = dados.get(titulo_coluna)
    codigo = str(codigo_bruto).strip() if not _vazio(codigo_bruto) else ""
    titulo = str(titulo_bruto).strip() if not _vazio(titulo_bruto) else ""
    excluido = _interpretar_excluido(dados.get(excluido_coluna))
    if formato_id == "extracao_pw" and (excluido is None or not titulo):
        return LinhaPrevia(
            numero_linha, codigo, titulo, bool(excluido), "linhas_ilegiveis",
            mensagem=_mensagem_extracao_defeituosa(),
        )
    if excluido is None or not titulo:
        return LinhaPrevia(
            numero_linha, codigo, titulo, bool(excluido), "linhas_ilegiveis",
            mensagem="Linha sem título ou com marca de excluído ilegível.",
        )

    if formato_id == "extracao_pw" and not codigo:
        return LinhaPrevia(
            numero_linha, codigo, titulo, excluido, "linhas_ilegiveis",
            mensagem=_mensagem_extracao_defeituosa(),
        )
    if not codigo:
        codigo, erro_composicao = _montar_codigo_das_caixas(dados, formato, indices, perfil)
        if erro_composicao:
            campo, caixa, mensagem = erro_composicao
            return LinhaPrevia(
                numero_linha, codigo, titulo, excluido, "linhas_ilegiveis",
                campo_falhou=campo, caixa_falhou=caixa, mensagem=mensagem,
            )

    resultado = interpretar(perfil, codigo)
    if isinstance(resultado, ErroCodigo):
        caixa = next(
            (campo.rotulo for campo in perfil.codigo.campos if campo.nome == resultado.segmento),
            resultado.segmento or "formato do código",
        )
        categoria = "linhas_ilegiveis" if formato_id == "extracao_pw" else "codigos_invalidos"
        return LinhaPrevia(
            numero_linha, codigo, titulo, excluido, categoria,
            campo_falhou=resultado.segmento or "",
            caixa_falhou=caixa,
            mensagem=(
                _mensagem_extracao_defeituosa()
                if formato_id == "extracao_pw"
                else resultado.mensagem
            ),
        )

    if formato_id == "extracao_pw":
        codigo_das_caixas, erro_composicao = _montar_codigo_das_caixas(
            dados, formato, indices, perfil
        )
        if erro_composicao:
            campo, caixa, _ = erro_composicao
            return LinhaPrevia(
                numero_linha, codigo, titulo, excluido, "linhas_ilegiveis",
                campo_falhou=campo,
                caixa_falhou=caixa,
                mensagem=_mensagem_extracao_defeituosa(),
            )
        resultado_caixas = interpretar(perfil, codigo_das_caixas)
        if isinstance(resultado_caixas, ErroCodigo):
            divergencias = _divergencias_dos_atributos(
                dados, formato, indices, perfil, resultado.segmentos
            )
            return LinhaPrevia(
                numero_linha, codigo, titulo, excluido,
                "atributos_divergentes" if divergencias else "linhas_ilegiveis",
                campo_falhou=resultado_caixas.segmento or "",
                caixa_falhou=resultado_caixas.segmento or "",
                mensagem=_mensagem_atributos_divergentes(divergencias)
                if divergencias
                else _mensagem_extracao_defeituosa(),
            )
        if dict(resultado_caixas.segmentos) != dict(resultado.segmentos):
            divergencias = _divergencias_dos_atributos(
                dados, formato, indices, perfil, resultado.segmentos
            )
            return LinhaPrevia(
                numero_linha, codigo, titulo, excluido,
                "atributos_divergentes" if divergencias else "linhas_ilegiveis",
                mensagem=_mensagem_atributos_divergentes(divergencias)
                if divergencias
                else _mensagem_extracao_defeituosa(),
            )

    if excluido:
        categoria = "excluidos"
    else:
        titulo_existente = existentes.get(resultado.identificador_base)
        if titulo_existente is None:
            categoria = "novos"
        elif titulo_existente.strip().casefold() != titulo.casefold():
            categoria = "titulos_divergentes"
        else:
            categoria = "ja_existentes"
    return LinhaPrevia(
        numero_linha=numero_linha,
        codigo=resultado.original.strip().upper(),
        titulo=titulo,
        excluido=excluido,
        categoria=categoria,
        identificador_base=resultado.identificador_base,
        segmentos=dict(resultado.segmentos),
    )


def _montar_codigo_das_caixas(dados, formato, indices, perfil):
    valores = {}
    cabecalhos = formato["cabecalhos_segmentos"]
    for segmento in perfil.codigo.campos:
        cabecalho = cabecalhos.get(segmento.nome)
        if cabecalho is None:
            if segmento.obrigatorio:
                return "", (
                    segmento.nome,
                    segmento.rotulo,
                    f"O formato não mapeia a caixa obrigatória '{segmento.rotulo}'.",
                )
            continue
        chave = _normalizar_cabecalho(cabecalho)
        if chave not in indices:
            if segmento.obrigatorio:
                return "", (
                    segmento.nome,
                    segmento.rotulo,
                    f"O cabeçalho da caixa '{segmento.rotulo}' não foi encontrado.",
                )
            continue
        valor = dados.get(chave)
        if _vazio(valor):
            if segmento.obrigatorio:
                return "", (
                    segmento.nome,
                    segmento.rotulo,
                    f"A caixa obrigatória '{segmento.rotulo}' está vazia.",
                )
            continue
        valor_texto = str(valor).strip().upper()
        if isinstance(valor, (int, float)) and int(valor) == valor:
            largura = _largura_numerica(segmento.padrao_regex)
            if largura:
                valor_texto = str(int(valor)).zfill(largura)
        valores[segmento.nome] = valor_texto

    partes_codigo: list[str] = []
    separador_pendente = None
    for parte in perfil.codigo.segmentos:
        if isinstance(parte, Separador):
            if partes_codigo:
                separador_pendente = parte.texto
            continue
        valor = valores.get(parte.nome)
        if valor is None:
            continue
        if partes_codigo and separador_pendente:
            partes_codigo.append(separador_pendente)
        partes_codigo.append(valor)
        separador_pendente = None
    return "".join(partes_codigo), None


def _divergencias_dos_atributos(dados, formato, indices, perfil, segmentos_name):
    divergencias = []
    for campo in perfil.codigo.campos:
        cabecalho = formato["cabecalhos_segmentos"].get(campo.nome)
        if cabecalho is None:
            continue
        chave = _normalizar_cabecalho(cabecalho)
        if chave not in indices:
            continue
        valor_bruto = dados.get(chave)
        if _vazio(valor_bruto):
            continue
        valor = str(valor_bruto).strip().upper()
        if isinstance(valor_bruto, (int, float)) and int(valor_bruto) == valor_bruto:
            largura = _largura_numerica(campo.padrao_regex)
            if largura:
                valor = str(int(valor_bruto)).zfill(largura)
        esperado = segmentos_name.get(campo.nome)
        if esperado is None or valor == str(esperado).strip().upper():
            continue
        rotulo_coluna = str(cabecalho).rstrip(":")
        rotulo_campo = campo.rotulo.casefold()
        divergencias.append((rotulo_campo, esperado, rotulo_coluna, valor))
    return divergencias


def _mensagem_atributos_divergentes(divergencias):
    if not divergencias:
        return ""
    partes = [
        f"Name e atributo divergem: o Name diz {rotulo} {esperado}; a coluna {coluna} diz {valor}."
        for rotulo, esperado, coluna, valor in divergencias
    ]
    return " ".join((*partes, "Confira no PW qual está certo, corrija e reextraia."))


def _mensagem_extracao_defeituosa():
    return (
        "A linha veio defeituosa da extração do PW (colunas fora do lugar). "
        "Reextraia essa disciplina e importe de novo."
    )


def _valor_coluna(valores, indices, cabecalho):
    indice = indices.get(_normalizar_cabecalho(cabecalho))
    celula = valores.get(indice) if indice is not None else None
    return celula.value if celula is not None else None


def _valor_json(valor):
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    return str(valor)


def _intervalos_contiguos(colunas):
    intervalos = []
    for coluna in colunas:
        if intervalos and coluna == intervalos[-1][1] + 1:
            intervalos[-1] = (intervalos[-1][0], coluna)
        else:
            intervalos.append((coluna, coluna))
    return intervalos


def _normalizar_cabecalho(valor):
    return re.sub(r"\s+", " ", str(valor).strip()).casefold()


def _largura_numerica(padrao):
    encontrado = re.fullmatch(r"\\d\{(\d+)\}", padrao)
    return int(encontrado.group(1)) if encontrado else 0


def _metadados_do_nome(nome_arquivo):
    base = Path(nome_arquivo).stem
    encontrado = re.fullmatch(r"(?P<codigo>.+)-(?P<revisao>\d+)", base)
    if encontrado:
        return encontrado.group("codigo"), encontrado.group("revisao")
    return base, "1"


def _vazio(valor):
    return valor is None or (isinstance(valor, str) and not valor.strip())


def _interpretar_excluido(valor):
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)) and valor in (0, 1):
        return bool(valor)
    if isinstance(valor, str):
        normalizado = valor.strip().casefold()
        if normalizado in {"0", "false", "falso", "nao", "não", "no", "n"}:
            return False
        if normalizado in {"1", "true", "verdadeiro", "sim", "yes", "s"}:
            return True
    return None
