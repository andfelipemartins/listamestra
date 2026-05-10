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
from core.engine.disciplinas import (
    ESTRUTURA,
    ESTRUTURA_OPCOES,
    MODALIDADES,
    SITUACOES,
    codigo_para_opcao,
    opcao_para_codigo,
)
from core.engine.emissao_inicial import recalcular_emissao_inicial
from core.engine.status import NOME_TRECHO
from db.connection import get_connection

_registry = ParserRegistry()


# ---------------------------------------------------------------------------
# Dados
# ---------------------------------------------------------------------------

def _listar_contratos() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, nome FROM contratos WHERE ativo = 1 ORDER BY nome"
        ).fetchall()
    return [dict(r) for r in rows]


def _buscar_documento(contrato_id: int, codigo: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM documentos WHERE contrato_id = ? AND codigo = ?",
            (contrato_id, codigo),
        ).fetchone()
    return dict(row) if row else None


def _buscar_revisao(documento_id: int, label_revisao: str, versao: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM revisoes WHERE documento_id = ? AND label_revisao = ? AND versao = ?",
            (documento_id, label_revisao, versao),
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
    """
    Salva ou atualiza o documento, insere a revisão e salva os GRDs.
    Retorna mensagem de resultado.
    """
    with get_connection() as conn:
        # Upsert documento
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

        # Verifica duplicidade de revisão
        rev_existe = conn.execute(
            "SELECT id FROM revisoes WHERE documento_id = ? AND label_revisao = ? AND versao = ?",
            (doc_id, rev_fields["label_revisao"], rev_fields["versao"]),
        ).fetchone()
        if rev_existe:
            return f"Revisão {rev_fields['label_revisao']} Versão {rev_fields['versao']} já existe para este documento."

        # Determina revisao (int) a partir do label
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

        # Recalcula ultima_revisao para o documento
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

        # Recalcula emissão inicial para o documento
        recalcular_emissao_inicial(conn, doc_id)

        # Salva GRDs
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
# UI
# ---------------------------------------------------------------------------

def _secao_contrato() -> Optional[int]:
    contratos = _listar_contratos()
    if not contratos:
        st.warning("Nenhum contrato cadastrado. Acesse a página **Importação** para criar um.")
        return None
    opcoes = {c["nome"]: c["id"] for c in contratos}
    nome_sel = st.selectbox("Contrato", list(opcoes.keys()))
    return opcoes[nome_sel]


def _campo_data(label: str, key: str, valor: Optional[str] = None) -> Optional[str]:
    """Retorna data como string ISO ou None."""
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


def _secao_documento(existing: Optional[dict]) -> dict:
    """Renderiza o grupo de campos do nível de documento. Retorna os valores."""
    st.markdown("**Dados do Documento**")

    c1, c2 = st.columns(2)
    with c1:
        titulo = st.text_input(
            "Descrição / Objeto *",
            value=existing.get("titulo") or "" if existing else "",
            key="inp_titulo",
            help="Nome do projeto ou objeto do documento.",
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
        modalidade = st.selectbox(
            "Modalidade",
            options=MODALIDADES,
            index=modalidade_idx,
            key="sel_modalidade",
        )
    with c4:
        disciplina_val = existing.get("disciplina") or "" if existing else ""
        opcao_atual = codigo_para_opcao(disciplina_val)
        estrutura_idx = (
            ESTRUTURA_OPCOES.index(opcao_atual)
            if opcao_atual and opcao_atual in ESTRUTURA_OPCOES
            else None
        )
        estrutura_opcao = st.selectbox(
            "Estrutura (disciplina)",
            options=ESTRUTURA_OPCOES,
            index=estrutura_idx,
            key="sel_estrutura",
        )
    with c5:
        fase = st.text_input(
            "Fase",
            value=existing.get("fase") or "" if existing else "",
            key="inp_fase",
            placeholder="Ex: EXECUTIVO",
        )

    return {
        "titulo": titulo,
        "responsavel": responsavel,
        "modalidade": modalidade,
        "disciplina": opcao_para_codigo(estrutura_opcao),
        "fase": fase,
    }


def _secao_revisao() -> dict:
    """Renderiza o grupo de campos do nível de revisão. Retorna os valores."""
    st.markdown("**Dados da Revisão**")

    c1, c2 = st.columns(2)
    with c1:
        label_revisao = st.text_input(
            "Revisão *",
            key="inp_revisao",
            placeholder="Ex: 0, 1, A, A1",
            help="Identificador da revisão conforme o nome do arquivo.",
        )
    with c2:
        versao = st.number_input(
            "Versão *",
            min_value=1,
            value=1,
            step=1,
            key="inp_versao",
        )

    c3, c4, c5 = st.columns(3)
    with c3:
        data_elaboracao = _campo_data("Data Elaboração", "date_elaboracao")
    with c4:
        data_emissao = _campo_data("Data Emissão", "date_emissao")
    with c5:
        data_analise = _campo_data("Data Análise", "date_analise")

    c6, c7 = st.columns(2)
    with c6:
        situacao = st.selectbox(
            "Situação",
            options=[""] + SITUACOES,
            index=0,
            key="sel_situacao",
        )
    with c7:
        situacao_real = st.text_input(
            "Situação Real",
            key="inp_situacao_real",
            placeholder="Ex: NÃO APROVADO",
        )

    c8, c9, c10 = st.columns(3)
    with c8:
        analise_interna = st.text_input(
            "Análise Interna",
            key="inp_analise_interna",
            placeholder="Ex: AI-001",
        )
    with c9:
        data_circular = _campo_data("Data Circular", "date_circular")
    with c10:
        num_circular = st.text_input(
            "Nº Circular",
            key="inp_num_circular",
            placeholder="Ex: 558/2024",
        )

    return {
        "label_revisao": label_revisao.strip(),
        "versao": int(versao),
        "data_elaboracao": data_elaboracao,
        "data_emissao": data_emissao,
        "data_analise": data_analise,
        "situacao": situacao or None,
        "situacao_real": situacao_real.strip() or None,
        "analise_interna": analise_interna.strip() or None,
        "data_circular": data_circular,
        "num_circular": num_circular.strip() or None,
    }


def _secao_grds() -> list[dict]:
    """Renderiza os campos de GRD para Produção, Topografia, Qualidade."""
    st.markdown("**GRD — Distribuição**")
    setores = [
        ("producao",   "Produção"),
        ("topografia", "Topografia"),
        ("qualidade",  "Qualidade"),
    ]
    grds = []
    cols = st.columns(len(setores))
    for col, (setor, nome) in zip(cols, setores):
        with col:
            st.markdown(f"*{nome}*")
            num = st.text_input(f"Nº GRD", key=f"grd_num_{setor}", placeholder="Ex: GRD-001")
            data = _campo_data("Data Envio", f"grd_data_{setor}")
            grds.append({"setor": setor, "numero_grd": num.strip() or None, "data_envio": data})
    return grds


# ---------------------------------------------------------------------------
# Página
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Cadastro Manual — SCLME",
    page_icon="📝",
    layout="wide",
)
st.title("📝 Cadastro Manual")
st.caption(
    "Registre documentos e revisões individualmente — "
    "complementa as importações em lote via Excel."
)

contrato_id = _secao_contrato()
if contrato_id is None:
    st.stop()

st.divider()

# ── Código ──────────────────────────────────────────────────────────────────
col_cod, col_btn = st.columns([3, 1])
with col_cod:
    codigo_input = st.text_input(
        "Código do Documento",
        placeholder="Ex: DE-15.25.00.00-6A1-1001",
        key="inp_codigo",
    ).strip().upper()
with col_btn:
    st.markdown("<br>", unsafe_allow_html=True)
    validar = st.button("Validar", type="primary", key="btn_validar")

if not codigo_input:
    st.info("Digite o código do documento para começar.")
    st.stop()

parsed = _registry.parse(codigo_input)
existing_doc = _buscar_documento(contrato_id, codigo_input)

if validar or existing_doc is not None or (not validar and codigo_input):
    # Validação do parser
    if not parsed.valido:
        st.error(f"Código inválido: {parsed.mensagem}")
        st.stop()

    # Status do documento
    if existing_doc:
        revisoes = _listar_revisoes(existing_doc["id"])
        st.success(
            f"Documento encontrado — {len(revisoes)} revisão(ões) registrada(s)."
        )
        if revisoes:
            with st.expander("Ver histórico de revisões"):
                for rev in revisoes:
                    ei = rev.get("emissao_inicial") or "—"
                    dt = rev.get("data_emissao") or "—"
                    sit = rev.get("situacao") or "—"
                    st.markdown(
                        f"- **{ei}** | Rev {rev['label_revisao']} Ver {rev['versao']} "
                        f"| Emissão: {dt} | Situação: {sit}"
                    )
    else:
        trecho = parsed.extras.get("trecho", "—") if parsed.valido else "—"
        nome_trecho = parsed.extras.get("nome_trecho", trecho) if parsed.valido else "—"
        sequencial = parsed.extras.get("sequencial", "—") if parsed.valido else "—"
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
        submitted = st.form_submit_button(
            "Salvar Revisão",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        # Validações frontend
        erros = []
        if not doc_fields["titulo"].strip():
            erros.append("Descrição / Objeto é obrigatório.")
        if not rev_fields["label_revisao"]:
            erros.append("Revisão é obrigatória.")

        if erros:
            for e in erros:
                st.error(e)
        else:
            msg = _salvar(contrato_id, codigo_input, doc_fields, rev_fields, grds)
            if "sucesso" in msg.lower():
                st.success(msg)
                # Força releitura da página para atualizar o histórico
                st.rerun()
            else:
                st.warning(msg)
