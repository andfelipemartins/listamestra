from datetime import date, timedelta

from django.core.exceptions import PermissionDenied
from django.db.models import Count, F, Prefetch
from django.utils import timezone

from core.perfil import ErroPerfil, perfil_de_dict
from core.perfil.painel import classificar
from contratos.models import Contrato, PerfilContrato
from documentos.models import Analise, Documento, Emissao
from importacoes.cronograma import comparar_previsoes_cronograma
from importacoes.models import (
    ImportacaoID,
    ImportacaoSituacao,
    InconsistenciaImportacao,
    PrevisaoEmissao,
)
from painel.prazos import dias_ate_vencimento, emissoes_abertas_prazo, feriados_prazo

from .models import AcaoPendencia


PRAZO_ANALISE = "analise-cliente"
PRAZO_DEVOLUCAO = "devolucao"
TIPOS_JANELA = {
    "erros": "Erros a corrigir",
    PRAZO_ANALISE: "Análise do cliente",
    PRAZO_DEVOLUCAO: "Nossa devolução",
    "cronograma": "Cronograma",
    "recusadas": "Linhas recusadas abertas",
}
_DIAS_PARA_VENCER = 3
_DIAS_CRONOGRAMA = 7


def contratos_acessiveis(usuario):
    contratos = Contrato.objects.all()
    if not usuario.is_staff:
        contratos = contratos.filter(
            ativo=True,
            participacoes__usuario=usuario,
            participacoes__ativo=True,
        )
    return contratos.distinct().order_by("nome", "pk")


def resolver_contrato(usuario, contrato_id=None):
    contratos = contratos_acessiveis(usuario)
    if contrato_id in (None, ""):
        return contratos.first()
    try:
        contrato = contratos.filter(pk=int(contrato_id)).first()
    except (TypeError, ValueError):
        contrato = None
    if contrato is None:
        raise PermissionDenied("Você não participa deste contrato.")
    return contrato


def carregar_minha_mesa(usuario, contrato_id=None, *, hoje=None, limite=10, incluir_ignorados=False):
    contratos = list(contratos_acessiveis(usuario))
    contrato = resolver_contrato(usuario, contrato_id)
    if contrato is None:
        return {"contratos": contratos, "contrato": None, "janelas": [], "perfil_erro": ""}

    hoje = hoje or timezone.localdate()
    perfil_modelo = PerfilContrato.perfil_vigente(contrato, hoje)
    perfil = None
    perfil_erro = ""
    if perfil_modelo is not None:
        try:
            perfil = perfil_de_dict(perfil_modelo.definicao)
        except ErroPerfil as erro:
            perfil_erro = f"O perfil vigente não pode alimentar as janelas: {erro}"
    else:
        perfil_erro = "Este contrato ainda não tem um perfil vigente."

    docs = _documentos_com_historico(contrato)
    erros = _erros_abertos(contrato, perfil, docs, incluir_ignorados=incluir_ignorados) if perfil else []
    prazos_analise, prazos_devolucao = _janelas_prazo(perfil, docs, hoje) if perfil else ([], [])
    cronograma = _itens_cronograma(contrato, hoje)
    recusadas = _linhas_recusadas(contrato)

    janelas = []
    if perfil:
        janelas.append(_janela("erros", "Erros a corrigir", erros, limite))
        if perfil.prazos is not None:
            regras_analise = [regra for regra in perfil.prazos.regras if regra.inicio == "emissao" and regra.fim == "analise"]
            regras_devolucao = [regra for regra in perfil.prazos.regras if regra.inicio == "analise" and regra.fim == "proxima_emissao"]
            if regras_analise:
                janelas.append(_janela(PRAZO_ANALISE, _rotulo_regras_regras(regras_analise), prazos_analise, limite))
            if regras_devolucao:
                janelas.append(_janela(PRAZO_DEVOLUCAO, _rotulo_regras_regras(regras_devolucao), prazos_devolucao, limite))
    janelas.extend(
        (
            _janela("cronograma", TIPOS_JANELA["cronograma"], cronograma, limite),
            _janela("recusadas", TIPOS_JANELA["recusadas"], recusadas, limite),
        )
    )
    return {
        "contratos": contratos,
        "contrato": contrato,
        "perfil_erro": perfil_erro,
        "janelas": janelas,
        "perfil": perfil,
    }


def carregar_janela(usuario, contrato_id, tipo, *, hoje=None):
    if tipo not in TIPOS_JANELA:
        raise ValueError("Janela desconhecida.")
    mesa = carregar_minha_mesa(usuario, contrato_id, hoje=hoje, limite=None)
    janela = next((item for item in mesa["janelas"] if item["id"] == tipo), None)
    if janela is None:
        janela = {"id": tipo, "titulo": TIPOS_JANELA[tipo], "quantidade": 0, "itens": []}
    return {**mesa, "janela": janela}


def carregar_ignorados(usuario, contrato_id, *, hoje=None):
    mesa = carregar_minha_mesa(usuario, contrato_id, hoje=hoje, limite=None, incluir_ignorados=True)
    janela_erros = next((item for item in mesa["janelas"] if item["id"] == "erros"), None)
    itens = [
        item for item in (janela_erros["todos"] if janela_erros else [])
        if item["ultima_acao"]
        and item["ultima_acao"].acao == AcaoPendencia.Acao.IGNORAR
        and item["ultima_acao"].resolvida_em is None
    ]
    return {
        **mesa,
        "janela": {"id": "ignorados", "titulo": "Pendências ignoradas", "quantidade": len(itens), "itens": itens, "todos": itens},
    }


def registrar_acao(usuario, contrato_id, documento_id, tipo_pendencia, acao, motivo=""):
    contrato = resolver_contrato(usuario, contrato_id)
    if contrato is None:
        raise PermissionDenied("Você não participa deste contrato.")
    if acao not in AcaoPendencia.Acao.values:
        raise ValueError("Ação desconhecida.")
    motivo = (motivo or "").strip()
    if acao == AcaoPendencia.Acao.IGNORAR and not motivo:
        raise ValueError("Informe o motivo para ignorar a pendência.")

    dados = carregar_minha_mesa(usuario, contrato.pk, limite=None)
    erros = next((item for item in dados["janelas"] if item["id"] == "erros"), None)
    pendencia = next(
        (
            item for item in (erros["todos"] if erros else [])
            if item["documento"].pk == int(documento_id)
            and item["tipo_pendencia"] == tipo_pendencia
        ),
        None,
    )
    if pendencia is None:
        raise ValueError("A pendência já não está aberta para ação.")

    texto_email = ""
    if acao == AcaoPendencia.Acao.PEDIR_CORRECAO:
        texto_email = _texto_email_correcao(pendencia)
    registro = AcaoPendencia(
        contrato=contrato,
        documento=pendencia["documento"],
        tipo_pendencia=tipo_pendencia,
        acao=acao,
        motivo=motivo,
        texto_email=texto_email,
        situacao_referencia=pendencia["situacao"],
        revisao_referencia=pendencia["revisao"],
        data_referencia=pendencia["data_situacao"],
        usuario=usuario,
    )
    registro.full_clean(exclude=("criado_em", "resolvida_em"))
    registro.save()
    return registro


def reativar_ignorado(usuario, contrato_id, documento_id, tipo_pendencia):
    contrato = resolver_contrato(usuario, contrato_id)
    if contrato is None:
        raise PermissionDenied("Você não participa deste contrato.")
    dados = carregar_ignorados(usuario, contrato.pk)
    ignorado = next(
        (
            item for item in dados["janela"]["todos"]
            if item["documento"].pk == int(documento_id)
            and item["tipo_pendencia"] == tipo_pendencia
        ),
        None,
    )
    if ignorado is None:
        raise ValueError("A pendência ignorada já não está disponível para reativação.")
    acao = ignorado["ultima_acao"]
    acao.resolvida_em = timezone.now()
    acao._history_user = usuario
    acao.save(update_fields=("resolvida_em",))
    return acao


def _documentos_com_historico(contrato):
    analises = Analise.objects.order_by(
        F("data_analise").desc(nulls_last=True), "-registrado_em", "-pk"
    )
    emissoes = Emissao.objects.order_by("data_emissao", "pk").prefetch_related(
        Prefetch("analises", queryset=analises)
    )
    return list(
        Documento.objects.filter(contrato=contrato, emissoes__isnull=False)
        .distinct()
        .prefetch_related(Prefetch("emissoes", queryset=emissoes))
        .order_by("identificador_base", "pk")
    )


def _erros_abertos(contrato, perfil, documentos, *, incluir_ignorados=False):
    grupos_ocultos = {
        grupo.id: grupo for grupo in perfil.painel.grupos if grupo.oculto_no_painel
    }
    if not grupos_ocultos:
        return []
    acoes = list(
        AcaoPendencia.objects.filter(contrato=contrato)
        .select_related("usuario")
        .order_by("-criado_em", "-pk")
    )
    ultimas_acoes = {}
    for acao in acoes:
        ultimas_acoes.setdefault((acao.documento_id, acao.tipo_pendencia), acao)

    itens = []
    for documento in documentos:
        emissao, analise = _situacao_e_analise_atual(documento)
        if emissao is None or analise is None:
            continue
        grupo = classificar(perfil, analise.situacao)
        if not grupo.oculto_no_painel or grupo.id not in grupos_ocultos:
            continue
        ultima_acao = ultimas_acoes.get((documento.pk, grupo.id))
        if (
            ultima_acao
            and ultima_acao.acao == AcaoPendencia.Acao.IGNORAR
            and ultima_acao.resolvida_em is None
            and not incluir_ignorados
        ):
            continue
        if (
            ultima_acao
            and ultima_acao.acao == AcaoPendencia.Acao.JA_CORRIGI
            and ultima_acao.situacao_referencia != analise.situacao
        ):
            ultima_acao = None
        data_situacao = analise.data_analise
        if data_situacao is None and analise.registrado_em:
            data_situacao = timezone.localtime(analise.registrado_em).date()
        if data_situacao is None:
            data_situacao = emissao.data_emissao
        itens.append(
            {
                "documento": documento,
                "codigo": documento.identificador_base,
                "titulo": documento.titulo or "(sem título)",
                "situacao": analise.situacao,
                "grupo": grupo.rotulo,
                "tipo_pendencia": grupo.id,
                "data_situacao": data_situacao,
                "data_desde": analise.data_analise or data_situacao,
                "emissao": emissao,
                "revisao": emissao.revisao,
                "versao": emissao.versao,
                "quem_lancou": _nome_usuario(analise.registrado_por),
                "ultima_acao": ultima_acao,
                "ultima_acao_por": _nome_usuario(ultima_acao.usuario) if ultima_acao else "",
            }
        )
    return sorted(itens, key=lambda item: (item["data_desde"], item["codigo"].casefold()))


def _situacao_e_analise_atual(documento):
    emissao = max(
        documento.emissoes.all(),
        key=lambda item: (item.data_emissao, item.pk),
        default=None,
    )
    if emissao is None:
        return None, None
    analise = next(iter(emissao.analises.all()), None)
    return emissao, analise


def _janelas_prazo(perfil, documentos, hoje):
    if perfil.prazos is None:
        return [], []
    regras_analise = [
        regra for regra in perfil.prazos.regras
        if regra.inicio == "emissao" and regra.fim == "analise"
    ]
    regras_devolucao = [
        regra for regra in perfil.prazos.regras
        if regra.inicio == "analise" and regra.fim == "proxima_emissao"
    ]
    return (
        _itens_regras_prazo(perfil, regras_analise, documentos, hoje),
        _itens_regras_prazo(perfil, regras_devolucao, documentos, hoje),
    )


def _itens_regras_prazo(perfil, regras, documentos, hoje):
    itens = []
    feriados = feriados_prazo(perfil.prazos, documentos, hoje)
    for regra in regras:
        for documento in documentos:
            for item_prazo in emissoes_abertas_prazo(perfil, regra, documento, hoje, feriados):
                avaliacao = item_prazo.avaliacao
                if avaliacao.situacao == "aberto_atrasado":
                    dias = avaliacao.dias_atraso
                    texto_prazo = f"Atrasado há {dias} {('dia' if dias == 1 else 'dias')}"
                    atrasado = True
                else:
                    dias = dias_ate_vencimento(regra, hoje, avaliacao.vencimento, feriados)
                    if dias > _DIAS_PARA_VENCER:
                        continue
                    texto_prazo = "Vence hoje" if dias == 0 else f"Vence em {dias} {('dia' if dias == 1 else 'dias')}"
                    atrasado = False
                itens.append(
                    {
                        "documento": documento,
                        "codigo": documento.identificador_base,
                        "titulo": documento.titulo or "(sem título)",
                        "regra": regra,
                        "regra_rotulo": regra.rotulo,
                        "emissao": item_prazo.emissao,
                        "revisao": item_prazo.emissao.revisao,
                        "versao": item_prazo.emissao.versao,
                        "situacao": item_prazo.analise.situacao if item_prazo.analise else "Em análise",
                        "data_inicio": item_prazo.inicio,
                        "vencimento": avaliacao.vencimento,
                        "atrasado": atrasado,
                        "dias": dias,
                        "texto_prazo": texto_prazo,
                    }
                )
    return sorted(
        itens,
        key=lambda item: (
            0 if item["atrasado"] else 1,
            -item["dias"] if item["atrasado"] else item["dias"],
            item["codigo"].casefold(),
            item["revisao"],
        ),
    )


def _itens_cronograma(contrato, hoje):
    itens = []
    limite = hoje + timedelta(days=_DIAS_CRONOGRAMA)
    for resultado in comparar_previsoes_cronograma(contrato, hoje=hoje):
        previsao = resultado.previsao
        vencido = resultado.status == "vencido_sem_emissao"
        futuro = resultado.status == "futuro" and previsao.data_prevista <= limite
        if not (vencido or futuro):
            continue
        dias = (hoje - previsao.data_prevista).days if vencido else (previsao.data_prevista - hoje).days
        texto_prazo = (
            f"Atrasado há {dias} {('dia' if dias == 1 else 'dias')}"
            if vencido
            else "Previsto para hoje" if dias == 0
            else f"Previsto em {dias} {('dia' if dias == 1 else 'dias')}"
        )
        itens.append(
            {
                "documento": previsao.documento,
                "codigo": previsao.documento.identificador_base,
                "titulo": previsao.documento.titulo or "(sem título)",
                "data_prevista": previsao.data_prevista,
                "vencido": vencido,
                "dias": dias,
                "texto_prazo": texto_prazo,
            }
        )
    return sorted(
        itens,
        key=lambda item: (0 if item["vencido"] else 1, -item["dias"] if item["vencido"] else item["dias"], item["codigo"].casefold()),
    )


def _linhas_recusadas(contrato):
    por_id = dict(
        InconsistenciaImportacao.objects.filter(
            importacao_id__contrato=contrato,
            resolvida_em__isnull=True,
        ).values("importacao_id").annotate(total=Count("pk")).values_list("importacao_id", "total")
    )
    por_situacao = dict(
        InconsistenciaImportacao.objects.filter(
            importacao_situacao__contrato=contrato,
            resolvida_em__isnull=True,
        ).values("importacao_situacao").annotate(total=Count("pk")).values_list("importacao_situacao", "total")
    )
    itens = []
    for importacao in ImportacaoID.objects.filter(pk__in=por_id).select_related("indice", "importado_por"):
        itens.append(
            {
                "importacao_id": importacao.pk,
                "arquivo": importacao.arquivo_nome,
                "tipo": "ID",
                "data_importacao": timezone.localtime(importacao.importado_em).date(),
                "quantidade": por_id[importacao.pk],
                "link_recusadas": True,
            }
        )
    for importacao in ImportacaoSituacao.objects.filter(pk__in=por_situacao).select_related("importado_por"):
        itens.append(
            {
                "importacao_id": importacao.pk,
                "arquivo": importacao.arquivo_nome,
                "tipo": "Situação PW",
                "data_importacao": timezone.localtime(importacao.importado_em).date(),
                "quantidade": por_situacao[importacao.pk],
                "link_recusadas": True,
            }
        )
    return sorted(itens, key=lambda item: (item["data_importacao"], item["tipo"], item["arquivo"].casefold()))


def _janela(identificador, rotulo, itens, limite):
    todos = list(itens)
    return {
        "id": identificador,
        "titulo": rotulo,
        "quantidade": len(todos),
        "itens": todos if limite is None else todos[:limite],
        "todos": todos,
    }


def _rotulo_regras_regras(regras):
    rotulos = []
    for regra in regras:
        if regra.rotulo not in rotulos:
            rotulos.append(regra.rotulo)
    return " / ".join(rotulos)


def _texto_email_correcao(pendencia):
    data = pendencia["data_situacao"].strftime("%d/%m/%Y") if pendencia["data_situacao"] else "sem data informada"
    revisao = f"{pendencia['revisao']}" + (
        f" versão {pendencia['versao']}" if pendencia["versao"] is not None else ""
    )
    return (
        "Prezados,\n\n"
        f"Solicitamos, por gentileza, a correção do registro do documento {pendencia['codigo']}, "
        f"revisão {revisao}, atualmente com a situação “{pendencia['situacao']}” desde {data}.\n\n"
        "Agradecemos a verificação e a atualização da situação no sistema.\n\n"
        "Atenciosamente,"
    )


def _nome_usuario(usuario):
    return usuario.get_full_name() or usuario.get_username() if usuario else "Sistema"
