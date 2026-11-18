"""
core/services/pendencias_service.py

Orquestracao das pendencias calculadas e das dispensas persistidas.
"""

from dataclasses import asdict
from typing import Optional

from core.engine.pendencias import Pendencia, TipoPendencia, detectar_pendencias
from core.repositories.pendencia_repository import ACOES_DISPENSA, PendenciaRepository


_ROTULOS_CATEGORIA = {
    TipoPendencia.PREVISTO_SEM_INICIO.value: "Previsto sem movimentação",
    TipoPendencia.PREVISTO_ESTAGNADO.value: "Previsto sem aprovação",
    TipoPendencia.LISTA_SEM_ID.value: "Documento da Lista fora do ID",
    TipoPendencia.ARQUIVO_SEM_DOCUMENTO.value: "Arquivo sem documento vinculado",
    TipoPendencia.DOCUMENTO_SEM_ARQUIVO.value: "Documento sem arquivo",
    TipoPendencia.CODIGO_INVALIDO.value: "Código inválido",
    TipoPendencia.REVISAO_SEM_DATA.value: "Revisão sem data de emissão",
    TipoPendencia.DOCUMENTO_SEM_TITULO.value: "Documento sem objeto ou título",
    TipoPendencia.DIVERGENCIA_TITULO.value: "Divergência entre títulos do ID e da Lista",
    TipoPendencia.EMITIDO_SEM_ANALISE.value: "Documento emitido sem análise",
    TipoPendencia.ANALISE_ATRASADA.value: "Análise atrasada",
}


def _tipo_valor(tipo) -> str:
    return str(getattr(tipo, "value", tipo))


class PendenciasService:
    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path
        self._repository = PendenciaRepository(db_path)

    def listar_pendencias(
        self,
        contrato_id: int,
        incluir_dispensadas: bool = False,
        tipo: TipoPendencia | str | None = None,
        trecho: Optional[str] = None,
        disciplina: Optional[str] = None,
        dias_analise: int = 30,
        dias_estagnacao: int = 60,
    ) -> list[dict]:
        detectadas = detectar_pendencias(
            contrato_id,
            db_path=self._db_path,
            dias_analise=dias_analise,
            dias_estagnacao=dias_estagnacao,
        )
        dispensas = self._dispensas_por_chave(contrato_id)
        itens = self._enriquecer(detectadas, dispensas)
        return self._filtrar(
            itens,
            incluir_dispensadas=incluir_dispensadas,
            tipo=tipo,
            trecho=trecho,
            disciplina=disciplina,
        )

    def dispensar_pendencia(
        self,
        contrato_id: int,
        tipo: TipoPendencia | str,
        chave: str,
        acao: str,
        observacao: Optional[str] = None,
        perfil: Optional[str] = None,
    ) -> int:
        tipo_valor = _tipo_valor(tipo)
        try:
            TipoPendencia(tipo_valor)
        except ValueError as exc:
            raise ValueError(f"Tipo de pendencia invalido: {tipo_valor}") from exc
        if acao not in ACOES_DISPENSA:
            raise ValueError("Acao deve ser 'resolvida' ou 'ignorada'.")
        if not str(chave).strip():
            raise ValueError("Chave da pendencia e obrigatoria.")
        return self._repository.dispensar(
            contrato_id,
            tipo_valor,
            str(chave),
            acao,
            observacao,
            perfil,
        )

    def reativar_pendencia(self, contrato_id: int, dispensa_id: int) -> bool:
        return self._repository.reativar(contrato_id, dispensa_id)

    def listar_dispensas(self, contrato_id: int) -> list[dict]:
        return self._repository.listar_por_contrato(contrato_id)

    def resumo_por_categoria(
        self,
        contrato_id: int,
        incluir_dispensadas: bool = False,
        dias_analise: int = 30,
        dias_estagnacao: int = 60,
        trecho: Optional[str] = None,
        disciplina: Optional[str] = None,
    ) -> dict[str, int]:
        resumo = {tipo.value: 0 for tipo in TipoPendencia}
        for item in self.listar_pendencias(
            contrato_id,
            incluir_dispensadas=incluir_dispensadas,
            trecho=trecho,
            disciplina=disciplina,
            dias_analise=dias_analise,
            dias_estagnacao=dias_estagnacao,
        ):
            resumo[item["tipo"]] += 1
        return resumo

    def painel(
        self,
        contrato_id: int,
        incluir_dispensadas: bool = False,
        tipo: TipoPendencia | str | None = None,
        trecho: Optional[str] = None,
        disciplina: Optional[str] = None,
        dias_analise: int = 30,
        dias_estagnacao: int = 60,
    ) -> dict:
        """Monta lista, resumo e opções de filtro a partir de uma única detecção."""
        detectadas = detectar_pendencias(
            contrato_id,
            db_path=self._db_path,
            dias_analise=dias_analise,
            dias_estagnacao=dias_estagnacao,
        )
        itens = self._enriquecer(detectadas, self._dispensas_por_chave(contrato_id))
        resumo = {tipo_item.value: 0 for tipo_item in TipoPendencia}
        for item in self._filtrar(
            itens,
            incluir_dispensadas=incluir_dispensadas,
            trecho=trecho,
            disciplina=disciplina,
        ):
            resumo[item["tipo"]] += 1

        return {
            "pendencias": self._filtrar(
                itens,
                incluir_dispensadas=incluir_dispensadas,
                tipo=tipo,
                trecho=trecho,
                disciplina=disciplina,
            ),
            "resumo": resumo,
            "opcoes_filtros": {
                "trechos": sorted({item["trecho"] for item in itens if item["trecho"]}),
                "disciplinas": sorted(
                    {item["disciplina"] for item in itens if item["disciplina"]}
                ),
            },
        }

    @staticmethod
    def rotulos_por_categoria() -> dict[str, str]:
        return dict(_ROTULOS_CATEGORIA)

    def opcoes_filtros(self, contrato_id: int) -> dict[str, list[str]]:
        pendencias = self.listar_pendencias(
            contrato_id,
            incluir_dispensadas=True,
        )
        return {
            "trechos": sorted({item["trecho"] for item in pendencias if item["trecho"]}),
            "disciplinas": sorted({item["disciplina"] for item in pendencias if item["disciplina"]}),
        }

    def _dispensas_por_chave(self, contrato_id: int) -> dict[tuple[str, str], dict]:
        return {
            (row["tipo_pendencia"], row["chave"]): row
            for row in self._repository.listar_por_contrato(contrato_id)
        }

    def _enriquecer(self, detectadas: list[Pendencia], dispensas: dict) -> list[dict]:
        itens = []
        for pendencia in detectadas:
            dispensa = dispensas.get((pendencia.tipo.value, pendencia.chave))
            item = self._serializar(pendencia)
            item.update({
                "dispensada": dispensa is not None,
                "dispensa_id": dispensa["id"] if dispensa else None,
                "acao_dispensa": dispensa["acao"] if dispensa else None,
                "observacao_dispensa": dispensa["observacao"] if dispensa else None,
                "perfil_dispensa": dispensa["perfil"] if dispensa else None,
                "dispensada_em": dispensa["criado_em"] if dispensa else None,
            })
            itens.append(item)
        return itens

    @staticmethod
    def _filtrar(
        itens: list[dict],
        incluir_dispensadas: bool = False,
        tipo: TipoPendencia | str | None = None,
        trecho: Optional[str] = None,
        disciplina: Optional[str] = None,
    ) -> list[dict]:
        tipo_filtro = _tipo_valor(tipo) if tipo is not None else None
        return [
            item
            for item in itens
            if (incluir_dispensadas or not item["dispensada"])
            and (tipo_filtro is None or item["tipo"] == tipo_filtro)
            and (trecho is None or item["trecho"] == trecho)
            and (disciplina is None or item["disciplina"] == disciplina)
        ]

    @staticmethod
    def _serializar(pendencia: Pendencia) -> dict:
        item = asdict(pendencia)
        item["tipo"] = pendencia.tipo.value
        return item
