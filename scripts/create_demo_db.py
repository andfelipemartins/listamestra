"""
scripts/create_demo_db.py

Gera um banco de DEMONSTRAÇÃO fictício e seguro para versionar.

PURPOSE: criar data/demo/sclme_demo.db do zero, com dados 100% fictícios, para
         abrir o app no Streamlit Cloud sem expor dados reais.
INPUTS:  nenhum (caminho opcional).
OUTPUTS: arquivo SQLite em data/demo/sclme_demo.db.
DEPS:    scripts/init_db.py, core/repositories, core/services/grd_service.
SEE:     db/connection.py (SCLME_DB_MODE=demo), README.md

NUNCA lê o banco operacional. NUNCA usa nomes reais de pessoas/empresas/projetistas.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from init_db import init_db
from db.connection import DB_PATH_DEMO, get_connection
from core.repositories.contract_repository import ContractRepository
from core.repositories.documento_repository import DocumentoRepository
from core.repositories.revisao_repository import RevisaoRepository
from core.services.grd_service import GrdService
from core.engine.emissao_inicial import recalcular_emissao_inicial

# Trechos fictícios (mesmos nomes-rótulo da Linha 15, sem dados reais)
_TRECHOS = {"19": "Oratório", "23": "São Mateus", "25": "Ragueb Chohfi"}

# (codigo, tipo, disciplina, trecho, titulo, [revisões])
# Cada revisão: (label, versao, data_emissao, data_analise, situacao)
# data_emissao None → Em Elaboração; sem situação + emissao → Em Análise;
# "NÃO APROVADO"/"NÃO CONFORME" → Em Revisão; "APROVADO" → Aprovado.
_DOCS = [
    ("DE-15.19.00.00-6A1-1001", "DE", "A1", "19", "PROJETO DEMO DE GEOMETRIA",
     [("1", 1, None, None, None)]),                                   # Em Elaboração
    ("DE-15.19.00.00-6B3-1002", "DE", "B3", "19", "PROJETO DEMO DE TERRAPLENAGEM",
     [("1", 1, "2025-02-10", None, None)]),                           # Em Análise
    ("MD-15.19.00.00-6J2-1003", "MD", "J2", "19", "MEMORIAL DEMO DE DRENAGEM",
     [("1", 1, "2025-01-15", "2025-02-01", "NÃO APROVADO")]),         # Em Revisão
    ("RT-15.19.00.00-6N3-1004", "RT", "N3", "19", "RELATÓRIO DEMO DE INTERFERÊNCIAS",
     [("0", 1, "2025-03-01", "2025-03-20", "APROVADO")]),            # rev 0 aprovada
    ("DE-15.23.00.00-6A1-2001", "DE", "A1", "23", "PROJETO DEMO DE VIA PERMANENTE",
     [("1", 1, "2025-01-10", "2025-01-25", "NÃO APROVADO"),
      ("2", 1, "2025-03-05", "2025-03-22", "NÃO APROVADO"),
      ("0", 1, "2025-05-02", "2025-05-18", "APROVADO")]),             # histórico → Aprovado
    ("DE-15.23.00.00-6B3-2002", "DE", "B3", "23", "PROJETO DEMO DE CONTENÇÕES",
     [("1", 1, "2025-02-12", None, None)]),                           # Em Análise
    ("MC-15.23.00.00-6F2-2003", "MC", "F2", "23", "MEMORIAL DEMO DE CÁLCULO ESTRUTURAL",
     [("A", 1, "2025-02-20", "2025-03-10", "APROVADO"),
      ("A1", 1, "2025-04-15", "2025-05-01", "APROVADO")]),            # A / A1 pós-aprovação
    ("RT-15.23.00.00-6J2-2004", "RT", "J2", "23", "RELATÓRIO DEMO DE SONDAGEM",
     [("1", 1, "2025-01-30", "2025-02-14", "NÃO CONFORME")]),         # Em Revisão
    ("DE-15.25.00.00-6A1-3001", "DE", "A1", "25", "PROJETO DEMO DE ARQUITETURA",
     [("0", 1, "2025-02-28", "2025-03-15", "APROVADO")]),            # Aprovado
    ("DE-15.25.00.00-6B3-3002", "DE", "B3", "25", "PROJETO DEMO DE FUNDAÇÕES",
     [("1", 1, None, None, None)]),                                   # Em Elaboração
    ("MD-15.25.00.00-6J2-3003", "MD", "J2", "25", "MEMORIAL DEMO DE PAVIMENTAÇÃO",
     [("1", 1, "2025-03-12", None, None)]),                           # Em Análise
    ("RT-15.25.00.00-6N3-3004", "RT", "N3", "25", "RELATÓRIO DEMO DE TOPOGRAFIA",
     [("1", 1, "2025-02-05", "2025-02-22", "NÃO APROVADO")]),         # Em Revisão
    ("DE-15.25.00.00-6F2-3005", "DE", "F2", "25", "PROJETO DEMO DE INSTALAÇÕES",
     [("0", 1, "2025-04-01", "2025-04-18", "APROVADO")]),            # Aprovado
    ("MC-15.25.00.00-6A1-3006", "MC", "A1", "25", "MEMORIAL DEMO DE QUANTIDADES",
     [("1", 1, "2025-03-20", "2025-04-05", "NÃO APROVADO"),
      ("2", 1, "2025-05-10", None, None)]),                           # última Em Análise
    ("DE-15.25.00.00-6B3-3007", "DE", "B3", "25", "PROJETO DEMO DE SINALIZAÇÃO",
     [("0", 1, "2025-04-22", "2025-05-09", "APROVADO")]),            # Aprovado
    # Extras: existem na lista mas NÃO no ID previsto (Comparação mostra "extras")
    ("DE-15.25.00.00-6J2-9001", "DE", "J2", "25", "PROJETO DEMO EXTRA NÃO PREVISTO",
     [("1", 1, "2025-05-01", None, None)]),
    ("RT-15.19.00.00-6F2-9002", "RT", "F2", "19", "RELATÓRIO DEMO EXTRA NÃO PREVISTO",
     [("1", 1, "2025-05-03", "2025-05-20", "APROVADO")]),
]

# Previstos extra (no ID, mas sem documento na lista → Comparação mostra "ausentes")
_PREVISTOS_AUSENTES = [
    ("DE-15.19.00.00-6N3-1101", "DE", "N3", "19", "PROJETO DEMO DE ILUMINAÇÃO"),
    ("MD-15.19.00.00-6F2-1102", "MD", "F2", "19", "MEMORIAL DEMO DE SANEAMENTO"),
    ("DE-15.23.00.00-6N3-2101", "DE", "N3", "23", "PROJETO DEMO DE PAISAGISMO"),
    ("RT-15.23.00.00-6A1-2102", "RT", "A1", "23", "RELATÓRIO DEMO DE GEOTECNIA"),
    ("DE-15.25.00.00-6J2-3101", "DE", "J2", "25", "PROJETO DEMO DE COMUNICAÇÃO VISUAL"),
    ("MC-15.25.00.00-6N3-3102", "MC", "N3", "25", "MEMORIAL DEMO DE ELÉTRICA"),
    ("DE-15.25.00.00-6F2-3103", "DE", "F2", "25", "PROJETO DEMO DE VENTILAÇÃO"),
]

# Códigos da lista que TAMBÉM são previstos (todos exceto os 90xx "extra")
_NAO_PREVISTOS = {"DE-15.25.00.00-6J2-9001", "RT-15.19.00.00-6F2-9002"}


def _label_para_revisao_int(label: str):
    try:
        return int(label)
    except (ValueError, TypeError):
        return None


def criar_banco_demo(db_path: str = DB_PATH_DEMO) -> str:
    """Cria (ou recria) o banco demo do zero. Retorna o caminho."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if os.path.exists(db_path):
        # Libera handles sqlite ainda abertos (Windows) antes de remover.
        import gc
        gc.collect()
        os.remove(db_path)

    init_db(db_path, verbose=False)

    contrato_id = ContractRepository(db_path).criar_contrato(
        "Demo Linha 15", "Cliente Demonstração"
    )

    doc_repo = DocumentoRepository(db_path)
    rev_repo = RevisaoRepository(db_path)

    # Documentos previstos (ID) — lista + ausentes
    previstos = [
        (c, t, disc, tr, tit) for (c, t, disc, tr, tit, _) in _DOCS
        if c not in _NAO_PREVISTOS
    ] + _PREVISTOS_AUSENTES
    with get_connection(db_path) as conn:
        for codigo, tipo, disc, trecho, titulo in previstos:
            conn.execute(
                """
                INSERT INTO documentos_previstos
                    (contrato_id, codigo, tipo, titulo, disciplina, trecho, ativo)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (contrato_id, codigo, tipo, titulo, disc, trecho),
            )

    # Documentos controlados (lista) + revisões
    doc_ids = []
    for codigo, tipo, disc, trecho, titulo, revisoes in _DOCS:
        doc_id = doc_repo.criar_documento({
            "contrato_id": contrato_id, "codigo": codigo, "tipo": tipo,
            "titulo": titulo, "disciplina": disc, "trecho": trecho,
            "nome_trecho": _TRECHOS.get(trecho, trecho), "modalidade": "CIVIL",
            "responsavel": "Equipe Demo", "fase": "EXECUTIVO", "origem": "demo",
        })
        doc_ids.append(doc_id)
        for label, versao, d_emis, d_anal, situacao in revisoes:
            rev_repo.criar_revisao({
                "documento_id": doc_id,
                "revisao": _label_para_revisao_int(label),
                "versao": versao, "label_revisao": label,
                "data_emissao": d_emis, "data_analise": d_anal,
                "situacao": situacao, "ultima_revisao": 0, "origem": "demo",
            })

    # Recalcula última revisão e rótulos de emissão (comportamento do importador)
    rev_repo.recalcular_ultimas_por_contrato(contrato_id)
    with get_connection(db_path) as conn:
        for doc_id in doc_ids:
            recalcular_emissao_inicial(conn, doc_id)

    _criar_grds_demo(db_path, contrato_id)
    return db_path


def _criar_grds_demo(db_path: str, contrato_id: int) -> None:
    """Cria 4 GRDs fictícias: emitida, enviada, recebida e anulada."""
    svc = GrdService(db_path=db_path)
    selec = svc.listar_documentos_selecionaveis(contrato_id)
    if not selec:
        return
    ids = [d["revisao_id"] for d in selec]

    def _itens(qtd):
        return [{"revisao_id": r, "qtd_a1": 2, "qtd_a4": 3, "qtd_digital": 1}
                for r in ids[:qtd]]

    base = {"obra": "Demo Linha 15", "ac": "Setor de Demonstração"}

    # 1) Emitida
    g1 = svc.criar_grd(contrato_id, {**base, "numero_grd": "GRD-DEMO-001",
                                     "destinatario": "Cliente Demonstração",
                                     "data_envio": "2025-05-05", "status": "rascunho"},
                       _itens(4)).grd_id
    svc.emitir_grd(g1)

    # 2) Enviada
    g2 = svc.criar_grd(contrato_id, {**base, "numero_grd": "GRD-DEMO-002",
                                     "destinatario": "Cliente Demonstração",
                                     "data_envio": "2025-05-12", "status": "rascunho"},
                       _itens(5)).grd_id
    svc.emitir_grd(g2); svc.marcar_enviada(g2)

    # 3) Recebida (com dados de recebimento fictícios)
    g3 = svc.criar_grd(contrato_id, {**base, "numero_grd": "GRD-DEMO-003",
                                     "destinatario": "Cliente Demonstração",
                                     "data_envio": "2025-05-18", "status": "rascunho"},
                       _itens(3)).grd_id
    svc.emitir_grd(g3); svc.marcar_enviada(g3)
    svc.marcar_recebida(
        g3, recebido_por="Recebedor Demonstração", recebido_cargo="Coordenador Demo",
        declaracao="Recebi os documentos relacionados nesta guia (demonstração).",
        recebido_em="2025-05-22",
    )

    # 4) Anulada (com motivo)
    g4 = svc.criar_grd(contrato_id, {**base, "numero_grd": "GRD-DEMO-004",
                                     "destinatario": "Cliente Demonstração",
                                     "data_envio": "2025-05-20", "status": "rascunho"},
                       _itens(2)).grd_id
    svc.emitir_grd(g4)
    svc.anular_grd(g4, motivo="Documento substituído por revisão posterior (demonstração).")


if __name__ == "__main__":
    caminho = criar_banco_demo()
    print(f"Banco demo criado em: {caminho}")
