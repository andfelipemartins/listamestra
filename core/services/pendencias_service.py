"""
core/services/pendencias_service.py

Orquestracao das pendencias calculadas e das dispensas persistidas.
"""

from dataclasses import asdict
from typing import Optional

from core.engine.pendencias import Pendencia, TipoPendencia, detectar_pendencias
from core.repositories.pendencia_repository import ACOES_DISPENSA, PendenciaRepository


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
        dispensas = {
            (row["tipo_pendencia"], row["chave"]): row
            for row in self._repository.listar_por_contrato(contrato_id)
        }
        tipo_filtro = _tipo_valor(tipo) if tipo is not None else None

        resultado = []
        for pendencia in detectadas:
            if tipo_filtro and pendencia.tipo.value != tipo_filtro:
                continue
            if trecho is not None and pendencia.trecho != trecho:
                continue
            if disciplina is not None and pendencia.disciplina != disciplina:
                continue

            dispensa = dispensas.get((pendencia.tipo.value, pendencia.chave))
            if dispensa and not incluir_dispensadas:
                continue

            item = self._serializar(pendencia)
            item.update({
                "dispensada": dispensa is not None,
                "dispensa_id": dispensa["id"] if dispensa else None,
                "acao_dispensa": dispensa["acao"] if dispensa else None,
                "observacao_dispensa": dispensa["observacao"] if dispensa else None,
                "perfil_dispensa": dispensa["perfil"] if dispensa else None,
                "dispensada_em": dispensa["criado_em"] if dispensa else None,
            })
            resultado.append(item)
        return resultado

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
    ) -> dict[str, int]:
        resumo = {tipo.value: 0 for tipo in TipoPendencia}
        for item in self.listar_pendencias(
            contrato_id,
            incluir_dispensadas=incluir_dispensadas,
            dias_analise=dias_analise,
            dias_estagnacao=dias_estagnacao,
        ):
            resumo[item["tipo"]] += 1
        return resumo

    @staticmethod
    def _serializar(pendencia: Pendencia) -> dict:
        item = asdict(pendencia)
        item["tipo"] = pendencia.tipo.value
        return item
