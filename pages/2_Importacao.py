"""
pages/2_Importacao.py

Página de importação de dados para o SCLME.
Permite criar o contrato e importar a Lista de Documentos e o Índice (ID) via upload.
"""

import os
import sys
import tempfile

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core.importers.lista_importer import ListaImporter
from core.importers.id_importer import IdImporter
from db.connection import get_connection

# ---------------------------------------------------------------------------
# Acesso a dados
# ---------------------------------------------------------------------------

def _listar_contratos() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, nome, cliente FROM contratos WHERE ativo = 1 ORDER BY nome"
        ).fetchall()
    return [dict(r) for r in rows]


def _criar_contrato(nome: str, cliente: str) -> int:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO contratos (nome, cliente) VALUES (?, ?)", (nome, cliente)
        )
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _historico_importacoes(contrato_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT origem, arquivo_importado, total_registros, total_novos,
                   total_atualizados, total_erros, status, confirmado_em
            FROM importacoes
            WHERE contrato_id = ?
            ORDER BY id DESC
            LIMIT 10
            """,
            (contrato_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _importar_arquivo(conteudo: bytes, contrato_id: int, origem: str):
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        f.write(conteudo)
        tmp = f.name
    try:
        if origem == "lista":
            return ListaImporter().importar(tmp, contrato_id)
        else:
            return IdImporter().importar(tmp, contrato_id)
    finally:
        os.unlink(tmp)


# ---------------------------------------------------------------------------
# Componentes de UI
# ---------------------------------------------------------------------------

def _secao_contrato() -> int | None:
    """Retorna o contrato_id selecionado, ou None se nenhum disponível."""
    contratos = _listar_contratos()

    st.subheader("Contrato")

    if contratos:
        opcoes = {c["nome"]: c["id"] for c in contratos}
        nome_sel = st.selectbox("Contrato ativo", list(opcoes.keys()))
        contrato_id = opcoes[nome_sel]
    else:
        st.info("Nenhum contrato cadastrado. Crie um abaixo para começar.")
        contrato_id = None

    with st.expander("Criar novo contrato"):
        with st.form("form_novo_contrato"):
            nome = st.text_input("Nome do contrato", placeholder="Ex: Contrato de Ragueb")
            cliente = st.text_input("Cliente", placeholder="Ex: Metrô de São Paulo")
            criar = st.form_submit_button("Criar")
        if criar:
            if not nome.strip():
                st.error("Informe o nome do contrato.")
            else:
                cid = _criar_contrato(nome.strip(), cliente.strip())
                st.success(f"Contrato **{nome}** criado com sucesso!")
                st.rerun()

    return contrato_id


def _resultado_badge(resultado, origem: str):
    if origem == "lista":
        novos = resultado.novos_documentos
        atualizados = resultado.documentos_atualizados
        total_rev = resultado.total_revisoes
        st.success(
            f"Importação concluída — "
            f"**{novos}** documentos novos, **{atualizados}** atualizados, "
            f"**{total_rev}** revisões processadas."
        )
    else:
        st.success(
            f"Importação concluída — "
            f"**{resultado.novos}** documentos novos, "
            f"**{resultado.atualizados}** atualizados."
        )

    if resultado.total_inconsistencias > 0:
        st.warning(
            f"{resultado.total_inconsistencias} inconsistência(s) registrada(s) no banco. "
            "Verifique a tabela `inconsistencias` para detalhes."
        )
        with st.expander("Ver inconsistências desta importação"):
            for inc in resultado.inconsistencias[:20]:
                st.markdown(f"- `{inc['codigo']}` — **{inc['tipo']}**: {inc['descricao']}")
            if len(resultado.inconsistencias) > 20:
                st.caption(f"... e mais {len(resultado.inconsistencias) - 20} ocorrências.")


def _tab_lista(contrato_id: int):
    st.markdown(
        "Importa a aba **Lista de documentos** do arquivo Excel. "
        "Cada linha é tratada como uma revisão de um documento."
    )
    arquivo = st.file_uploader(
        "Arquivo Excel (.xlsx)", type=["xlsx"], key="upload_lista"
    )
    if arquivo:
        st.caption(f"Arquivo selecionado: **{arquivo.name}** ({arquivo.size // 1024} KB)")
        if st.button("Importar Lista de Documentos", type="primary", key="btn_lista"):
            with st.spinner("Importando…"):
                try:
                    resultado = _importar_arquivo(arquivo.read(), contrato_id, "lista")
                    _resultado_badge(resultado, "lista")
                except Exception as e:
                    st.error(f"Erro na importação: {e}")


def _tab_id(contrato_id: int):
    st.markdown(
        "Importa a aba **ID XX-XX-XXXX** do arquivo Excel (Índice de Documentos). "
        "Representa o escopo completo do contrato — o 100% de referência."
    )
    arquivo = st.file_uploader(
        "Arquivo Excel (.xlsx)", type=["xlsx"], key="upload_id"
    )
    if arquivo:
        st.caption(f"Arquivo selecionado: **{arquivo.name}** ({arquivo.size // 1024} KB)")
        if st.button("Importar Índice (ID)", type="primary", key="btn_id"):
            with st.spinner("Importando…"):
                try:
                    resultado = _importar_arquivo(arquivo.read(), contrato_id, "id")
                    _resultado_badge(resultado, "id")
                except ValueError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"Erro na importação: {e}")


def _historico(contrato_id: int):
    historico = _historico_importacoes(contrato_id)
    if not historico:
        st.info("Nenhuma importação realizada ainda.")
        return

    import pandas as pd
    df = pd.DataFrame(historico)
    df = df.rename(columns={
        "origem":           "Origem",
        "arquivo_importado":"Arquivo",
        "total_registros":  "Lidos",
        "total_novos":      "Novos",
        "total_atualizados":"Atualizados",
        "total_erros":      "Erros",
        "status":           "Status",
        "confirmado_em":    "Data",
    })
    df["Data"] = df["Data"].str[:16].str.replace("T", " ")
    st.dataframe(df, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Página
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Importação — SCLME", page_icon="📥", layout="wide")

st.title("📥 Importação de Dados")

contrato_id = _secao_contrato()

if contrato_id is None:
    st.stop()

st.divider()

tab_lista, tab_id, tab_hist = st.tabs([
    "📋 Lista de Documentos",
    "📑 Índice de Documentos (ID)",
    "🕘 Histórico",
])

with tab_lista:
    _tab_lista(contrato_id)

with tab_id:
    _tab_id(contrato_id)

with tab_hist:
    _historico(contrato_id)
