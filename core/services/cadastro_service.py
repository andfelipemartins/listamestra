"""
core/services/cadastro_service.py

Regras de aplicacao do Cadastro Manual.

Concentra validacao de codigo, normalizacao de payload e orquestracao da
persistencia. Nao depende de Streamlit nem do estado de sessao da pagina.
Continua a usar core.importers.cadastro_importer.salvar_documento_revisao
para preservar a transacao ja testada (upsert + emissao_inicial + ultima_revisao).
"""

from dataclasses import dataclass, field
from typing import Optional

from core.importers.cadastro_importer import salvar_documento_revisao
from core.parsers.registry import ParserRegistry
from core.repositories.documento_repository import DocumentoRepository
from core.repositories.revisao_repository import RevisaoRepository


@dataclass
class ResultadoValidacao:
    """Retorno estruturado de validar_codigo."""
    codigo: str
    valido: bool
    mensagem_erro: Optional[str] = None
    parsed: Optional[object] = None
    dados_derivados: dict = field(default_factory=dict)
    documento_existente: Optional[dict] = None
    revisoes_existentes: list[dict] = field(default_factory=list)


@dataclass
class ResultadoCadastro:
    """Retorno estruturado de cadastrar_documento_manual."""
    sucesso: bool
    codigo: str
    mensagem: str
    documento_id: Optional[int] = None
    revisao_id: Optional[int] = None
    documento_existente: bool = False
    erros: list[str] = field(default_factory=list)
    alertas: list[str] = field(default_factory=list)


class CadastroService:
    def __init__(
        self,
        doc_repo: Optional[DocumentoRepository] = None,
        rev_repo: Optional[RevisaoRepository] = None,
        parser_registry: Optional[ParserRegistry] = None,
        db_path: Optional[str] = None,
    ):
        self._doc_repo = doc_repo or DocumentoRepository(db_path)
        self._rev_repo = rev_repo or RevisaoRepository(db_path)
        self._registry = parser_registry or ParserRegistry()
        self._db_path = db_path

    # ------------------------------------------------------------------
    # Consultas auxiliares
    # ------------------------------------------------------------------

    def buscar_documento_existente(
        self, contrato_id: int, codigo: str
    ) -> Optional[dict]:
        return self._doc_repo.buscar_por_codigo(contrato_id, codigo)

    def listar_revisoes_existentes(self, documento_id: int) -> list[dict]:
        return self._rev_repo.listar_resumo_por_documento(documento_id)

    # ------------------------------------------------------------------
    # Validação e dados derivados
    # ------------------------------------------------------------------

    def _extrair_dados_derivados(self, parsed) -> dict:
        """Campos derivados do parse usados pela UI e pela persistencia."""
        e = parsed.extras or {}
        classe = e.get("classe", "") or ""
        subclasse = e.get("subclasse", "") or ""
        return {
            "tipo": parsed.tipo,
            "descricao_tipo": parsed.descricao_tipo,
            "trecho": e.get("trecho", ""),
            "nome_trecho": e.get("nome_trecho", ""),
            "etapa": e.get("etapa", ""),
            "classe": classe,
            "subclasse": subclasse,
            "disciplina": (classe + subclasse) or None,
            "fase": e.get("etapa") or None,
        }

    def validar_codigo(
        self, contrato_id: int, codigo: str
    ) -> ResultadoValidacao:
        """Faz o parse do codigo e enriquece com lookup do existente."""
        parsed = self._registry.parse(codigo)
        if not getattr(parsed, "valido", False):
            return ResultadoValidacao(
                codigo=codigo,
                valido=False,
                mensagem_erro=getattr(parsed, "mensagem", "Código inválido."),
                parsed=parsed,
            )

        existente = self.buscar_documento_existente(contrato_id, codigo)
        revisoes = (
            self.listar_revisoes_existentes(existente["id"])
            if existente else []
        )
        return ResultadoValidacao(
            codigo=codigo,
            valido=True,
            parsed=parsed,
            dados_derivados=self._extrair_dados_derivados(parsed),
            documento_existente=existente,
            revisoes_existentes=revisoes,
        )

    def montar_resultado_validacao(
        self, codigo: str, parse_result, documento_existente: Optional[dict] = None
    ) -> ResultadoValidacao:
        """Monta ResultadoValidacao a partir de um parse ja feito (reuso externo)."""
        if not getattr(parse_result, "valido", False):
            return ResultadoValidacao(
                codigo=codigo,
                valido=False,
                mensagem_erro=getattr(parse_result, "mensagem", "Código inválido."),
                parsed=parse_result,
            )
        revisoes = (
            self.listar_revisoes_existentes(documento_existente["id"])
            if documento_existente else []
        )
        return ResultadoValidacao(
            codigo=codigo,
            valido=True,
            parsed=parse_result,
            dados_derivados=self._extrair_dados_derivados(parse_result),
            documento_existente=documento_existente,
            revisoes_existentes=revisoes,
        )

    def validar_campos_obrigatorios(
        self, doc_fields: dict, rev_fields: dict
    ) -> list[str]:
        """Retorna lista de erros (vazia se tudo ok)."""
        erros = []
        titulo = (doc_fields.get("titulo") or "").strip()
        label = str(rev_fields.get("label_revisao") or "").strip()
        if not titulo:
            erros.append("Descrição/Objeto é obrigatório.")
        if not label:
            erros.append("Revisão é obrigatória.")
        return erros

    # ------------------------------------------------------------------
    # Normalização e preparação de payload
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_or_none(val):
        if val is None:
            return None
        if isinstance(val, str):
            val = val.strip()
            return val or None
        return val

    def normalizar_payload_formulario(
        self, doc_fields: dict, rev_fields: dict
    ) -> tuple[dict, dict]:
        """Aplica strip e converte vazios para None nos campos de UI."""
        doc_norm = {
            "titulo": self._strip_or_none(doc_fields.get("titulo")),
            "responsavel": self._strip_or_none(doc_fields.get("responsavel")),
            "modalidade": self._strip_or_none(doc_fields.get("modalidade")),
        }
        rev_norm = {
            "label_revisao": str(rev_fields.get("label_revisao") or "").strip(),
            "versao": int(rev_fields.get("versao") or 1),
            "data_elaboracao": rev_fields.get("data_elaboracao") or None,
            "data_emissao": rev_fields.get("data_emissao") or None,
            "data_analise": rev_fields.get("data_analise") or None,
            "situacao": rev_fields.get("situacao") or None,
            "situacao_real": self._strip_or_none(rev_fields.get("situacao_real")),
            "analise_interna": self._strip_or_none(rev_fields.get("analise_interna")),
            "data_circular": rev_fields.get("data_circular") or None,
            "num_circular": self._strip_or_none(rev_fields.get("num_circular")),
        }
        return doc_norm, rev_norm

    def preparar_documento_para_cadastro(
        self,
        contrato_id: int,
        codigo: str,
        dados_formulario: dict,
    ) -> dict:
        """Dict pronto para DocumentoRepository.criar_documento.

        disciplina e fase sao derivadas do codigo (fonte da verdade);
        outros campos vem do formulario.
        """
        parsed = self._registry.parse(codigo)
        derivados = (
            self._extrair_dados_derivados(parsed)
            if getattr(parsed, "valido", False) else {}
        )
        doc_norm = {
            "titulo": self._strip_or_none(dados_formulario.get("titulo")),
            "responsavel": self._strip_or_none(dados_formulario.get("responsavel")),
            "modalidade": self._strip_or_none(dados_formulario.get("modalidade")),
        }
        return {
            "contrato_id": contrato_id,
            "codigo": codigo,
            "tipo": derivados.get("tipo"),
            "titulo": doc_norm["titulo"],
            "disciplina": derivados.get("disciplina"),
            "modalidade": doc_norm["modalidade"],
            "responsavel": doc_norm["responsavel"],
            "fase": derivados.get("fase"),
            "trecho": derivados.get("trecho") or None,
            "nome_trecho": derivados.get("nome_trecho") or None,
            "origem": "cadastro_manual",
        }

    def preparar_revisao_para_cadastro(
        self,
        documento: dict,
        dados_formulario: dict,
    ) -> dict:
        """Dict pronto para RevisaoRepository.criar_revisao."""
        label = str(dados_formulario.get("label_revisao") or "").strip()
        try:
            revisao_int = int(label)
        except (ValueError, TypeError):
            revisao_int = None
        return {
            "documento_id": documento["id"],
            "revisao": revisao_int,
            "versao": int(dados_formulario.get("versao") or 1),
            "label_revisao": label,
            "data_elaboracao": dados_formulario.get("data_elaboracao") or None,
            "data_emissao": dados_formulario.get("data_emissao") or None,
            "data_analise": dados_formulario.get("data_analise") or None,
            "situacao_real": self._strip_or_none(dados_formulario.get("situacao_real")),
            "situacao": dados_formulario.get("situacao") or None,
            "emissao_circular": self._strip_or_none(dados_formulario.get("num_circular")),
            "analise_circular": self._strip_or_none(dados_formulario.get("analise_interna")),
            "data_circular": dados_formulario.get("data_circular") or None,
            "ultima_revisao": 0,
            "origem": "cadastro_manual",
        }

    # ------------------------------------------------------------------
    # Orquestração da persistência
    # ------------------------------------------------------------------

    def cadastrar_documento_manual(
        self,
        contrato_id: int,
        codigo: str,
        doc_fields: dict,
        rev_fields: dict,
        grds: Optional[list[dict]] = None,
        db_path: Optional[str] = None,
    ) -> ResultadoCadastro:
        """Orquestra o cadastro manual de 1 documento/revisao.

        - normaliza payload do formulario;
        - valida campos obrigatorios;
        - delega persistencia para salvar_documento_revisao (transacao testada);
        - retorna ResultadoCadastro estruturado.
        """
        grds = grds or []
        doc_norm, rev_norm = self.normalizar_payload_formulario(doc_fields, rev_fields)
        erros = self.validar_campos_obrigatorios(doc_norm, rev_norm)
        if erros:
            return ResultadoCadastro(
                sucesso=False,
                codigo=codigo,
                mensagem="Campos obrigatórios faltando.",
                erros=erros,
            )

        existente_antes = (
            self.buscar_documento_existente(contrato_id, codigo) is not None
        )

        mensagem = salvar_documento_revisao(
            contrato_id, codigo, doc_norm, rev_norm, grds,
            db_path=db_path or self._db_path,
        )

        msg_lower = mensagem.lower()
        sucesso = "sucesso" in msg_lower
        alertas = [mensagem] if "já existe" in msg_lower else []

        doc = self.buscar_documento_existente(contrato_id, codigo)
        doc_id = doc["id"] if doc else None
        revisao_id = None
        if doc and sucesso:
            ultima = self._rev_repo.buscar_ultima_revisao(doc_id)
            revisao_id = ultima["id"] if ultima else None

        return ResultadoCadastro(
            sucesso=sucesso,
            codigo=codigo,
            mensagem=mensagem,
            documento_id=doc_id,
            revisao_id=revisao_id,
            documento_existente=existente_antes,
            alertas=alertas,
        )
