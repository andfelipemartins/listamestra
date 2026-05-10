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
import pandas as pd

from core.importers.lista_importer import ListaImporter
from core.importers.id_importer import IdImporter
from core.importers.arquivos_importer import ArquivosImporter
from core.engine.preview_arquivos import gerar_preview
from core.engine.status import NOME_TRECHO
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


def _tab_arquivos(contrato_id: int):
    # ── Estado ──────────────────────────────────────────────────────────────
    # Dois estados possíveis:
    #   A) Sem preview → mostra upload
    #   B) Com preview → mostra tabela de confirmação
    PREVIEW_KEY = f"preview_arquivos_{contrato_id}"
    NOME_KEY    = f"preview_nome_{contrato_id}"

    # ── Estado B: preview aguardando confirmação ─────────────────────────────
    if PREVIEW_KEY in st.session_state:
        preview  = st.session_state[PREVIEW_KEY]
        nome_txt = st.session_state[NOME_KEY]

        st.markdown(f"**Arquivo analisado:** `{nome_txt}`")

        # KPIs de contexto
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Arquivos novos", preview.total_arquivos_novos)
        c2.metric("Já registrados", preview.ja_existentes)
        c3.metric("Sem doc no banco", len(preview.sem_documento))
        c4.metric("OBSOLETO ignorados", preview.obsoletos)
        if preview.nao_reconhecidos:
            st.caption(f"⚠️ {len(preview.nao_reconhecidos)} nome(s) não reconhecido(s) — serão ignorados.")

        if preview.vazio:
            st.success("Nenhum arquivo novo encontrado — Lista já está atualizada.")
            if st.button("Nova análise", key="btn_nova_analise"):
                del st.session_state[PREVIEW_KEY]
                del st.session_state[NOME_KEY]
                st.rerun()
            return

        st.divider()
        st.markdown(
            f"**{preview.total_documentos_novos} documento(s) com arquivo(s) novo(s).** "
            "Confirme ou preencha o **Objeto** de cada um antes de salvar."
        )

        # Monta DataFrame com uma linha por documento
        rows = []
        for codigo, items in preview.novos_por_codigo.items():
            exts = sorted({i.extensao.upper() for i in items})
            revs = sorted({
                f"{i.label_revisao}-{i.versao}" if i.versao else i.label_revisao
                for i in items
            })
            tipo = codigo.split("-")[0]
            trecho_code = codigo.split(".")[1] if "." in codigo else "00"
            rows.append({
                "Código":   codigo,
                "Tipo":     tipo,
                "Trecho":   NOME_TRECHO.get(trecho_code, trecho_code),
                "Arquivos": f"{', '.join(exts)} | Rev {', '.join(revs)}",
                "Objeto":   items[0].titulo_atual or "",
            })
        df = pd.DataFrame(rows)

        edited = st.data_editor(
            df,
            column_config={
                "Código":   st.column_config.TextColumn("Código",   disabled=True),
                "Tipo":     st.column_config.TextColumn("Tipo",     disabled=True, width="small"),
                "Trecho":   st.column_config.TextColumn("Trecho",   disabled=True),
                "Arquivos": st.column_config.TextColumn("Arquivos", disabled=True),
                "Objeto":   st.column_config.TextColumn(
                    "Objeto",
                    help="Confirme ou preencha o nome do projeto para este documento.",
                    width="large",
                ),
            },
            use_container_width=True,
            hide_index=True,
            key="editor_preview",
        )

        # Validação: todos os Objetos preenchidos?
        em_branco = edited[edited["Objeto"].str.strip() == ""]["Código"].tolist()
        if em_branco:
            st.warning(
                f"Preencha o **Objeto** dos seguintes documentos antes de confirmar: "
                + ", ".join(f"`{c}`" for c in em_branco[:10])
            )

        col_conf, col_cancel = st.columns([1, 5])
        confirmar = col_conf.button(
            "Confirmar e salvar",
            type="primary",
            key="btn_confirmar",
            disabled=bool(em_branco),
        )
        col_cancel.button(
            "Cancelar",
            key="btn_cancelar",
            on_click=lambda: (
                st.session_state.pop(PREVIEW_KEY, None),
                st.session_state.pop(NOME_KEY, None),
            ),
        )

        if confirmar:
            titulos = dict(zip(edited["Código"], edited["Objeto"]))
            with st.spinner("Salvando…"):
                resultado = ArquivosImporter().confirmar_preview(
                    preview, titulos, contrato_id, nome_txt
                )
            st.success(
                f"**{resultado.novos}** arquivo(s) registrado(s) com sucesso."
            )
            del st.session_state[PREVIEW_KEY]
            del st.session_state[NOME_KEY]
            st.rerun()

        # Detalhes extras
        if preview.sem_documento:
            with st.expander(f"Códigos não encontrados no banco ({len(preview.sem_documento)})"):
                for c in preview.sem_documento:
                    st.markdown(f"- `{c}`")

        return

    # ── Estado A: upload ─────────────────────────────────────────────────────
    st.markdown(
        "Importa um arquivo de texto com nomes de arquivos gerado pelo Windows. "
        "Arquivos em pastas **OBSOLETO** são ignorados automaticamente."
    )
    with st.expander("Como gerar o nomes.txt"):
        st.code(
            ":: Abra o Prompt de Comando na pasta sincronizada do SharePoint\n"
            ":: Apenas a pasta atual:\n"
            "dir /b /o:n >nomes.txt\n\n"
            ":: Recursivo (inclui subpastas — recomendado):\n"
            "dir /b /s /o:n >nomes.txt",
            language="bat",
        )

    arquivo = st.file_uploader(
        "Arquivo de nomes (.txt)", type=["txt"], key="upload_nomes"
    )
    if arquivo:
        st.caption(f"**{arquivo.name}** · {arquivo.size} bytes")
        if st.button("Analisar", type="primary", key="btn_analisar"):
            with st.spinner("Analisando…"):
                try:
                    conteudo = arquivo.read().decode("utf-8", errors="replace")
                    preview  = gerar_preview(conteudo, contrato_id)
                    st.session_state[PREVIEW_KEY] = preview
                    st.session_state[NOME_KEY]    = arquivo.name
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao analisar o arquivo: {e}")


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

tab_lista, tab_id, tab_arq, tab_hist = st.tabs([
    "📋 Lista de Documentos",
    "📑 Índice de Documentos (ID)",
    "📁 Arquivos (nomes.txt)",
    "🕘 Histórico",
])

with tab_lista:
    _tab_lista(contrato_id)

with tab_id:
    _tab_id(contrato_id)

with tab_arq:
    _tab_arquivos(contrato_id)

with tab_hist:
    _historico(contrato_id)
