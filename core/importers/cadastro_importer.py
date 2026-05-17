"""
core/importers/cadastro_importer.py

Lógica de negócio do Cadastro Manual — separada da UI para permitir testes.
"""

from core.parsers.registry import ParserRegistry
from core.engine.emissao_inicial import recalcular_emissao_inicial
from core.repositories.documento_repository import DocumentoRepository
from core.repositories.revisao_repository import RevisaoRepository
from db.connection import get_connection

_registry = ParserRegistry()
_documento_repository = DocumentoRepository()
_revisao_repository = RevisaoRepository()


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

    disciplina e fase são sempre derivadas do código (fonte da verdade),
    nunca dos campos vindos da UI.
    """
    parsed = _registry.parse(codigo)
    disciplina_auto = (
        (parsed.extras.get("classe", "") + parsed.extras.get("subclasse", "")) or None
        if parsed.valido else None
    )
    fase_auto = parsed.extras.get("etapa") if parsed.valido else None

    with get_connection(db_path) as conn:
        doc_id = _documento_repository.buscar_id_por_codigo(
            contrato_id, codigo, conn=conn
        )

        if doc_id is not None:
            _documento_repository.atualizar_documento(
                doc_id,
                {
                    "titulo": doc_fields.get("titulo") or None,
                    "disciplina": disciplina_auto,
                    "modalidade": doc_fields.get("modalidade") or None,
                    "responsavel": doc_fields.get("responsavel") or None,
                    "fase": fase_auto,
                },
                conn=conn,
                coalesce=True,
            )
            doc_novo = False
        else:
            doc_id = _documento_repository.criar_documento(
                {
                    "contrato_id": contrato_id,
                    "codigo": codigo,
                    "tipo": parsed.tipo if parsed.valido else None,
                    "titulo": doc_fields.get("titulo") or None,
                    "disciplina": disciplina_auto,
                    "modalidade": doc_fields.get("modalidade") or None,
                    "responsavel": doc_fields.get("responsavel") or None,
                    "fase": fase_auto,
                    "trecho": parsed.extras.get("trecho") if parsed.valido else None,
                    "nome_trecho": parsed.extras.get("nome_trecho") if parsed.valido else None,
                    "origem": "cadastro_manual",
                },
                conn=conn,
            )
            doc_novo = True

        if _revisao_repository.existe_revisao(
            doc_id,
            rev_fields["label_revisao"],
            rev_fields["versao"],
            conn=conn,
        ):
            return (
                f"Revisão {rev_fields['label_revisao']} "
                f"Versão {rev_fields['versao']} já existe para este documento."
            )

        try:
            revisao_int = int(rev_fields["label_revisao"])
        except (ValueError, TypeError):
            revisao_int = None

        rev_id = _revisao_repository.criar_revisao(
            {
                "documento_id": doc_id,
                "revisao": revisao_int,
                "versao": rev_fields["versao"],
                "label_revisao": rev_fields["label_revisao"],
                "data_elaboracao": rev_fields.get("data_elaboracao"),
                "data_emissao": rev_fields.get("data_emissao"),
                "data_analise": rev_fields.get("data_analise"),
                "situacao_real": rev_fields.get("situacao_real") or None,
                "situacao": rev_fields.get("situacao") or None,
                "emissao_circular": rev_fields.get("num_circular") or None,
                "analise_circular": rev_fields.get("analise_interna") or None,
                "data_circular": rev_fields.get("data_circular"),
                "ultima_revisao": 0,
                "origem": "cadastro_manual",
            },
            conn=conn,
        )

        _revisao_repository.desmarcar_ultimas_por_documento(doc_id, conn=conn)
        ultima = _revisao_repository.buscar_ultima_revisao(doc_id, conn=conn)
        if ultima:
            _revisao_repository.marcar_como_ultima(ultima["id"], conn=conn)

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
