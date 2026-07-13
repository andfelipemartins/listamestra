# PURPOSE: Serve a confirmacao publica de recebimento de GRD via token unico.
# INPUTS: Token de rota e campos HTML de recebimento enviados pelo destinatario.
# OUTPUTS: Paginas HTML de formulario, sucesso ou erro sem regra de dominio propria.
# DEPS: FastAPI, Jinja2, core.services.grd_service.GrdService.
# SEE: docs/adr/0004-recebimento-grd-por-token.md, api/templates/recebimento_form.html

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates

from core.services.grd_service import GrdService


TEMPLATES_DIR = Path(__file__).parent / "templates"
ServiceFactory = Callable[[], GrdService]


def _data_recebimento_valida(valor: str) -> bool:
    """Valida somente o formato ISO do campo HTML; a regra pertence ao dominio."""
    if not valor:
        return True
    try:
        date.fromisoformat(valor)
    except ValueError:
        return False
    return True


def create_app(service_factory: ServiceFactory = GrdService) -> FastAPI:
    """Cria o adaptador HTTP sem manter estado de GRD fora do servico."""
    app = FastAPI(
        title="SCLME - Recebimento de GRD",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    def renderizar_erro(request: Request, mensagem: str, status_code: int = 400):
        return templates.TemplateResponse(
            request,
            "recebimento_erro.html",
            {"mensagem": mensagem},
            status_code=status_code,
        )

    def contexto_formulario(service: GrdService, token: str) -> dict | None:
        estado = service.estado_token(token)
        if not estado["valido"]:
            return None
        grd = estado["grd"]
        return {
            "grd": grd,
            "itens": service.listar_itens(grd["id"]),
        }

    @app.get("/", response_class=PlainTextResponse)
    def diagnostico() -> str:
        return "SCLME - servico de recebimento de GRD"

    @app.get("/grd/receber/{token}", response_class=HTMLResponse)
    def exibir_formulario(request: Request, token: str):
        service = service_factory()
        estado = service.estado_token(token)
        if not estado["valido"]:
            return renderizar_erro(request, estado["motivo"])

        contexto = contexto_formulario(service, token)
        if contexto is None:
            return renderizar_erro(request, "Este link nao esta mais disponivel.")
        return templates.TemplateResponse(
            request,
            "recebimento_form.html",
            {
                **contexto,
                "token": token,
                "erro": None,
                "valores": {
                    "recebido_por": "",
                    "recebido_cargo": "",
                    "recebido_em": date.today().isoformat(),
                    "declaracao": "",
                },
            },
        )

    @app.post("/grd/receber/{token}", response_class=HTMLResponse)
    def confirmar_recebimento(
        request: Request,
        token: str,
        recebido_por: str = Form(""),
        recebido_cargo: str = Form(""),
        recebido_em: str = Form(""),
        declaracao: str = Form(""),
    ):
        service = service_factory()
        estado_antes = service.estado_token(token)
        valores = {
            "recebido_por": recebido_por,
            "recebido_cargo": recebido_cargo,
            "recebido_em": recebido_em or date.today().isoformat(),
            "declaracao": declaracao,
        }

        if not _data_recebimento_valida(recebido_em):
            contexto = contexto_formulario(service, token)
            if contexto is None:
                estado = service.estado_token(token)
                return renderizar_erro(request, estado["motivo"])
            return templates.TemplateResponse(
                request,
                "recebimento_form.html",
                {**contexto, "token": token, "erro": "Informe uma data valida.", "valores": valores},
                status_code=400,
            )

        resultado = service.registrar_recebimento_por_token(
            token,
            recebido_por,
            recebido_cargo,
            declaracao,
            valores["recebido_em"],
        )
        if resultado.sucesso:
            return templates.TemplateResponse(
                request,
                "recebimento_sucesso.html",
                {
                    "numero_grd": (estado_antes.get("grd") or {}).get("numero_grd"),
                    "recebido_por": recebido_por.strip(),
                    "recebido_em": valores["recebido_em"],
                },
            )

        contexto = contexto_formulario(service, token)
        if contexto is None:
            return renderizar_erro(request, resultado.mensagem)
        return templates.TemplateResponse(
            request,
            "recebimento_form.html",
            {**contexto, "token": token, "erro": resultado.mensagem, "valores": valores},
            status_code=400,
        )

    return app


app = create_app()
