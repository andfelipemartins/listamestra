"""Motor declarativo de perfis de contrato, sem dependências de aplicação."""

from .modelo import (
    ErroPerfil,
    EstruturaCodigo,
    PerfilContrato,
    Restricao,
    Segmento,
    Separador,
    carregar_perfil,
    carregar_yaml,
    perfil_de_dict,
)

__all__ = [
    "ErroPerfil",
    "EstruturaCodigo",
    "PerfilContrato",
    "Restricao",
    "Segmento",
    "Separador",
    "carregar_perfil",
    "carregar_yaml",
    "perfil_de_dict",
]
