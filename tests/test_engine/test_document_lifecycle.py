"""
tests/test_engine/test_document_lifecycle.py

Testes da engine central de ciclo documental (DocumentLifecycleEngine).

Cobre os 24 conceitos obrigatorios da spec, organizados em classes por topico.
Todos os testes sao de dominio puro — sem banco, sem Streamlit, sem mocks.

Casos A–K da spec cobertos explicitamente com marcacao.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from core.engine.document_lifecycle import (
    # Tipos
    LinhaDocumental,
    LifecycleIssue,
    LifecycleLine,
    LifecycleResult,
    # Enums
    TipoInferencia,
    SeveridadeIssue,
    TipoIssue,
    # Politicas
    RevisionPolicy,
    StatusPolicy,
    LinePolicy,
    # Constantes de status
    STATUS_APROVADO,
    STATUS_EM_REVISAO,
    STATUS_EM_ANALISE,
    STATUS_EM_ELABORACAO,
    STATUS_CANCELADO,
    # Constantes de resultado de linha
    RESULTADO_NAO_APROVADO,
    RESULTADO_NAO_CONFORME,
    RESULTADO_APROVADO,
    RESULTADO_CANCELADO,
    RESULTADO_EM_ANALISE,
    RESULTADO_EM_ELABORACAO,
    # API de conveniencia
    calcular_status_operacional,
    calcular_resultado_linha,
    calcular_ja_aprovado,
    calcular_ultima_revisao,
    calcular_emissao_inicial_labels,
    analisar_linhas_documento,
    analisar_importacao_documental,
)

# ---------------------------------------------------------------------------
# Helpers de construcao de LinhaDocumental
# ---------------------------------------------------------------------------

CODIGO = "DE-15.25.00.00-6J2-1005"


def linha(
    label: str,
    versao: int = 1,
    situacao: str = None,
    data_emissao: str = None,
    data_analise: str = None,
    data_elaboracao: str = None,
    ordem: int = 0,
    ja_persistida: bool = False,
) -> LinhaDocumental:
    """Cria LinhaDocumental com valores minimos para testes."""
    return LinhaDocumental(
        codigo=CODIGO,
        label_revisao=label,
        versao=versao,
        situacao=situacao,
        data_emissao=data_emissao,
        data_analise=data_analise,
        data_elaboracao=data_elaboracao,
        ordem=ordem,
        ja_persistida=ja_persistida,
    )


# ---------------------------------------------------------------------------
# A. Documento-base
# ---------------------------------------------------------------------------

class TestDocumentoBase:
    """Spec caso A: codigo e reconhecido como documento-base sem revisao/versao."""

    def test_codigo_valido_como_documento_base(self):
        """Engine aceita codigo da Linha 15 como documento-base."""
        l = linha("1", 1)
        assert l.codigo == CODIGO

    def test_engine_retorna_lifecycle_result_com_codigo(self):
        resultado = analisar_linhas_documento(CODIGO, [linha("1", 1, data_emissao="2024-01-01")])
        assert resultado.codigo == CODIGO

    def test_engine_sem_linhas_retorna_vazio(self):
        resultado = analisar_linhas_documento(CODIGO, [])
        assert resultado.total_linhas == 0
        assert resultado.status_atual == STATUS_EM_ELABORACAO
        assert resultado.ja_aprovado is False


# ---------------------------------------------------------------------------
# B. Chave logica
# ---------------------------------------------------------------------------

class TestChaveLogica:
    """Spec caso B: codigo + revisao + versao identificam linha unica."""

    def test_chave_logica_formato(self):
        l = linha("A", 2)
        assert l.chave_logica == f"{CODIGO}|A|2"

    def test_chaves_distintas_para_labels_diferentes(self):
        l1 = linha("1", 1)
        l2 = linha("2", 1)
        assert l1.chave_logica != l2.chave_logica

    def test_chaves_distintas_para_versoes_diferentes(self):
        l1 = linha("2", 1)
        l2 = linha("2", 2)
        assert l1.chave_logica != l2.chave_logica

    def test_chave_identica_para_mesmos_codigo_label_versao(self):
        l1 = linha("A1", 3)
        l2 = linha("A1", 3)
        assert l1.chave_logica == l2.chave_logica

    def test_duplicata_chave_no_lote_gera_issue_bloqueante(self):
        linhas = [
            linha("1", 1, data_emissao="2024-01-01"),
            linha("1", 1, data_emissao="2024-01-01"),  # duplicata
        ]
        resultado = analisar_linhas_documento(CODIGO, linhas)
        bloqueantes = resultado.issues_bloqueantes
        assert any(i.tipo == TipoIssue.CHAVE_DUPLICADA for i in bloqueantes)

    def test_sem_duplicata_nao_gera_issue_chave(self):
        linhas = [
            linha("1", 1, data_emissao="2024-01-01"),
            linha("2", 1, data_emissao="2024-02-01"),
        ]
        resultado = analisar_linhas_documento(CODIGO, linhas)
        assert not any(i.tipo == TipoIssue.CHAVE_DUPLICADA for i in resultado.todas_issues)


# ---------------------------------------------------------------------------
# C. Sequencia normal
# ---------------------------------------------------------------------------

class TestSequenciaNormal:
    """Spec caso C: 1/1 → 2/1 → 3/1 → 0/1 gera EMISSÃO INICIAL, REVISÃO 1, 2, REVISÃO FINAL."""

    def _sequencia(self) -> list[LinhaDocumental]:
        return [
            linha("1", 1, data_emissao="2024-01-01"),
            linha("2", 1, data_emissao="2024-02-01"),
            linha("3", 1, data_emissao="2024-03-01"),
            linha("0", 1, situacao="APROVADO", data_emissao="2024-04-01"),
        ]

    def test_rotulos_emissao_inicial(self):
        resultado = analisar_linhas_documento(CODIGO, self._sequencia())
        labels = [ll.emissao_inicial_label for ll in resultado.linhas]
        assert labels[0] == "EMISSÃO INICIAL"
        assert labels[1] == "REVISÃO 1"
        assert labels[2] == "REVISÃO 2"
        assert labels[3] == "REVISÃO FINAL"

    def test_ultima_revisao_e_a_revisao_0(self):
        resultado = analisar_linhas_documento(CODIGO, self._sequencia())
        assert resultado.ultima_revisao is not None
        assert resultado.ultima_revisao.linha.label_revisao == "0"

    def test_status_atual_aprovado_para_sequencia_finalizada(self):
        resultado = analisar_linhas_documento(CODIGO, self._sequencia())
        assert resultado.status_atual == STATUS_APROVADO

    def test_quatro_linhas_na_sequencia(self):
        resultado = analisar_linhas_documento(CODIGO, self._sequencia())
        assert resultado.total_linhas == 4

    def test_rotulos_sem_aprovacao_nao_gera_revisao_final(self):
        """Ultima linha sem situacao aprovada usa REVISÃO N."""
        linhas = [
            linha("1", 1, data_emissao="2024-01-01"),
            linha("2", 1, data_emissao="2024-02-01"),
        ]
        resultado = analisar_linhas_documento(CODIGO, linhas)
        labels = [ll.emissao_inicial_label for ll in resultado.linhas]
        assert labels[0] == "EMISSÃO INICIAL"
        assert labels[1] == "REVISÃO 1"

    def test_documento_unico_e_emissao_inicial(self):
        resultado = analisar_linhas_documento(CODIGO, [linha("1", 1, data_emissao="2024-01-01")])
        assert resultado.linhas[0].emissao_inicial_label == "EMISSÃO INICIAL"


# ---------------------------------------------------------------------------
# D. Pos-aprovacao — 7 linhas operacionais
# ---------------------------------------------------------------------------

class TestPosAprovacao:
    """Spec caso D: 1/1 → 2/1 → 3/1 → 0/1 → A1/1 → A/1 → A/2 = 7 linhas."""

    def _sequencia_completa(self) -> list[LinhaDocumental]:
        return [
            linha("1",  1, data_emissao="2024-01-01"),
            linha("2",  1, data_emissao="2024-02-01"),
            linha("3",  1, data_emissao="2024-03-01"),
            linha("0",  1, situacao="APROVADO", data_emissao="2024-04-01"),
            linha("A1", 1, data_emissao="2024-05-01"),
            linha("A",  1, situacao="APROVADO", data_emissao="2024-06-01"),
            linha("A",  2, situacao="APROVADO", data_emissao="2024-07-01"),
        ]

    def test_sete_linhas_sem_criar_extra(self):
        resultado = analisar_linhas_documento(CODIGO, self._sequencia_completa())
        assert resultado.total_linhas == 7

    def test_ja_aprovado_true_pela_revisao_0(self):
        resultado = analisar_linhas_documento(CODIGO, self._sequencia_completa())
        assert resultado.ja_aprovado is True

    def test_status_atual_da_ultima_linha(self):
        resultado = analisar_linhas_documento(CODIGO, self._sequencia_completa())
        assert resultado.status_atual == STATUS_APROVADO

    def test_revisao_0_marcada_como_aprovacao_historica(self):
        resultado = analisar_linhas_documento(CODIGO, self._sequencia_completa())
        linha_0 = next(ll for ll in resultado.linhas if ll.linha.label_revisao == "0")
        assert linha_0.inferencia == TipoInferencia.APROVACAO_HISTORICA

    def test_revisao_A1_nao_e_aprovacao_historica(self):
        assert RevisionPolicy.is_aprovacao_historica("A1") is False

    def test_revisao_A_e_aprovacao_historica(self):
        assert RevisionPolicy.is_aprovacao_historica("A") is True

    def test_revisao_0_e_aprovacao_historica(self):
        assert RevisionPolicy.is_aprovacao_historica("0") is True


# ---------------------------------------------------------------------------
# E. Nova revisao reprova anterior
# ---------------------------------------------------------------------------

class TestNovaRevisaoReprovaAnterior:
    """Spec caso E: revisao 3/1 apos 2/1 → 2/1 superada; bloqueante se sem data_analise."""

    def test_revisao_2_superada_sem_data_analise_gera_bloqueante(self):
        linhas = [
            linha("2", 1, data_emissao="2024-02-01"),   # sem data_analise
            linha("3", 1, data_emissao="2024-03-01"),
        ]
        resultado = analisar_linhas_documento(CODIGO, linhas)
        linha_2 = resultado.linhas[0]   # mais antiga na ordem

        assert linha_2.inferencia == TipoInferencia.SUPERADA_POR_REVISAO
        assert linha_2.tem_bloqueante
        assert resultado.tem_bloqueante
        assert any(
            i.tipo == TipoIssue.DATA_ANALISE_OBRIGATORIA
            for i in linha_2.issues
        )

    def test_revisao_2_superada_com_data_analise_nao_bloqueia(self):
        linhas = [
            linha("2", 1, data_emissao="2024-02-01", data_analise="2024-02-20"),
            linha("3", 1, data_emissao="2024-03-01"),
        ]
        resultado = analisar_linhas_documento(CODIGO, linhas)
        linha_2 = resultado.linhas[0]

        assert linha_2.inferencia == TipoInferencia.SUPERADA_POR_REVISAO
        assert not linha_2.tem_bloqueante
        assert not resultado.tem_bloqueante

    def test_inferencia_apenas_na_linha_anterior_nao_na_nova(self):
        linhas = [
            linha("2", 1, data_emissao="2024-02-01", data_analise="2024-02-20"),
            linha("3", 1, data_emissao="2024-03-01"),
        ]
        resultado = analisar_linhas_documento(CODIGO, linhas)
        linha_3 = resultado.linhas[1]   # mais nova

        assert linha_3.inferencia == TipoInferencia.NENHUMA

    def test_revisoes_nao_numericas_nao_geram_superacao_entre_si(self):
        """A1 apos A1 (mesmo label) nao gera SUPERADA."""
        linhas = [
            linha("A1", 1, data_emissao="2024-01-01"),
            linha("B1", 1, data_emissao="2024-02-01"),
        ]
        resultado = analisar_linhas_documento(CODIGO, linhas)
        # A1 → B1: labels distintos e nenhum e numerico puro → sem inferencia especial
        assert resultado.linhas[0].inferencia == TipoInferencia.NENHUMA


# ---------------------------------------------------------------------------
# F. Nova versao torna anterior nao conforme
# ---------------------------------------------------------------------------

class TestNovaVersaoSubstituiAnterior:
    """Spec caso F: 2/2 apos 2/1 → 2/1 substituida; bloqueante se sem data_analise."""

    def test_versao_1_substituida_sem_data_analise_bloqueia(self):
        linhas = [
            linha("2", 1, data_emissao="2024-02-01"),   # sem data_analise
            linha("2", 2, data_emissao="2024-02-15"),
        ]
        resultado = analisar_linhas_documento(CODIGO, linhas)
        linha_v1 = resultado.linhas[0]

        assert linha_v1.inferencia == TipoInferencia.SUBSTITUIDA_POR_VERSAO
        assert linha_v1.tem_bloqueante
        assert resultado.tem_bloqueante

    def test_versao_1_substituida_com_data_analise_nao_bloqueia(self):
        linhas = [
            linha("2", 1, data_emissao="2024-02-01", data_analise="2024-02-10"),
            linha("2", 2, data_emissao="2024-02-15"),
        ]
        resultado = analisar_linhas_documento(CODIGO, linhas)
        linha_v1 = resultado.linhas[0]

        assert linha_v1.inferencia == TipoInferencia.SUBSTITUIDA_POR_VERSAO
        assert not linha_v1.tem_bloqueante

    def test_versao_menor_nao_gera_substituicao(self):
        """2/1 ordenado apos 2/2 nao gera inferencia (versao menor e anterior)."""
        linhas = [
            linha("2", 2, data_emissao="2024-02-15"),
            linha("2", 1, data_emissao="2024-02-01"),   # mais antiga
        ]
        resultado = analisar_linhas_documento(CODIGO, linhas)
        # v1 e mais antiga (anterior), v2 e posterior — v1 recebe inferencia
        linha_v1 = next(ll for ll in resultado.linhas if ll.linha.versao == 1)
        assert linha_v1.inferencia == TipoInferencia.SUBSTITUIDA_POR_VERSAO


# ---------------------------------------------------------------------------
# G. Aprovacao historica
# ---------------------------------------------------------------------------

class TestAprovacaoHistorica:
    """Spec caso G: existindo 0/1 aprovado, ja_aprovado=True mesmo com A1/1 em analise."""

    def test_ja_aprovado_true_com_revisao_0(self):
        linhas = [
            linha("0", 1, situacao="APROVADO", data_emissao="2024-04-01"),
            linha("A1", 1, data_emissao="2024-05-01"),
        ]
        resultado = analisar_linhas_documento(CODIGO, linhas)
        assert resultado.ja_aprovado is True

    def test_status_atual_nao_e_aprovado_pois_ultima_e_em_analise(self):
        linhas = [
            linha("0", 1, situacao="APROVADO", data_emissao="2024-04-01"),
            linha("A1", 1, data_emissao="2024-05-01"),   # sem analise
        ]
        resultado = analisar_linhas_documento(CODIGO, linhas)
        assert resultado.status_atual == STATUS_EM_ANALISE

    def test_ja_aprovado_false_sem_revisao_historica(self):
        linhas = [
            linha("1", 1, data_emissao="2024-01-01"),
            linha("2", 1, data_emissao="2024-02-01", data_analise="2024-02-20"),
        ]
        resultado = analisar_linhas_documento(CODIGO, linhas)
        assert resultado.ja_aprovado is False

    def test_ja_aprovado_true_com_letra_pura(self):
        linhas = [
            linha("A", 1, situacao="APROVADO", data_emissao="2024-06-01"),
        ]
        resultado = analisar_linhas_documento(CODIGO, linhas)
        assert resultado.ja_aprovado is True

    def test_A1_nao_gera_aprovacao_historica(self):
        linhas = [
            linha("A1", 1, situacao="APROVADO", data_emissao="2024-05-01"),
        ]
        resultado = analisar_linhas_documento(CODIGO, linhas)
        assert resultado.ja_aprovado is False


# ---------------------------------------------------------------------------
# H. Situacao Real nao inferida
# ---------------------------------------------------------------------------

class TestSituacaoRealNaoInferida:
    """Spec caso H: engine nao deve inferir LIBERADO ou NÃO LIBERADO."""

    def test_situacao_real_nao_definida_pela_engine(self):
        """Engine nao preenche situacao_real nas linhas de saida."""
        l = linha("1", 1, data_emissao="2024-01-01")
        assert l.situacao_real is None
        resultado = analisar_linhas_documento(CODIGO, [l])
        # Engine nao altera o campo situacao_real
        assert resultado.linhas[0].linha.situacao_real is None

    def test_situacao_real_preservada_quando_fornecida(self):
        l = LinhaDocumental(
            codigo=CODIGO, label_revisao="1", versao=1,
            data_emissao="2024-01-01", situacao_real="LIBERADO"
        )
        resultado = analisar_linhas_documento(CODIGO, [l])
        assert resultado.linhas[0].linha.situacao_real == "LIBERADO"

    def test_status_operacional_nao_inclui_liberado(self):
        """Status operacional calculado nao retorna LIBERADO."""
        status = calcular_status_operacional(None, "2024-01-01")
        assert status not in ("LIBERADO", "NÃO LIBERADO")


# ---------------------------------------------------------------------------
# I. Cancelado nao remove da linha do tempo
# ---------------------------------------------------------------------------

class TestCancelado:
    """Spec caso I: CANCELADO nao apaga documento; permanece na linha do tempo."""

    def test_cancelado_tem_status_cancelado(self):
        l = linha("1", 1, situacao="CANCELADO", data_emissao="2024-01-01")
        status = calcular_status_operacional("CANCELADO", "2024-01-01")
        assert status == STATUS_CANCELADO

    def test_cancelado_aparece_nas_linhas_do_resultado(self):
        linhas = [
            linha("1", 1, data_emissao="2024-01-01"),
            linha("2", 1, situacao="CANCELADO", data_emissao="2024-02-01"),
        ]
        resultado = analisar_linhas_documento(CODIGO, linhas)
        assert resultado.total_linhas == 2
        canceladas = [ll for ll in resultado.linhas if ll.status_operacional == STATUS_CANCELADO]
        assert len(canceladas) == 1

    def test_cancelado_e_ultimo_quando_mais_recente(self):
        linhas = [
            linha("1", 1, data_emissao="2024-01-01"),
            linha("2", 1, situacao="CANCELADO", data_emissao="2024-02-01"),
        ]
        resultado = analisar_linhas_documento(CODIGO, linhas)
        assert resultado.status_atual == STATUS_CANCELADO


# ---------------------------------------------------------------------------
# J. Importacao parcial — ausencia nao inativa linha existente
# ---------------------------------------------------------------------------

class TestImportacaoParcial:
    """Spec caso J: ausencia de linha no lote importado nao inativa/remove existente."""

    def test_linhas_existentes_nao_removidas_por_ausencia_no_lote(self):
        """Documento tem 3 linhas no banco; importacao traz apenas 1 nova. As 3 persistem."""
        existentes = [
            linha("1", 1, data_emissao="2024-01-01", ja_persistida=True),
            linha("2", 1, data_emissao="2024-02-01", data_analise="2024-02-20",
                  ja_persistida=True),
        ]
        # Lote de entrada traz apenas uma nova linha — nao cancela as existentes
        entradas = [
            linha("3", 1, data_emissao="2024-03-01"),
        ]
        resultado = analisar_importacao_documental(CODIGO, entradas, existentes)
        assert resultado.total_linhas == 3   # 2 existentes + 1 nova

    def test_lote_vazio_preserva_todas_as_existentes(self):
        existentes = [
            linha("1", 1, data_emissao="2024-01-01", ja_persistida=True),
            linha("2", 1, data_emissao="2024-02-01", ja_persistida=True),
        ]
        resultado = analisar_importacao_documental(CODIGO, [], existentes)
        assert resultado.total_linhas == 2

    def test_atualizacao_linha_existente_gera_aviso_nao_bloqueante(self):
        """Tentar importar chave ja existente gera AVISO, nao BLOQUEANTE."""
        existentes = [
            linha("1", 1, data_emissao="2024-01-01", data_analise="2024-01-20",
                  ja_persistida=True),
        ]
        entradas = [
            linha("1", 1, data_emissao="2024-01-01"),   # mesma chave
        ]
        resultado = analisar_importacao_documental(CODIGO, entradas, existentes)
        avisos = resultado.issues_avisos
        assert any(i.tipo == TipoIssue.ATUALIZACAO_LINHA_EXISTENTE for i in avisos)
        assert not resultado.tem_bloqueante


# ---------------------------------------------------------------------------
# K. Status operacional — mapeamento completo
# ---------------------------------------------------------------------------

class TestStatusOperacional:
    """Spec caso K: mapeamento completo de status operacional (Regras 11-15)."""

    # Aprovado (Regra 11)
    def test_aprovado_por_situacao_aprovado(self):
        assert calcular_status_operacional("APROVADO", "2024-01-01") == STATUS_APROVADO

    def test_aprovado_por_para_aprovacao(self):
        assert calcular_status_operacional("PARA APROVAÇÃO", "2024-01-01") == STATUS_APROVADO

    def test_aprovado_por_em_coleta_assinaturas(self):
        assert calcular_status_operacional("EM COLETA DE ASSINATURAS", "2024-01-01") == STATUS_APROVADO

    # Em Revisão (Regra 12)
    def test_em_revisao_por_nao_aprovado(self):
        assert calcular_status_operacional("NÃO APROVADO", "2024-01-01") == STATUS_EM_REVISAO

    def test_em_revisao_por_nao_conforme(self):
        assert calcular_status_operacional("NÃO CONFORME", "2024-01-01") == STATUS_EM_REVISAO

    def test_em_revisao_por_data_analise_preenchida(self):
        """Qualquer situacao nao conclusiva + data_analise = Em Revisao."""
        assert calcular_status_operacional("À EMITIR", "2024-01-01", "2024-01-15") == STATUS_EM_REVISAO
        assert calcular_status_operacional(None, "2024-01-01", "2024-01-15") == STATUS_EM_REVISAO

    # Em Análise (Regra 13)
    def test_em_analise_com_data_emissao_sem_analise(self):
        assert calcular_status_operacional(None, "2024-01-01") == STATUS_EM_ANALISE
        assert calcular_status_operacional(None, "2024-01-01", None) == STATUS_EM_ANALISE

    # Em Elaboração (Regra 14)
    def test_em_elaboracao_sem_data_emissao(self):
        assert calcular_status_operacional(None, None) == STATUS_EM_ELABORACAO
        assert calcular_status_operacional("À EMITIR", None) == STATUS_EM_ELABORACAO

    # Cancelado (Regra 15)
    def test_cancelado_preserva_linha(self):
        assert calcular_status_operacional("CANCELADO", "2024-01-01") == STATUS_CANCELADO
        assert calcular_status_operacional("CANCELADO", None) == STATUS_CANCELADO

    def test_cancelado_tem_precedencia_sobre_data_analise(self):
        assert calcular_status_operacional("CANCELADO", "2024-01-01", "2024-01-15") == STATUS_CANCELADO


# ---------------------------------------------------------------------------
# Testes de RevisionPolicy
# ---------------------------------------------------------------------------

class TestRevisionPolicy:

    def test_numerica_identifica_labels_numericos(self):
        assert RevisionPolicy.is_numerica("0") is True
        assert RevisionPolicy.is_numerica("1") is True
        assert RevisionPolicy.is_numerica("12") is True

    def test_numerica_rejeita_nao_numericos(self):
        assert RevisionPolicy.is_numerica("A") is False
        assert RevisionPolicy.is_numerica("A1") is False
        assert RevisionPolicy.is_numerica("") is False

    def test_valor_numerico_retorna_int(self):
        assert RevisionPolicy.valor_numerico("0") == 0
        assert RevisionPolicy.valor_numerico("3") == 3
        assert RevisionPolicy.valor_numerico("A") is None

    def test_letra_pura_identifica_letras_unicas(self):
        assert RevisionPolicy.is_letra_pura("A") is True
        assert RevisionPolicy.is_letra_pura("Z") is True
        assert RevisionPolicy.is_letra_pura("A1") is False
        assert RevisionPolicy.is_letra_pura("AB") is False

    def test_aprovacao_historica_label_zero(self):
        assert RevisionPolicy.is_aprovacao_historica("0") is True

    def test_aprovacao_historica_letra_pura(self):
        assert RevisionPolicy.is_aprovacao_historica("A") is True
        assert RevisionPolicy.is_aprovacao_historica("B") is True

    def test_aprovacao_historica_nao_para_compostos(self):
        assert RevisionPolicy.is_aprovacao_historica("A1") is False
        assert RevisionPolicy.is_aprovacao_historica("B2") is False
        assert RevisionPolicy.is_aprovacao_historica("1") is False
        assert RevisionPolicy.is_aprovacao_historica("2") is False

    def test_pos_aprovacao_identifica_letras_com_numero(self):
        assert RevisionPolicy.is_pos_aprovacao("A1") is True
        assert RevisionPolicy.is_pos_aprovacao("B2") is True
        assert RevisionPolicy.is_pos_aprovacao("A") is False
        assert RevisionPolicy.is_pos_aprovacao("1") is False


# ---------------------------------------------------------------------------
# Testes de ordem cronologica
# ---------------------------------------------------------------------------

class TestOrdemCronologica:
    """Regra 3: data_emissao > data_elaboracao > ordem; nulls ao fim."""

    def test_ordena_por_data_emissao_asc(self):
        linhas = [
            linha("2", 1, data_emissao="2024-02-01"),
            linha("1", 1, data_emissao="2024-01-01"),
        ]
        resultado = analisar_linhas_documento(CODIGO, linhas)
        assert resultado.linhas[0].linha.label_revisao == "1"
        assert resultado.linhas[1].linha.label_revisao == "2"

    def test_null_data_emissao_vai_ao_fim(self):
        linhas = [
            linha("SEM", 1),              # sem data_emissao
            linha("1", 1, data_emissao="2024-01-01"),
        ]
        resultado = analisar_linhas_documento(CODIGO, linhas)
        assert resultado.linhas[0].linha.label_revisao == "1"
        assert resultado.linhas[1].linha.label_revisao == "SEM"

    def test_empate_data_emissao_desempata_por_data_elaboracao(self):
        linhas = [
            linha("2", 1, data_emissao="2024-01-01", data_elaboracao="2024-01-05", ordem=1),
            linha("1", 1, data_emissao="2024-01-01", data_elaboracao="2024-01-01", ordem=0),
        ]
        resultado = analisar_linhas_documento(CODIGO, linhas)
        # label "1" tem elaboracao anterior, deve vir primeiro
        assert resultado.linhas[0].linha.label_revisao == "1"

    def test_empate_total_desempata_por_ordem(self):
        linhas = [
            linha("2", 1, data_emissao="2024-01-01", ordem=5),
            linha("1", 1, data_emissao="2024-01-01", ordem=1),
        ]
        resultado = analisar_linhas_documento(CODIGO, linhas)
        assert resultado.linhas[0].linha.label_revisao == "1"

    def test_calcular_emissao_labels_respeita_ordem(self):
        linhas = [
            linha("2", 1, data_emissao="2024-02-01"),
            linha("1", 1, data_emissao="2024-01-01"),
        ]
        labels = calcular_emissao_inicial_labels(linhas)
        # labels[0] corresponde a linha 1 (mais antiga), labels[1] a linha 2
        assert labels[0] == "EMISSÃO INICIAL"
        assert labels[1] == "REVISÃO 1"


# ---------------------------------------------------------------------------
# Testes da API calcular_ultima_revisao
# ---------------------------------------------------------------------------

class TestCalcularUltimaRevisao:
    """Regra 5: ultima revisao = linha mais recente na ordem operacional."""

    def test_ultima_revisao_e_a_mais_recente(self):
        linhas = [
            linha("1", 1, data_emissao="2024-01-01"),
            linha("2", 1, data_emissao="2024-02-01"),
        ]
        ultima = calcular_ultima_revisao(linhas)
        assert ultima is not None
        assert ultima.label_revisao == "2"

    def test_ultima_revisao_lista_vazia_retorna_none(self):
        assert calcular_ultima_revisao([]) is None

    def test_ultima_revisao_marcada_como_ultima_no_resultado(self):
        linhas = [
            linha("1", 1, data_emissao="2024-01-01"),
            linha("2", 1, data_emissao="2024-02-01"),
        ]
        resultado = analisar_linhas_documento(CODIGO, linhas)
        ultima = resultado.ultima_revisao
        assert ultima is not None
        assert ultima.eh_ultima_revisao is True
        assert resultado.linhas[0].eh_ultima_revisao is False


# ---------------------------------------------------------------------------
# Testes de calcular_ja_aprovado
# ---------------------------------------------------------------------------

class TestCalcularJaAprovado:

    def test_ja_aprovado_com_label_zero(self):
        linhas = [linha("0", 1)]
        assert calcular_ja_aprovado(linhas) is True

    def test_ja_aprovado_com_letra_pura(self):
        linhas = [linha("A", 1)]
        assert calcular_ja_aprovado(linhas) is True

    def test_nao_aprovado_com_numerico(self):
        linhas = [linha("1", 1), linha("2", 1)]
        assert calcular_ja_aprovado(linhas) is False

    def test_nao_aprovado_lista_vazia(self):
        assert calcular_ja_aprovado([]) is False

    def test_ja_aprovado_mesmo_com_pos_aprovacao(self):
        """Aprovacao historica permanece mesmo com A1 apos 0."""
        linhas = [linha("0", 1), linha("A1", 1)]
        assert calcular_ja_aprovado(linhas) is True


# ---------------------------------------------------------------------------
# Testes de LifecycleResult — propriedades
# ---------------------------------------------------------------------------

class TestLifecycleResult:

    def test_tem_bloqueante_true_quando_ha_bloqueante(self):
        linhas = [
            linha("2", 1, data_emissao="2024-02-01"),   # sem analise
            linha("3", 1, data_emissao="2024-03-01"),
        ]
        resultado = analisar_linhas_documento(CODIGO, linhas)
        assert resultado.tem_bloqueante is True

    def test_tem_bloqueante_false_quando_nao_ha_bloqueante(self):
        linhas = [
            linha("1", 1, data_emissao="2024-01-01"),
        ]
        resultado = analisar_linhas_documento(CODIGO, linhas)
        assert resultado.tem_bloqueante is False

    def test_issues_bloqueantes_filtradas_corretamente(self):
        linhas = [
            linha("2", 1, data_emissao="2024-02-01"),
            linha("3", 1, data_emissao="2024-03-01"),
        ]
        resultado = analisar_linhas_documento(CODIGO, linhas)
        assert len(resultado.issues_bloqueantes) >= 1
        for issue in resultado.issues_bloqueantes:
            assert issue.severidade == SeveridadeIssue.BLOQUEANTE

    def test_issues_avisos_filtradas_corretamente(self):
        existentes = [linha("1", 1, data_emissao="2024-01-01", data_analise="2024-01-10",
                            ja_persistida=True)]
        entradas   = [linha("1", 1, data_emissao="2024-01-01")]
        resultado = analisar_importacao_documental(CODIGO, entradas, existentes)
        for issue in resultado.issues_avisos:
            assert issue.severidade == SeveridadeIssue.AVISO

    def test_codigo_do_resultado_preservado(self):
        resultado = analisar_linhas_documento(CODIGO, [])
        assert resultado.codigo == CODIGO


# ---------------------------------------------------------------------------
# Testes de analisar_importacao_documental
# ---------------------------------------------------------------------------

class TestAnalisarImportacaoDocumental:

    def test_lote_puro_sem_existentes_insere_tudo(self):
        entradas = [
            linha("1", 1, data_emissao="2024-01-01"),
            linha("2", 1, data_emissao="2024-02-01", data_analise="2024-02-10"),
        ]
        resultado = analisar_importacao_documental(CODIGO, entradas)
        assert resultado.total_linhas == 2

    def test_nova_linha_apos_existentes_forma_sequencia_completa(self):
        existentes = [
            linha("1", 1, data_emissao="2024-01-01", data_analise="2024-01-20",
                  ja_persistida=True),
            linha("2", 1, data_emissao="2024-02-01", data_analise="2024-02-15",
                  ja_persistida=True),
        ]
        entradas = [linha("3", 1, data_emissao="2024-03-01")]
        resultado = analisar_importacao_documental(CODIGO, entradas, existentes)
        assert resultado.total_linhas == 3

    def test_nova_linha_sem_data_analise_na_anterior_bloqueia(self):
        """Linha existente (1/1) sem data_analise + nova linha (2/1) → bloqueante."""
        existentes = [
            linha("1", 1, data_emissao="2024-01-01", ja_persistida=True),  # sem analise
        ]
        entradas = [linha("2", 1, data_emissao="2024-02-01")]
        resultado = analisar_importacao_documental(CODIGO, entradas, existentes)
        assert resultado.tem_bloqueante

    def test_sem_entradas_sem_existentes_resultado_vazio(self):
        resultado = analisar_importacao_documental(CODIGO, [])
        assert resultado.total_linhas == 0
        assert not resultado.tem_bloqueante


# ---------------------------------------------------------------------------
# Resultado de linha individual (LinePolicy / resultado_linha)
# ---------------------------------------------------------------------------

class TestResultadoLinhaPolicy:
    """LinePolicy.calcular — resultado visual de linha (vocabulario fechado)."""

    def test_nao_aprovado(self):
        assert LinePolicy.calcular("NÃO APROVADO", "2025-01-01", "2025-02-01") == RESULTADO_NAO_APROVADO

    def test_nao_conforme(self):
        assert LinePolicy.calcular("NÃO CONFORME", "2025-01-01", "2025-02-01") == RESULTADO_NAO_CONFORME

    def test_aprovado(self):
        assert LinePolicy.calcular("APROVADO", "2025-01-01", "2025-02-01") == RESULTADO_APROVADO

    def test_aprovado_variantes_normalizam(self):
        assert LinePolicy.calcular("PARA APROVAÇÃO", "2025-01-01") == RESULTADO_APROVADO
        assert LinePolicy.calcular("EM COLETA DE ASSINATURAS", "2025-01-01") == RESULTADO_APROVADO

    def test_cancelado(self):
        assert LinePolicy.calcular("CANCELADO", "2025-01-01") == RESULTADO_CANCELADO

    def test_emitida_sem_analise_em_analise(self):
        assert LinePolicy.calcular(None, "2025-01-01", None) == RESULTADO_EM_ANALISE

    def test_situacao_em_analise_exibe_em_analise(self):
        assert LinePolicy.calcular("EM ANÁLISE", "2025-01-01", None) == RESULTADO_EM_ANALISE

    def test_sem_data_emissao_em_elaboracao(self):
        assert LinePolicy.calcular(None, None, None) == RESULTADO_EM_ELABORACAO

    def test_nao_aprovado_nunca_vira_em_revisao(self):
        """NÃO APROVADO é resultado de linha; 'Em Revisão' é status consolidado."""
        resultado = LinePolicy.calcular("NÃO APROVADO", "2025-01-01", "2025-02-01")
        assert resultado == RESULTADO_NAO_APROVADO
        assert resultado != STATUS_EM_REVISAO

    def test_funcao_conveniencia_equivalente(self):
        assert calcular_resultado_linha("NÃO APROVADO", "2025-01-01") == RESULTADO_NAO_APROVADO
        assert calcular_resultado_linha("APROVADO", "2025-01-01") == RESULTADO_APROVADO


class TestResultadoLinhaSequenciaReal:
    """
    Caso real DE-15.23.17.84-6J2-1005 (spec):
    sequencia 1/1, 2/1, 3/1, 4/1 (NÃO APROVADO) → 0/1 (APROVADO) → A1/1 (EM ANÁLISE).
    """

    def _sequencia(self):
        return [
            linha("1", 1, situacao="NÃO APROVADO", data_emissao="2025-07-30", data_analise="2025-08-10"),
            linha("2", 1, situacao="NÃO APROVADO", data_emissao="2025-09-24", data_analise="2025-10-05"),
            linha("3", 1, situacao="NÃO APROVADO", data_emissao="2025-10-23", data_analise="2025-11-10"),
            linha("4", 1, situacao="NÃO APROVADO", data_emissao="2025-11-26", data_analise="2025-12-15"),
            linha("0", 1, situacao="APROVADO",     data_emissao="2026-02-23", data_analise="2026-03-10"),
            linha("A1", 1, situacao="EM ANÁLISE",  data_emissao="2026-05-14"),
        ]

    def test_linhas_1_a_4_resultado_nao_aprovado(self):
        resultado = analisar_linhas_documento(CODIGO, self._sequencia())
        por_label = {ll.linha.label_revisao: ll.resultado_linha for ll in resultado.linhas}
        assert por_label["1"] == RESULTADO_NAO_APROVADO
        assert por_label["2"] == RESULTADO_NAO_APROVADO
        assert por_label["3"] == RESULTADO_NAO_APROVADO
        assert por_label["4"] == RESULTADO_NAO_APROVADO

    def test_linha_0_resultado_aprovado(self):
        resultado = analisar_linhas_documento(CODIGO, self._sequencia())
        por_label = {ll.linha.label_revisao: ll.resultado_linha for ll in resultado.linhas}
        assert por_label["0"] == RESULTADO_APROVADO

    def test_linha_a1_resultado_em_analise(self):
        resultado = analisar_linhas_documento(CODIGO, self._sequencia())
        por_label = {ll.linha.label_revisao: ll.resultado_linha for ll in resultado.linhas}
        assert por_label["A1"] == RESULTADO_EM_ANALISE

    def test_status_documento_atual_em_analise(self):
        resultado = analisar_linhas_documento(CODIGO, self._sequencia())
        assert resultado.status_atual == STATUS_EM_ANALISE

    def test_ja_aprovado_true(self):
        resultado = analisar_linhas_documento(CODIGO, self._sequencia())
        assert resultado.ja_aprovado is True

    def test_resultado_linha_nao_expoe_conceitos_internos(self):
        """Nenhum resultado de linha deve conter termos internos da engine."""
        resultado = analisar_linhas_documento(CODIGO, self._sequencia())
        proibidos = {"superada", "histórica", "historica", "inferida", "substituída", "substituida"}
        for ll in resultado.linhas:
            texto = ll.resultado_linha.lower()
            assert not any(p in texto for p in proibidos)
