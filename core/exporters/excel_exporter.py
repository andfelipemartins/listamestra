"""
core/exporters/excel_exporter.py

Geração de relatórios Excel para o SCLME.

Todas as funções retornam bytes prontos para st.download_button.
"""

import io
from typing import Optional

import pandas as pd

from core.engine.comparacao import ResultadoComparacao


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _writer(buffer: io.BytesIO) -> pd.ExcelWriter:
    return pd.ExcelWriter(buffer, engine="openpyxl")


def _exportar_df(df: pd.DataFrame, writer: pd.ExcelWriter, sheet: str,
                 rename: Optional[dict] = None) -> None:
    out = df.rename(columns=rename) if rename else df
    out.to_excel(writer, sheet_name=sheet, index=False)


# ---------------------------------------------------------------------------
# 1. Lista Mestra
# ---------------------------------------------------------------------------

def exportar_lista_mestra(df_progresso: pd.DataFrame, nome_contrato: str) -> bytes:
    """
    Exporta todos os documentos previstos com status calculado.

    df_progresso: saída de carregar_progresso() — contém codigo, titulo,
                  trecho, nome_trecho, tipo, situacao, data_emissao, status.
    """
    buf = io.BytesIO()
    with _writer(buf) as writer:
        rename = {
            "codigo":       "Código",
            "tipo":         "Tipo",
            "nome_trecho":  "Trecho",
            "titulo":       "Título",
            "status_atual": "Status Atual",
            "ja_aprovado":  "Já Aprovado",
            "situacao":     "Situação",
            "data_emissao": "Data Emissão",
        }
        cols = [c for c in rename if c in df_progresso.columns]
        _exportar_df(
            df_progresso[cols],
            writer,
            sheet="Lista Mestra",
            rename=rename,
        )
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 2. Relatório de alertas
# ---------------------------------------------------------------------------

def exportar_alertas(alertas: list[dict], nome_contrato: str) -> bytes:
    """
    Duas abas: 'Análise Prolongada' e 'Sem Revisão'.
    """
    buf = io.BytesIO()
    prolongada = [a for a in alertas if a["tipo"] == "analise_prolongada"]
    sem_inicio = [a for a in alertas if a["tipo"] == "sem_inicio"]

    with _writer(buf) as writer:
        if prolongada:
            df_p = pd.DataFrame(prolongada)[["codigo", "titulo", "dias", "data_referencia", "mensagem"]]
            _exportar_df(
                df_p,
                writer,
                sheet="Análise Prolongada",
                rename={
                    "codigo":          "Código",
                    "titulo":          "Título",
                    "dias":            "Dias",
                    "data_referencia": "Emitido em",
                    "mensagem":        "Situação",
                },
            )
        else:
            pd.DataFrame(columns=["Código", "Título"]).to_excel(
                writer, sheet_name="Análise Prolongada", index=False
            )

        if sem_inicio:
            df_s = pd.DataFrame(sem_inicio)[["codigo", "titulo"]]
            _exportar_df(
                df_s,
                writer,
                sheet="Sem Revisão",
                rename={"codigo": "Código", "titulo": "Título"},
            )
        else:
            pd.DataFrame(columns=["Código", "Título"]).to_excel(
                writer, sheet_name="Sem Revisão", index=False
            )

    return buf.getvalue()


# ---------------------------------------------------------------------------
# 3. Histórico de revisões de um documento
# ---------------------------------------------------------------------------

def exportar_historico_revisoes(revisoes: list[dict], doc: dict, nome_contrato: str) -> bytes:
    """
    Uma aba com a linha do tempo completa de revisões do documento.

    revisoes: lista de dicts conforme retornado pela query de 5_Documento.py.
    doc:      dict com os campos do documento (codigo, titulo, etc.)
    """
    buf = io.BytesIO()
    rename = {
        "emissao_inicial":  "Emissão",
        "revisao":          "Rev.",
        "versao":           "Ver.",
        "label_revisao":    "Label",
        "data_elaboracao":  "Data Elaboração",
        "data_emissao":     "Data Emissão",
        "data_analise":     "Data Análise",
        "dias_elaboracao":  "Dias Elab.",
        "dias_analise":     "Dias Análise",
        "situacao":         "Situação",
        "situacao_real":    "Situação Real",
        "retorno":          "Retorno",
        "emissao_circular": "Nº Circular",
        "analise_circular": "Análise Interna",
        "data_circular":    "Data Circular",
    }

    with _writer(buf) as writer:
        if revisoes:
            df = pd.DataFrame(revisoes)
            cols = [c for c in rename if c in df.columns]
            _exportar_df(
                df[cols],
                writer,
                sheet="Revisões",
                rename=rename,
            )
        else:
            pd.DataFrame(columns=list(rename.values())).to_excel(
                writer, sheet_name="Revisões", index=False
            )

    return buf.getvalue()


# ---------------------------------------------------------------------------
# 4. Comparação ID × Lista
# ---------------------------------------------------------------------------

def exportar_comparacao(resultado: ResultadoComparacao, nome_contrato: str) -> bytes:
    """
    Três abas: 'Ausentes', 'Extras', 'Divergências'.
    """
    buf = io.BytesIO()

    def _sheet(df: pd.DataFrame, writer, name: str, rename: dict) -> None:
        if not df.empty:
            cols = [c for c in rename if c in df.columns]
            _exportar_df(df[cols], writer, sheet=name, rename=rename)
        else:
            pd.DataFrame(columns=list(rename.values())).to_excel(
                writer, sheet_name=name, index=False
            )

    with _writer(buf) as writer:
        _sheet(
            resultado.ausentes, writer, "Ausentes",
            {"codigo": "Código", "titulo": "Título", "tipo": "Tipo", "nome_trecho": "Trecho"},
        )
        _sheet(
            resultado.extras, writer, "Extras",
            {"codigo": "Código", "titulo": "Título", "tipo": "Tipo", "nome_trecho": "Trecho"},
        )
        _sheet(
            resultado.divergencias, writer, "Divergências",
            {
                "codigo":         "Código",
                "titulo_id":      "Título (ID)",
                "titulo_lista":   "Título (Lista)",
                "nome_trecho":    "Trecho",
            },
        )

    return buf.getvalue()
