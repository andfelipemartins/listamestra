# PURPOSE: Centraliza configuracoes simples do SCLME.
# INPUTS: Variaveis de ambiente SCLME_GRD_TOKEN_TTL_DIAS, SCLME_PUBLIC_BASE_URL
# OUTPUTS: Constantes de configuracao consumidas por services e paginas
# DEPS: stdlib os
# SEE: core/services/grd_service.py, pages/6_GRD.py

import os


def _int_env(nome: str, padrao: int) -> int:
    try:
        valor = int(os.getenv(nome, str(padrao)))
    except (TypeError, ValueError):
        return padrao
    return valor if valor > 0 else padrao


GRD_TOKEN_TTL_DIAS = _int_env("SCLME_GRD_TOKEN_TTL_DIAS", 30)
PUBLIC_BASE_URL = (os.getenv("SCLME_PUBLIC_BASE_URL") or "http://localhost:8100").rstrip("/")
