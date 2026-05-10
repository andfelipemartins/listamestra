"""
core/importers/cadastro_importer.py

Lógica de negócio do Cadastro Manual — separada da UI para permitir testes.
"""

from core.parsers.registry import ParserRegistry
from core.engine.emissao_inicial import recalcular_emissao_inicial
from db.connection import get_connection

_registry = ParserRegistry()


def salvar_documento_revisao(
    contrato_id: int,
    codigo: str,
    doc_fields: dict,
    rev_fields: dict,
    grds: list[dict],
    db_path: str = None,
) -> str:
    """
    Salva (upsert) o documento e insere a revisão com os GRDs.
    Não duplica revisão já existente (label + versão).
    Retorna mensagem de resultado.
    """
    with get_connection(db_path) as conn:
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
                    doc_fields.get("titulo") or None,
                    doc_fields.get("disciplina") or None,
                    doc_fields.get("modalidade") or None,
                    doc_fields.get("responsavel") or None,
                    doc_fields.get("fase") or None,
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
                    doc_fields.get("titulo") or None,
                    doc_fields.get("disciplina") or None,
                    doc_fields.get("modalidade") or None,
                    doc_fields.get("responsavel") or None,
                    doc_fields.get("fase") or None,
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
            return (
                f"Revisão {rev_fields['label_revisao']} "
                f"Versão {rev_fields['versao']} já existe para este documento."
            )

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
                rev_fields.get("data_elaboracao"),
                rev_fields.get("data_emissao"),
                rev_fields.get("data_analise"),
                rev_fields.get("situacao_real") or None,
                rev_fields.get("situacao") or None,
                rev_fields.get("num_circular") or None,
                rev_fields.get("analise_interna") or None,
                rev_fields.get("data_circular"),
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
    return (
        f"{prefixo}evisão {rev_fields['label_revisao']} "
        f"(Versão {rev_fields['versao']}) registrada com sucesso."
    )
