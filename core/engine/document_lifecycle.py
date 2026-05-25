"""
core/engine/document_lifecycle.py

Engine central de ciclo documental do SCLME.

Fonte unica de verdade para: status operacional, aprovacao historica,
ordem cronologica, ultima revisao, rotulos de emissao, inferencia de
linha anterior e deteccao de conflitos/pendencias.

Sem dependencias de Streamlit. Sem acesso direto ao banco.
Recebe LinhaDocumental, devolve LifecycleResult.

Regras codificadas (correspondencia com spec):
  Regra  2 — chave logica: codigo + label_revisao + versao
  Regra  3 — ordem: data_emissao > data_elaboracao > ordem (nulls ao fim)
  Regra  5 — ultima revisao = linha mais recente na ordem operacional
  Regra  6 — situacao_importada preservada; status_operacional calculado
  Regra  8 — aprovacao historica: label '0' ou letra pura [A-Z]
  Regras 9A/9B/9C — inferencia de linha anterior por revisao/versao posterior
  Regra 10 — data_analise obrigatoria em linha superada/substituida (bloqueante)
  Regras 11-15 — mapeamento completo de status operacional
  Regra 16 — ausencia no lote importado nao inativa linha existente
  Regra 19 — conflitos detectados e reportados como LifecycleIssue
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from core.engine.disciplinas import SITUACOES_APROVADO


# ---------------------------------------------------------------------------
# Constantes de dominio
# ---------------------------------------------------------------------------

SITUACOES_REVISAO: frozenset[str] = frozenset({"NÃO APROVADO", "NÃO CONFORME"})

STATUS_CANCELADO    = "Cancelado"
STATUS_APROVADO     = "Aprovado"
STATUS_EM_REVISAO   = "Em Revisão"
STATUS_EM_ANALISE   = "Em Análise"
STATUS_EM_ELABORACAO = "Em Elaboração"

STATUS_ORDEM = [
    STATUS_EM_ELABORACAO,
    STATUS_EM_ANALISE,
    STATUS_EM_REVISAO,
    STATUS_APROVADO,
    STATUS_CANCELADO,
]

# Padroes de label de revisao
_RE_NUMERICA      = re.compile(r"^\d+$")          # 0, 1, 2, ...
_RE_LETRA_PURA    = re.compile(r"^[A-Z]$")        # A, B, C — aprovacao historica
_RE_POS_APROVACAO = re.compile(r"^[A-Z]\d+$")     # A1, A2, B1 — nao conta como aprovacao


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TipoInferencia(str, Enum):
    """O que a engine inferiu sobre uma linha a partir da linha subsequente."""
    NENHUMA               = "nenhuma"
    SUPERADA_POR_REVISAO  = "superada_por_revisao"   # nova revisao numerica superior
    SUBSTITUIDA_POR_VERSAO = "substituida_por_versao" # nova versao da mesma revisao
    APROVACAO_HISTORICA   = "aprovacao_historica"     # manteve aprovacao historica


class SeveridadeIssue(str, Enum):
    BLOQUEANTE = "bloqueante"
    AVISO      = "aviso"


class TipoIssue(str, Enum):
    DATA_ANALISE_OBRIGATORIA  = "data_analise_obrigatoria"   # bloqueante
    CHAVE_DUPLICADA           = "chave_duplicada"             # bloqueante
    ATUALIZACAO_LINHA_EXISTENTE = "atualizacao_linha_existente"  # aviso
    DATA_EMISSAO_FORA_DE_ORDEM = "data_emissao_fora_de_ordem"   # aviso
    STATUS_INCONSISTENTE      = "status_inconsistente"        # aviso


# ---------------------------------------------------------------------------
# DTOs de entrada e saida
# ---------------------------------------------------------------------------

@dataclass
class LinhaDocumental:
    """
    Representa uma linha da Lista Mestra (uma revisao + versao de um documento).

    Entrada da engine — agnóstica de banco de dados e de Streamlit.
    Corresponde a uma linha na tabela `revisoes`.
    """
    codigo: str
    label_revisao: str          # "0", "1", "A", "A1", "B1" etc.
    versao: int                 # 1, 2, 3, ...
    situacao: Optional[str]     = None   # valor bruto importado
    data_emissao: Optional[str] = None
    data_analise: Optional[str] = None
    data_elaboracao: Optional[str] = None
    situacao_real: Optional[str] = None  # manual — engine nunca infere
    id: Optional[int]           = None   # id no banco, se persistida
    importacao_id: Optional[int] = None
    ordem: int                  = 0      # tiebreaker cronologico (id / posicao de importacao)
    ja_persistida: bool         = False  # True se ja existe no banco

    @property
    def chave_logica(self) -> str:
        """Identificador unico de linha: codigo|label|versao (Regra 2)."""
        return f"{self.codigo}|{self.label_revisao}|{self.versao}"


@dataclass
class LifecycleIssue:
    """Problema ou conflito detectado pela engine."""
    tipo: TipoIssue
    severidade: SeveridadeIssue
    descricao: str
    linha_chave: Optional[str] = None   # chave_logica da linha afetada


@dataclass
class LifecycleLine:
    """Linha documental enriquecida com analise de ciclo de vida."""
    linha: LinhaDocumental
    status_operacional: str
    emissao_inicial_label: str
    inferencia: TipoInferencia
    inferencia_descricao: Optional[str]
    eh_ultima_revisao: bool
    issues: list[LifecycleIssue] = field(default_factory=list)

    @property
    def tem_bloqueante(self) -> bool:
        return any(i.severidade == SeveridadeIssue.BLOQUEANTE for i in self.issues)


@dataclass
class LifecycleResult:
    """Resultado completo da analise de ciclo de vida de um documento."""
    codigo: str
    linhas: list[LifecycleLine]           = field(default_factory=list)
    issues_documento: list[LifecycleIssue] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Propriedades derivadas (nao armazenadas)
    # ------------------------------------------------------------------

    @property
    def ja_aprovado(self) -> bool:
        """True se existe alguma linha com aprovacao historica (Regra 8)."""
        return any(
            RevisionPolicy.is_aprovacao_historica(ll.linha.label_revisao)
            for ll in self.linhas
        )

    @property
    def ultima_revisao(self) -> Optional[LifecycleLine]:
        """Linha mais recente na ordem operacional."""
        candidates = [ll for ll in self.linhas if ll.eh_ultima_revisao]
        return candidates[0] if candidates else None

    @property
    def status_atual(self) -> str:
        """Status operacional da ultima revisao."""
        ur = self.ultima_revisao
        return ur.status_operacional if ur else STATUS_EM_ELABORACAO

    @property
    def todas_issues(self) -> list[LifecycleIssue]:
        result = list(self.issues_documento)
        for ll in self.linhas:
            result.extend(ll.issues)
        return result

    @property
    def tem_bloqueante(self) -> bool:
        return any(i.severidade == SeveridadeIssue.BLOQUEANTE for i in self.todas_issues)

    @property
    def total_linhas(self) -> int:
        return len(self.linhas)

    @property
    def issues_bloqueantes(self) -> list[LifecycleIssue]:
        return [i for i in self.todas_issues if i.severidade == SeveridadeIssue.BLOQUEANTE]

    @property
    def issues_avisos(self) -> list[LifecycleIssue]:
        return [i for i in self.todas_issues if i.severidade == SeveridadeIssue.AVISO]


# ---------------------------------------------------------------------------
# Politicas de dominio — funcoes puras sem estado e sem banco
# ---------------------------------------------------------------------------

class RevisionPolicy:
    """Regras sobre labels de revisao (Regras 2, 8)."""

    @staticmethod
    def is_numerica(label: str) -> bool:
        """Revisao puramente numerica: '0', '1', '2', ..."""
        return bool(_RE_NUMERICA.match(label or ""))

    @staticmethod
    def valor_numerico(label: str) -> Optional[int]:
        """Valor inteiro de revisao numerica, ou None se nao for numerica."""
        try:
            return int(label) if RevisionPolicy.is_numerica(label) else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def is_letra_pura(label: str) -> bool:
        """Letra maiuscula unica: 'A', 'B', ... — conta como aprovacao historica."""
        return bool(_RE_LETRA_PURA.match(label or ""))

    @staticmethod
    def is_aprovacao_historica(label: str) -> bool:
        """'0' ou letra pura — conta como aprovacao historica (Regra 8)."""
        return label == "0" or RevisionPolicy.is_letra_pura(label)

    @staticmethod
    def is_pos_aprovacao(label: str) -> bool:
        """A1, A2, B1... — pos-aprovacao, nao conta como aprovacao historica."""
        return bool(_RE_POS_APROVACAO.match(label or ""))


class StatusPolicy:
    """Regras de calculo de status operacional (Regras 11-15)."""

    @staticmethod
    def calcular(
        situacao: Optional[str],
        data_emissao: Optional[str],
        data_analise: Optional[str] = None,
    ) -> str:
        """
        Status operacional calculado pela engine — nao depende do valor importado.

        Ordem de precedencia:
        1. CANCELADO                                          → Cancelado
        2. situacao in SITUACOES_APROVADO                    → Aprovado
        3. situacao in SITUACOES_REVISAO (NÃO APROVADO, etc) → Em Revisão
        4. data_analise preenchida (e situacao nao conclusiva) → Em Revisão
        5. data_emissao preenchida (sem data_analise)         → Em Análise
        6. sem data_emissao                                   → Em Elaboração
        """
        s = (situacao or "").strip().upper()

        if s == "CANCELADO":
            return STATUS_CANCELADO

        if s in SITUACOES_APROVADO:
            return STATUS_APROVADO

        if s in SITUACOES_REVISAO:
            return STATUS_EM_REVISAO

        # Qualquer outra situacao com data_analise registrada = revisao concluida
        if data_analise:
            return STATUS_EM_REVISAO

        if data_emissao:
            return STATUS_EM_ANALISE

        return STATUS_EM_ELABORACAO


# ---------------------------------------------------------------------------
# Funcoes auxiliares internas
# ---------------------------------------------------------------------------

def _chave_ordem(linha: LinhaDocumental) -> tuple:
    """
    Chave de ordenacao cronologica (Regra 3).

    Ordem: NULL dates last → data_emissao → data_elaboracao → ordem (id).
    """
    sem_emissao    = 0 if linha.data_emissao    else 1
    sem_elaboracao = 0 if linha.data_elaboracao else 1
    return (
        sem_emissao,
        linha.data_emissao    or "",
        sem_elaboracao,
        linha.data_elaboracao or "",
        linha.ordem,
    )


def _ordenar_linhas(linhas: list[LinhaDocumental]) -> list[LinhaDocumental]:
    """Retorna copia ordenada cronologicamente (Regra 3)."""
    return sorted(linhas, key=_chave_ordem)


def _calcular_emissao_labels(ordenadas: list[LinhaDocumental]) -> list[str]:
    """
    Gera rotulos de emissao inicial para cada linha na sequencia ordenada (Regra 3).

    - indice 0       → EMISSÃO INICIAL
    - indices 1..N-2 → REVISÃO 1, REVISÃO 2, ...
    - indice N-1     → REVISÃO FINAL se situacao aprovada; senão REVISÃO N-1
    """
    n = len(ordenadas)
    if n == 0:
        return []

    labels: list[str] = []
    for i, linha in enumerate(ordenadas):
        if i == 0:
            labels.append("EMISSÃO INICIAL")
        elif i == n - 1:
            s = (linha.situacao or "").strip().upper()
            if s in SITUACOES_APROVADO:
                labels.append("REVISÃO FINAL")
            else:
                labels.append(f"REVISÃO {i}")
        else:
            labels.append(f"REVISÃO {i}")
    return labels


def _inferir_linha_anterior(
    linha_atual: LinhaDocumental,
    linha_proxima: LinhaDocumental,
) -> TipoInferencia:
    """
    Determina a inferencia aplicada em linha_atual dado que linha_proxima
    e a sua sucessora imediata na ordem cronologica (Regra 9).

    A. Nova revisao numerica superior      → SUPERADA_POR_REVISAO
    B. Mesma label, versao maior           → SUBSTITUIDA_POR_VERSAO
    C. Linha com aprovacao historica       → APROVACAO_HISTORICA
    """
    label_atual = linha_atual.label_revisao
    label_prox  = linha_proxima.label_revisao

    # B — mesma label, versao maior: substituicao (verificado ANTES de aprovacao historica)
    # Ex: 0/1 → 0/2 e SUBSTITUIDA_POR_VERSAO, nao APROVACAO_HISTORICA
    if label_atual == label_prox and linha_proxima.versao > linha_atual.versao:
        return TipoInferencia.SUBSTITUIDA_POR_VERSAO

    # C — aprovacao historica: apenas quando label seguinte e distinto
    if RevisionPolicy.is_aprovacao_historica(label_atual):
        return TipoInferencia.APROVACAO_HISTORICA

    # A — revisao numerica superior: superacao
    num_atual = RevisionPolicy.valor_numerico(label_atual)
    num_prox  = RevisionPolicy.valor_numerico(label_prox)
    if num_atual is not None and num_prox is not None and num_prox > num_atual:
        return TipoInferencia.SUPERADA_POR_REVISAO

    return TipoInferencia.NENHUMA


def _descricao_inferencia(
    inferencia: TipoInferencia,
    proxima: LinhaDocumental,
) -> Optional[str]:
    """Texto legivel da inferencia para exibicao na previa."""
    if inferencia == TipoInferencia.SUPERADA_POR_REVISAO:
        return (
            f"Superada pela revisão {proxima.label_revisao}/v{proxima.versao} — "
            "não aprovada pelo cliente (inferência da engine)"
        )
    if inferencia == TipoInferencia.SUBSTITUIDA_POR_VERSAO:
        return (
            f"Substituída pela versão {proxima.versao} da revisão "
            f"{proxima.label_revisao} — não conforme (inferência da engine)"
        )
    if inferencia == TipoInferencia.APROVACAO_HISTORICA:
        return "Aprovação histórica mantida — revisão subsequente não cancela aprovação anterior"
    return None


def _gerar_issues_linha(
    linha: LinhaDocumental,
    inferencia: TipoInferencia,
) -> list[LifecycleIssue]:
    """
    Gera issues especificas de uma linha dado sua inferencia (Regra 10).

    Quando inferencia ativa (SUPERADA ou SUBSTITUIDA) e data_analise ausente
    → issue BLOQUEANTE de data_analise_obrigatoria.
    """
    issues: list[LifecycleIssue] = []

    if inferencia in (TipoInferencia.SUPERADA_POR_REVISAO, TipoInferencia.SUBSTITUIDA_POR_VERSAO):
        if not linha.data_analise:
            if inferencia == TipoInferencia.SUPERADA_POR_REVISAO:
                motivo = "superada por revisão posterior"
            else:
                motivo = "substituída por nova versão"
            issues.append(LifecycleIssue(
                tipo=TipoIssue.DATA_ANALISE_OBRIGATORIA,
                severidade=SeveridadeIssue.BLOQUEANTE,
                descricao=(
                    f"data_analise obrigatória: revisão {linha.label_revisao}/v{linha.versao} "
                    f"foi {motivo} mas não possui data de análise registrada. "
                    "Preencha antes de confirmar a importação."
                ),
                linha_chave=linha.chave_logica,
            ))

    return issues


def _detectar_duplicatas(linhas: list[LinhaDocumental]) -> list[LifecycleIssue]:
    """Detecta chaves duplicadas no lote de entrada (Regra 19)."""
    issues: list[LifecycleIssue] = []
    vistas: set[str] = set()
    for linha in linhas:
        chave = linha.chave_logica
        if chave in vistas:
            issues.append(LifecycleIssue(
                tipo=TipoIssue.CHAVE_DUPLICADA,
                severidade=SeveridadeIssue.BLOQUEANTE,
                descricao=(
                    f"Chave duplicada: {chave} aparece mais de uma vez no lote de entrada — "
                    "apenas uma ocorrência pode ser processada"
                ),
                linha_chave=chave,
            ))
        else:
            vistas.add(chave)
    return issues


# ---------------------------------------------------------------------------
# Engine principal
# ---------------------------------------------------------------------------

class DocumentLifecycleEngine:
    """
    Engine central de ciclo documental do SCLME.

    Sem estado. Sem banco. Sem Streamlit.
    Recebe listas de LinhaDocumental, devolve LifecycleResult.

    Uso tipico:
        engine = DocumentLifecycleEngine()
        resultado = engine.analisar_linhas_documento(codigo, linhas)
        if resultado.tem_bloqueante:
            mostrar_pendencias(resultado.issues_bloqueantes)
    """

    def analisar_linhas_documento(
        self,
        codigo: str,
        linhas: list[LinhaDocumental],
    ) -> LifecycleResult:
        """
        Analisa o ciclo de vida completo de um documento.

        Dado o conjunto de todas as linhas (revisoes/versoes) do documento,
        calcula: ordem cronologica, rotulos de emissao, status operacional
        de cada linha, inferencias entre linhas consecutivas e issues.

        Nao persiste nada. Pode ser chamado com linhas existentes (do banco)
        ou com linhas ainda nao persistidas (preview).
        """
        if not linhas:
            return LifecycleResult(codigo=codigo)

        # Detecta duplicatas no lote (Regra 19)
        issues_doc = _detectar_duplicatas(linhas)

        # Ordena cronologicamente (Regra 3)
        ordenadas = _ordenar_linhas(linhas)
        n = len(ordenadas)

        # Rotulos de emissao inicial (Regra 3)
        labels = _calcular_emissao_labels(ordenadas)

        # Processa cada linha
        lifecycle_lines: list[LifecycleLine] = []
        for i, linha in enumerate(ordenadas):
            status_op = StatusPolicy.calcular(
                linha.situacao, linha.data_emissao, linha.data_analise
            )

            # Inferencia: determinada pela linha subsequente (Regra 9)
            if i < n - 1:
                proxima    = ordenadas[i + 1]
                inferencia = _inferir_linha_anterior(linha, proxima)
                desc_inf   = _descricao_inferencia(inferencia, proxima)
            else:
                inferencia = TipoInferencia.NENHUMA
                desc_inf   = None

            # Override: linha superada/substituida entra em revisao (exceto cancelada)
            if inferencia in (
                TipoInferencia.SUPERADA_POR_REVISAO,
                TipoInferencia.SUBSTITUIDA_POR_VERSAO,
            ) and status_op != STATUS_CANCELADO:
                status_op = STATUS_EM_REVISAO

            # Issues desta linha (Regra 10)
            issues_linha = _gerar_issues_linha(linha, inferencia)

            lifecycle_lines.append(LifecycleLine(
                linha=linha,
                status_operacional=status_op,
                emissao_inicial_label=labels[i],
                inferencia=inferencia,
                inferencia_descricao=desc_inf,
                eh_ultima_revisao=(i == n - 1),
                issues=issues_linha,
            ))

        return LifecycleResult(
            codigo=codigo,
            linhas=lifecycle_lines,
            issues_documento=issues_doc,
        )

    def analisar_importacao_documental(
        self,
        codigo: str,
        linhas_entrada: list[LinhaDocumental],
        linhas_existentes: Optional[list[LinhaDocumental]] = None,
    ) -> LifecycleResult:
        """
        Analisa o impacto de importar novas linhas num documento com historico existente.

        Combina linhas_existentes + linhas_entrada sem duplicar chaves:
        - Chave nova: inserção pura — linha aparece na sequencia combinada
        - Chave existente: tentativa de atualização — gera AVISO (Regra 2)

        Ausencia de linha no lote de entrada nao inativa existente (Regra 16).

        Nao persiste nada. Retorna LifecycleResult com analise da sequencia completa.
        """
        existentes = linhas_existentes or []
        chaves_existentes = {l.chave_logica: l for l in existentes}

        linhas_combinadas: list[LinhaDocumental] = list(existentes)
        issues_combinacao: list[LifecycleIssue] = []

        for entrada in linhas_entrada:
            if entrada.chave_logica in chaves_existentes:
                # Atualizacao: linha ja existe — aviso, nao duplica (Regra 2)
                issues_combinacao.append(LifecycleIssue(
                    tipo=TipoIssue.ATUALIZACAO_LINHA_EXISTENTE,
                    severidade=SeveridadeIssue.AVISO,
                    descricao=(
                        f"Linha {entrada.chave_logica} já existe no banco — "
                        "sera atualizada se houver mudanca relevante nos campos"
                    ),
                    linha_chave=entrada.chave_logica,
                ))
                # Substitui pela versao mais recente dos dados
                linhas_combinadas = [
                    entrada if l.chave_logica == entrada.chave_logica else l
                    for l in linhas_combinadas
                ]
            else:
                linhas_combinadas.append(entrada)

        resultado = self.analisar_linhas_documento(codigo, linhas_combinadas)
        resultado.issues_documento.extend(issues_combinacao)
        return resultado


# ---------------------------------------------------------------------------
# API de conveniencia — funcoes de modulo (evita instanciar a engine manualmente)
# ---------------------------------------------------------------------------

_engine = DocumentLifecycleEngine()


def calcular_status_operacional(
    situacao: Optional[str],
    data_emissao: Optional[str],
    data_analise: Optional[str] = None,
) -> str:
    """
    Calcula status operacional de uma linha documental (Regras 11-15).

    Versao mais precisa de classificar_status() do modulo status.py:
    - Adiciona tratamento de NÃO CONFORME, CANCELADO e data_analise.
    - Nao quebra compatibilidade com chamadas existentes (data_analise opcional).
    """
    return StatusPolicy.calcular(situacao, data_emissao, data_analise)


def calcular_ja_aprovado(linhas: list[LinhaDocumental]) -> bool:
    """True se o documento possui aprovacao historica em alguma linha (Regra 8)."""
    return any(RevisionPolicy.is_aprovacao_historica(l.label_revisao) for l in linhas)


def calcular_ultima_revisao(
    linhas: list[LinhaDocumental],
) -> Optional[LinhaDocumental]:
    """Retorna a linha mais recente segundo a ordem operacional (Regra 5)."""
    if not linhas:
        return None
    return _ordenar_linhas(linhas)[-1]


def calcular_emissao_inicial_labels(
    linhas: list[LinhaDocumental],
) -> list[str]:
    """
    Gera rotulos de emissao inicial para a sequencia ordenada de linhas (Regra 3).

    Retorna lista na mesma ordem que as linhas apos ordenacao cronologica.
    """
    return _calcular_emissao_labels(_ordenar_linhas(linhas))


def analisar_linhas_documento(
    codigo: str,
    linhas: list[LinhaDocumental],
) -> LifecycleResult:
    """Analisa ciclo de vida de um documento dado seu conjunto de linhas."""
    return _engine.analisar_linhas_documento(codigo, linhas)


def analisar_importacao_documental(
    codigo: str,
    linhas_entrada: list[LinhaDocumental],
    linhas_existentes: Optional[list[LinhaDocumental]] = None,
) -> LifecycleResult:
    """Analisa o impacto de importar novas linhas num documento com historico."""
    return _engine.analisar_importacao_documental(
        codigo, linhas_entrada, linhas_existentes or []
    )


def analisar_transicao_documental(
    codigo: str,
    linhas_antes: list[LinhaDocumental],
    linhas_depois: list[LinhaDocumental],
) -> LifecycleResult:
    """
    Analisa o ciclo documental no estado final depois de uma transicao (importacao/atualizacao).

    Diferente de analisar_importacao_documental — que recebe apenas linhas novas e
    mescla com as existentes — esta funcao analisa o estado completo depois da
    importacao. Isso garante que:

    - Linhas atualizadas sao analisadas com seus novos valores (ex: data_analise
      preenchida resolve um bloqueante; data_analise ausente cria um bloqueante).
    - O historico completo de revisoes e considerado na ordem correta.
    - Linhas ausentes do lote nao sao inativadas (Regra 16 — o banco temporario
      ja preserva todas as linhas existentes via upsert idempotente).

    linhas_antes e aceito por completude e possiveis extensoes futuras, mas a
    analise de ciclo documental e feita exclusivamente sobre linhas_depois.

    Nao persiste nada. Nao altera nenhum banco.
    """
    return _engine.analisar_linhas_documento(codigo, linhas_depois)
