"""
pages/4_CadastroManual.py

Cadastro manual de documentos e revisões — entrada linha a linha como em uma planilha.
Permite registrar novos documentos e adicionar revisões a documentos já existentes.
"""

import os
import sys
from datetime import date
from typing import Optional

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.parsers.registry import ParserRegistry
from core.parsers.codigo_builder import (
    LINHA15_TIPOS,
    LINHA15_TRECHOS,
    LINHA15_CLASSES,
    montar_codigo_linha15,
    desmontar_codigo_linha15,
)
from core.engine.disciplinas import (
    ESTRUTURA_OPCOES,
    MODALIDADES,
    SITUACOES,
    codigo_para_opcao,
    opcao_para_codigo,
)
from core.engine.emissao_inicial import recalcular_emissao_inicial
from app.session import require_contrato, sidebar_contexto
from core.auth.permissions import require_permission, widget_seletor_perfil
from db.connection import get_connection

st.set_page_config(
    page_title="Cadastro Manual — SCLME",
    page_icon="📝",
    layout="wide",
)

widget_seletor_perfil()
sidebar_contexto()

st.title("📝 Cadastro Manual")
st.caption(
    "Registre documentos e revisões individualmente — "
    "complementa as importações em lote via Excel."
)

contrato = require_contrato()
require_permission("create_document")

_registry = ParserRegistry()

st.caption(f"Contrato: **{contrato['nome']}**")
st.divider()

# ---------------------------------------------------------------------------
# Dados
# ---------------------------------------------------------------------------

def _buscar_documento(contrato_id: int, codigo: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM documentos WHERE contrato_id = ? AND codigo = ?",
            (contrato_id, codigo),
        ).fetchone()
    return dict(row) if row else None


def _listar_revisoes(documento_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT label_revisao, versao, emissao_inicial, data_emissao, situacao
            FROM revisoes
            WHERE documento_id = ?
            ORDER BY
                CASE WHEN data_emissao IS NULL THEN 1 ELSE 0 END,
                data_emissao ASC,
                revisao ASC,
                versao ASC
            """,
            (documento_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _salvar(
    contrato_id: int,
    codigo: str,
    doc_fields: dict,
    rev_fields: dict,
    grds: list[dict],
) -> str:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM documentos WHERE contrato_id = ? AND codigo = ?",
            (contrato_id, codigo),
        ).fetchone()

        if row:
            doc_id = row["id"]
            conn.execute(
                """
                UPDATE documentos SET
                    titulo      = COALESCE(?, titulo),
                    disciplina  = COALESCE(?, disciplina),
                    modalidade  = COALESCE(?, modalidade),
                    responsavel = COALESCE(?, responsavel),
                    fase        = COALESCE(?, fase),
                    atualizado_em = datetime('now')
                WHERE id = ?
                """,
                (
                    doc_fields["titulo"] or None,
                    doc_fields["disciplina"] or None,
                    doc_fields["modalidade"] or None,
                    doc_fields["responsavel"] or None,
                    doc_fields["fase"] or None,
                    doc_id,
                ),
            )
            doc_novo = False
        else:
            parsed = _registry.parse(codigo)
            cur = conn.execute(
                """
                INSERT INTO documentos
                    (contrato_id, codigo, tipo, titulo, disciplina, modalidade,
                     responsavel, fase, trecho, nome_trecho, origem)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'cadastro_manual')
                """,
                (
                    contrato_id,
                    codigo,
                    parsed.tipo if parsed.valido else None,
                    doc_fields["titulo"] or None,
                    doc_fields["disciplina"] or None,
                    doc_fields["modalidade"] or None,
                    doc_fields["responsavel"] or None,
                    doc_fields["fase"] or None,
                    parsed.extras.get("trecho") if parsed.valido else None,
                    parsed.extras.get("nome_trecho") if parsed.valido else None,
                ),
            )
            doc_id = cur.lastrowid
            doc_novo = True

        rev_existe = conn.execute(
            "SELECT id FROM revisoes WHERE documento_id = ? AND label_revisao = ? AND versao = ?",
            (doc_id, rev_fields["label_revisao"], rev_fields["versao"]),
        ).fetchone()
        if rev_existe:
            return f"Revisão {rev_fields['label_revisao']} Versão {rev_fields['versao']} já existe para este documento."

        try:
            revisao_int = int(rev_fields["label_revisao"])
        except (ValueError, TypeError):
            revisao_int = None

        cur = conn.execute(
            """
            INSERT INTO revisoes
                (documento_id, revisao, versao, label_revisao,
                 data_elaboracao, data_emissao, data_analise,
                 situacao_real, situacao,
                 emissao_circular, analise_circular, data_circular,
                 ultima_revisao, origem)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'cadastro_manual')
            """,
            (
                doc_id,
                revisao_int,
                rev_fields["versao"],
                rev_fields["label_revisao"],
                rev_fields["data_elaboracao"],
                rev_fields["data_emissao"],
                rev_fields["data_analise"],
                rev_fields["situacao_real"] or None,
                rev_fields["situacao"] or None,
                rev_fields["num_circular"] or None,
                rev_fields["analise_interna"] or None,
                rev_fields["data_circular"],
            ),
        )
        rev_id = cur.lastrowid

        conn.execute(
            "UPDATE revisoes SET ultima_revisao = 0 WHERE documento_id = ?",
            (doc_id,),
        )
        ultima = conn.execute(
            """
            SELECT id FROM revisoes
            WHERE documento_id = ?
            ORDER BY
                CASE WHEN data_emissao IS NULL THEN 1 ELSE 0 END,
                data_emissao DESC, revisao DESC, versao DESC
            LIMIT 1
            """,
            (doc_id,),
        ).fetchone()
        if ultima:
            conn.execute(
                "UPDATE revisoes SET ultima_revisao = 1 WHERE id = ?",
                (ultima["id"],),
            )

        recalcular_emissao_inicial(conn, doc_id)

        for grd in grds:
            if grd.get("numero_grd") or grd.get("data_envio"):
                conn.execute(
                    """
                    INSERT OR REPLACE INTO grds (revisao_id, setor, numero_grd, data_envio)
                    VALUES (?, ?, ?, ?)
                    """,
                    (rev_id, grd["setor"], grd.get("numero_grd") or None, grd.get("data_envio")),
                )

    prefixo = "Documento criado e r" if doc_novo else "R"
    return f"{prefixo}evisão {rev_fields['label_revisao']} (Versão {rev_fields['versao']}) registrada com sucesso."


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def _campo_data(label: str, key: str, valor: Optional[str] = None) -> Optional[str]:
    default = None
    if valor:
        try:
            from datetime import datetime
            default = datetime.strptime(valor[:10], "%Y-%m-%d").date()
        except ValueError:
            default = None
    result = st.date_input(label, value=default, key=key, format="DD/MM/YYYY")
    if result and result != date(1900, 1, 1):
        return result.isoformat()
    return None


# ---------------------------------------------------------------------------
# Builder de código segmentado
# ---------------------------------------------------------------------------

def _secao_codigo() -> str:
    """
    Exibe o builder segmentado ou o campo livre (toggle), retorna o código montado.
    """
    colar = st.toggle("Colar código completo", key="toggle_colar", value=False)

    if colar:
        codigo = st.text_input(
            "Código do Documento",
            placeholder="Ex: DE-15.25.00.00-6A1-1001",
            key="inp_codigo_livre",
        ).strip().upper()
        return codigo

    # ── Builder segmentado ──────────────────────────────────────────────
    tipos_opts    = list(LINHA15_TIPOS.keys())
    trechos_opts  = list(LINHA15_TRECHOS.keys())
    classes_opts  = list(LINHA15_CLASSES.keys())

    st.markdown("**Código do Documento**")
    c1, c2, c3, c4, c5, c6, c7, c8 = st.columns([2, 2, 2, 2, 1, 1, 1, 2])

    with c1:
        tipo = st.selectbox(
            "Tipo",
            tipos_opts,
            format_func=lambda k: f"{k} — {LINHA15_TIPOS[k]}",
            key="bld_tipo",
        )
    with c2:
        trecho = st.selectbox(
            "Trecho",
            trechos_opts,
            format_func=lambda k: f"{k} — {LINHA15_TRECHOS[k]}",
            key="bld_trecho",
        )
    with c3:
        subtrecho = st.text_input("Subtrecho", value="00", max_chars=2, key="bld_subtrecho")
    with c4:
        unidade = st.text_input("Unidade", value="00", max_chars=2, key="bld_unidade")
    with c5:
        etapa = st.text_input("Etapa", value="6", max_chars=1, key="bld_etapa")
    with c6:
        classe = st.selectbox(
            "Classe",
            classes_opts,
            format_func=lambda k: f"{k} — {LINHA15_CLASSES[k]}",
            key="bld_classe",
        )
    with c7:
        subclasse = st.text_input("Subcls", value="1", max_chars=2, key="bld_subclasse")
    with c8:
        sequencial = st.text_input("Sequencial", value="0001", max_chars=4, key="bld_sequencial")

    codigo = montar_codigo_linha15(
        tipo,
        trecho.zfill(2) if trecho.isdigit() else "00",
        subtrecho.zfill(2) if subtrecho.isdigit() else "00",
        unidade.zfill(2) if unidade.isdigit() else "00",
        etapa if etapa.isdigit() else "6",
        classe,
        subclasse if subclasse.isdigit() else "1",
        sequencial.zfill(4) if sequencial.isdigit() else "0001",
    )

    st.code(codigo, language=None)
    return codigo


# ---------------------------------------------------------------------------
# Seções do formulário
# ---------------------------------------------------------------------------

def _secao_documento(existing: Optional[dict]) -> dict:
    st.markdown("**Dados do Documento**")

    c1, c2 = st.columns(2)
    with c1:
        titulo = st.text_input(
            "Descrição / Objeto *",
            value=existing.get("titulo") or "" if existing else "",
            key="inp_titulo",
        )
    with c2:
        responsavel = st.text_input(
            "Elaboração (responsável)",
            value=existing.get("responsavel") or "" if existing else "",
            key="inp_responsavel",
        )

    c3, c4, c5 = st.columns(3)
    with c3:
        modalidade_val = existing.get("modalidade") or "" if existing else ""
        modalidade_idx = MODALIDADES.index(modalidade_val) if modalidade_val in MODALIDADES else None
        modalidade = st.selectbox("Modalidade", options=MODALIDADES, index=modalidade_idx, key="sel_modalidade")
    with c4:
        disciplina_val = existing.get("disciplina") or "" if existing else ""
        opcao_atual = codigo_para_opcao(disciplina_val)
        estrutura_idx = (
            ESTRUTURA_OPCOES.index(opcao_atual)
            if opcao_atual and opcao_atual in ESTRUTURA_OPCOES
            else None
        )
        estrutura_opcao = st.selectbox(
            "Estrutura (disciplina)", options=ESTRUTURA_OPCOES, index=estrutura_idx, key="sel_estrutura"
        )
    with c5:
        fase = st.text_input(
            "Fase", value=existing.get("fase") or "" if existing else "",
            key="inp_fase", placeholder="Ex: EXECUTIVO",
        )

    return {
        "titulo":      titulo,
        "responsavel": responsavel,
        "modalidade":  modalidade,
        "disciplina":  opcao_para_codigo(estrutura_opcao),
        "fase":        fase,
    }


def _secao_revisao() -> dict:
    st.markdown("**Dados da Revisão**")

    c1, c2 = st.columns(2)
    with c1:
        label_revisao = st.text_input(
            "Revisão *", key="inp_revisao", placeholder="Ex: 0, 1, A, A1",
        )
    with c2:
        versao = st.number_input("Versão *", min_value=1, value=1, step=1, key="inp_versao")

    c3, c4, c5 = st.columns(3)
    with c3:
        data_elaboracao = _campo_data("Data Elaboração", "date_elaboracao")
    with c4:
        data_emissao = _campo_data("Data Emissão", "date_emissao")
    with c5:
        data_analise = _campo_data("Data Análise", "date_analise")

    c6, c7 = st.columns(2)
    with c6:
        situacao = st.selectbox("Situação", options=[""] + SITUACOES, index=0, key="sel_situacao")
    with c7:
        situacao_real = st.text_input("Situação Real", key="inp_situacao_real", placeholder="Ex: NÃO APROVADO")

    c8, c9, c10 = st.columns(3)
    with c8:
        analise_interna = st.text_input("Análise Interna", key="inp_analise_interna", placeholder="Ex: AI-001")
    with c9:
        data_circular = _campo_data("Data Circular", "date_circular")
    with c10:
        num_circular = st.text_input("Nº Circular", key="inp_num_circular", placeholder="Ex: 558/2024")

    return {
        "label_revisao":  label_revisao.strip(),
        "versao":         int(versao),
        "data_elaboracao": data_elaboracao,
        "data_emissao":   data_emissao,
        "data_analise":   data_analise,
        "situacao":       situacao or None,
        "situacao_real":  situacao_real.strip() or None,
        "analise_interna": analise_interna.strip() or None,
        "data_circular":  data_circular,
        "num_circular":   num_circular.strip() or None,
    }


def _secao_grds() -> list[dict]:
    st.markdown("**GRD — Distribuição**")
    setores = [("producao", "Produção"), ("topografia", "Topografia"), ("qualidade", "Qualidade")]
    grds = []
    cols = st.columns(len(setores))
    for col, (setor, nome) in zip(cols, setores):
        with col:
            st.markdown(f"*{nome}*")
            num  = st.text_input(f"Nº GRD", key=f"grd_num_{setor}", placeholder="Ex: GRD-001")
            data = _campo_data("Data Envio", f"grd_data_{setor}")
            grds.append({"setor": setor, "numero_grd": num.strip() or None, "data_envio": data})
    return grds


# ---------------------------------------------------------------------------
# Página
# ---------------------------------------------------------------------------

codigo_input = _secao_codigo()

if not codigo_input:
    st.info("Preencha o código do documento para continuar.")
    st.stop()

parsed = _registry.parse(codigo_input)
existing_doc = _buscar_documento(contrato["id"], codigo_input)

if not parsed.valido:
    st.error(f"Código inválido: {parsed.mensagem}")
    st.stop()

if existing_doc:
    revisoes = _listar_revisoes(existing_doc["id"])
    st.success(f"Documento encontrado — {len(revisoes)} revisão(ões) registrada(s).")
    if revisoes:
        with st.expander("Ver histórico de revisões"):
            for rev in revisoes:
                ei  = rev.get("emissao_inicial") or "—"
                dt  = rev.get("data_emissao") or "—"
                sit = rev.get("situacao") or "—"
                st.markdown(
                    f"- **{ei}** | Rev {rev['label_revisao']} Ver {rev['versao']} "
                    f"| Emissão: {dt} | Situação: {sit}"
                )
else:
    nome_trecho = parsed.extras.get("nome_trecho", "—")
    trecho      = parsed.extras.get("trecho", "—")
    sequencial  = parsed.extras.get("sequencial", "—")
    st.info(
        f"Documento novo — Tipo: **{parsed.tipo}** | "
        f"Trecho: **{nome_trecho}** ({trecho}) | "
        f"Sequencial: **{sequencial}**"
    )

st.divider()

with st.form("form_cadastro"):
    doc_fields = _secao_documento(existing_doc)

    st.divider()
    rev_fields = _secao_revisao()

    st.divider()
    with st.expander("GRD — opcional"):
        grds = _secao_grds()

    st.markdown("")
    submitted = st.form_submit_button("Salvar Revisão", type="primary", use_container_width=True)

if submitted:
    erros = []
    if not doc_fields["titulo"].strip():
        erros.append("Descrição / Objeto é obrigatório.")
    if not rev_fields["label_revisao"]:
        erros.append("Revisão é obrigatória.")

    if erros:
        for e in erros:
            st.error(e)
    else:
        msg = _salvar(contrato["id"], codigo_input, doc_fields, rev_fields, grds)
        if "sucesso" in msg.lower():
            st.success(msg)
            st.rerun()
        else:
            st.warning(msg)
