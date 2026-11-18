from datetime import timedelta
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.perfil import ErroPerfil, perfil_de_dict
from core.perfil.codigo import montar
from contratos.models import Contrato, PerfilContrato
from documentos.models import Analise, CodigoDocumento, Documento, Emissao
from importacoes.models import ImportacaoID, ImportacaoSituacao, IndiceDocumentos, ItemPrevisto


class Command(BaseCommand):
    help = "Cria documentos sintéticos para visualizar o painel da chefia."

    def add_arguments(self, parser):
        parser.add_argument("contrato_id", type=int)

    def handle(self, *args, **options):
        contrato_id = options["contrato_id"]
        try:
            contrato = Contrato.objects.get(pk=contrato_id)
        except Contrato.DoesNotExist as erro:
            raise CommandError(f"Contrato com ID {contrato_id} não existe.") from erro
        if Documento.objects.filter(contrato=contrato).exists():
            raise CommandError("O comando não pode rodar em contrato que já tenha documentos.")

        perfil_modelo = PerfilContrato.perfil_vigente(contrato, timezone.localdate())
        if perfil_modelo is None:
            raise CommandError("O contrato precisa ter um perfil vigente para gerar o demo.")
        try:
            perfil = perfil_de_dict(perfil_modelo.definicao)
        except ErroPerfil as erro:
            raise CommandError(f"Perfil vigente inválido: {erro}") from erro

        codigos = _codigos_demo(perfil, 63)
        if len({codigo[1] for codigo in codigos}) != len(codigos):
            raise CommandError("Não foi possível gerar códigos únicos com as caixas deste perfil.")

        hoje = timezone.localdate()
        grupos = perfil.painel.grupos
        status = []
        for indice in range(60):
            grupo = grupos[indice % len(grupos)]
            situacao = grupo.estados[0] if grupo.estados else "Em Análise"
            status.append(None if grupo.sem_emissao else situacao)
        status[58] = "Estado sintético sem mapeamento"
        status[59] = "Outro estado sintético sem mapeamento"

        with transaction.atomic():
            indice = IndiceDocumentos.objects.create(
                contrato=contrato,
                codigo="DEMO-PAINEL",
                revisao="1",
                fonte=IndiceDocumentos.Fonte.EXCEL_ID,
                arquivo_nome="demo-sintetico.xlsx",
                importado_em=timezone.now(),
            )
            emissao_count = 0
            for posicao, (codigo, identificador, segmentos) in enumerate(codigos[:60]):
                documento = Documento.objects.create(
                    contrato=contrato,
                    identificador_base=identificador,
                    tipo=segmentos.get("tipo", ""),
                    titulo=f"Documento sintético {posicao + 1:02d}",
                    disciplina=segmentos.get("classe", segmentos.get("disciplina", "")),
                    trecho=segmentos.get("trecho", ""),
                    atributos=segmentos,
                )
                CodigoDocumento.objects.create(
                    documento=documento,
                    perfil=perfil_modelo,
                    codigo=codigo,
                )
                ItemPrevisto.objects.create(
                    indice=indice,
                    documento=documento,
                    titulo=documento.titulo,
                )
                if status[posicao] is None:
                    continue
                data_emissao = hoje - timedelta(days=90 - posicao)
                emissao = Emissao.objects.create(
                    documento=documento,
                    revisao="1",
                    versao=1,
                    fase=Emissao.Fase.PRELIMINAR,
                    data_emissao=data_emissao,
                    origem=Emissao.Origem.CLIENTE,
                )
                Analise.objects.create(
                    emissao=emissao,
                    etapa="Análise do cliente",
                    situacao=status[posicao],
                    origem=Analise.Origem.IMPORTADO_PW,
                    data_analise=data_emissao + timedelta(days=3),
                )
                emissao_count += 1

            for posicao, (codigo, identificador, segmentos) in enumerate(codigos[60:63], start=1):
                documento = Documento.objects.create(
                    contrato=contrato,
                    identificador_base=identificador,
                    tipo=segmentos.get("tipo", ""),
                    titulo=f"Documento sintético fora do ID {posicao}",
                    disciplina=segmentos.get("classe", segmentos.get("disciplina", "")),
                    trecho=segmentos.get("trecho", ""),
                    atributos=segmentos,
                    fora_do_id=True,
                )
                CodigoDocumento.objects.create(documento=documento, perfil=perfil_modelo, codigo=codigo)
                emissao = Emissao.objects.create(
                    documento=documento,
                    revisao="1",
                    versao=1,
                    fase=Emissao.Fase.PRELIMINAR,
                    data_emissao=hoje - timedelta(days=15 - posicao),
                    origem=Emissao.Origem.CLIENTE,
                )
                Analise.objects.create(
                    emissao=emissao,
                    etapa="Análise do cliente",
                    situacao="Em Análise",
                    origem=Analise.Origem.IMPORTADO_PW,
                    data_analise=emissao.data_emissao + timedelta(days=2),
                )

            ImportacaoID.objects.create(
                contrato=contrato,
                indice=indice,
                arquivo_nome="demo-sintetico.xlsx",
                linhas_validas=60,
            )
            ImportacaoSituacao.objects.create(
                contrato=contrato,
                data_extracao=hoje,
                arquivo_nome="demo-sintetico-pw.xlsx",
                documentos=63,
                emissoes=emissao_count + 3,
                analises_explicitas=emissao_count + 3,
            )

        self.stdout.write(self.style.SUCCESS("Dados sintéticos do painel criados: 60 previstos e 3 fora do ID."))


def _codigos_demo(perfil, quantidade):
    resultados = []
    for indice in range(quantidade):
        for tentativa in range(40):
            segmentos = {}
            for campo_indice, campo in enumerate(perfil.codigo.campos):
                valores = list((campo.valores or {}).keys())
                if campo.nome in {"sequencial", "numero", "número"} and re.fullmatch(r"\\d\{(\d+)\}", campo.padrao_regex):
                    largura = int(re.fullmatch(r"\\d\{(\d+)\}", campo.padrao_regex).group(1))
                    valor = str(1001 + indice).zfill(largura)
                elif valores:
                    valor = valores[(indice + tentativa * campo_indice) % len(valores)]
                else:
                    valor = _valor_sintetico(campo.padrao_regex)
                segmentos[campo.nome] = valor
            try:
                codigo = montar(perfil, segmentos)
            except ValueError:
                continue
            identificador = codigo
            if perfil.codigo.revisao_no_codigo and perfil.codigo.segmento_revisao:
                # O próprio parser exclui a caixa de revisão da identidade-base.
                from core.perfil.codigo import interpretar

                interpretado = interpretar(perfil, codigo)
                identificador = interpretado.identificador_base
            if all(identificador != existente[1] for existente in resultados):
                resultados.append((codigo, identificador, segmentos))
                break
        else:
            return []
    return resultados


def _valor_sintetico(padrao):
    for candidato in ("0", "1", "A", "00", "01", "AA", "001", "000", "0000", "A1", "CC"):
        if re.fullmatch(padrao, candidato, re.IGNORECASE):
            return candidato
    numero = re.fullmatch(r"\\d\{(\d+)\}", padrao)
    if numero:
        return "0" * int(numero.group(1))
    letras = re.fullmatch(r"\[A-Z\]\{(\d+)\}", padrao)
    if letras:
        return "A" * int(letras.group(1))
    raise CommandError(f"Não há valor sintético simples para o padrão {padrao!r}.")
