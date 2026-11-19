"""Motor declarativo de perfis de contrato, sem dependências de aplicação."""

from .modelo import (
    ErroPerfil,
    EstruturaCodigo,
    Grupo,
    IndicadorAprovacao,
    PainelPerfil,
    PerfilContrato,
    Restricao,
    Segmento,
    Separador,
    carregar_perfil,
    carregar_yaml,
    perfil_de_dict,
)
from .indicadores import (
    DocumentoIndicador,
    EmissaoIndicador,
    ResultadoContagemIndicador,
    ResultadoIndicadorAprovacao,
    calcular_indicador_aprovacao,
)

__all__ = [
    "ErroPerfil",
    "EstruturaCodigo",
    "Grupo",
    "IndicadorAprovacao",
    "PainelPerfil",
    "PerfilContrato",
    "Restricao",
    "Segmento",
    "Separador",
    "DocumentoIndicador",
    "EmissaoIndicador",
    "ResultadoContagemIndicador",
    "ResultadoIndicadorAprovacao",
    "carregar_perfil",
    "carregar_yaml",
    "calcular_indicador_aprovacao",
    "perfil_de_dict",
]
