import os
import re
import sqlite3
import threading
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.db import close_old_connections, connections
from django.utils import timezone

from .models import BackupTentativa


_NOME_BACKUP = re.compile(r"^sclme_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2}-\d{6})\.sqlite3$")
_RETENCAO = 30
_IDADE_LOCK_HORAS = 12
_disparo_lock = threading.Lock()
_ultimo_disparo_preguicoso = None


@dataclass(frozen=True)
class ResultadoBackup:
    sucesso: bool
    caminho: Path | None = None
    tamanho_bytes: int | None = None
    mensagem: str = ""
    ignorado: bool = False


@dataclass(frozen=True)
class ResultadoRestauracao:
    caminho: Path
    backup_seguranca: Path


class ErroBackup(RuntimeError):
    pass


def diretorio_backup():
    return Path(settings.SCLME_BACKUP_DIR)


def fazer_backup(*, force=False, database_alias="default", origem=BackupTentativa.Origem.COMANDO):
    agora = timezone.localtime()
    dia = agora.date()
    diretorio = diretorio_backup()
    caminho_previsto = diretorio / _nome_arquivo(agora)
    conexao = connections[database_alias]

    if conexao.vendor != "sqlite":
        return _registrar_erro(
            dia,
            origem,
            force,
            caminho_previsto,
            "Backup para PostgreSQL não suportado ainda.",
        )

    if not force:
        try:
            existentes = _backups_do_dia(dia, diretorio)
            if existentes:
                return ResultadoBackup(
                    True,
                    existentes[-1],
                    existentes[-1].stat().st_size,
                    "Já existe uma cópia deste dia.",
                    ignorado=True,
                )
        except OSError as erro:
            return _registrar_erro(dia, origem, force, caminho_previsto, str(erro))

    try:
        diretorio.mkdir(parents=True, exist_ok=True)
        lock_path = diretorio / f".sclme_{dia.isoformat()}.lock"
        lock_fd = _adquirir_lock(lock_path)
        if lock_fd is None:
            return ResultadoBackup(
                True, mensagem="Outra execução está fazendo o backup deste dia.", ignorado=True
            )
    except Exception as erro:
        return _registrar_erro(dia, origem, force, caminho_previsto, str(erro))

    tentativa = None
    temporario = None
    caminho = diretorio / _nome_arquivo(timezone.localtime())
    try:
        if not force:
            existentes = _backups_do_dia(dia, diretorio)
            if existentes:
                return ResultadoBackup(
                    True,
                    existentes[-1],
                    existentes[-1].stat().st_size,
                    "Já existe uma cópia deste dia.",
                    ignorado=True,
                )

        tentativa = BackupTentativa.objects.create(
            data_backup=dia,
            status=BackupTentativa.Status.EM_ANDAMENTO,
            origem=origem,
            forcado=force,
            caminho=str(caminho),
        )
        conexao.ensure_connection()
        if conexao.connection is None:
            raise ErroBackup("O Django não abriu a conexão SQLite do banco.")

        temporario = diretorio / f".{caminho.name}.{uuid.uuid4().hex}.part"
        with closing(sqlite3.connect(str(temporario))) as destino:
            conexao.connection.backup(destino)
        os.replace(temporario, caminho)
        tamanho = caminho.stat().st_size
        mensagem = _limpar_antigos(diretorio)
        tentativa.status = BackupTentativa.Status.SUCESSO
        tentativa.tamanho_bytes = tamanho
        tentativa.mensagem = mensagem
        tentativa.save(update_fields=("status", "tamanho_bytes", "mensagem"))
        return ResultadoBackup(True, caminho, tamanho, mensagem)
    except Exception as erro:
        mensagem = str(erro) or erro.__class__.__name__
        if temporario is not None:
            try:
                temporario.unlink(missing_ok=True)
            except OSError:
                pass
        if tentativa is not None:
            try:
                tentativa.status = BackupTentativa.Status.ERRO
                tentativa.mensagem = mensagem
                tentativa.save(update_fields=("status", "mensagem"))
            except Exception as erro_log:
                mensagem = f"{mensagem}; não foi possível registrar o resultado: {erro_log}"
            return ResultadoBackup(False, caminho, None, mensagem)
        return _registrar_erro(dia, origem, force, caminho, mensagem)
    finally:
        try:
            os.close(lock_fd)
        except OSError:
            pass
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass


def listar_backups():
    diretorio = diretorio_backup()
    try:
        if not diretorio.is_dir():
            return []
        caminhos = sorted(
            (item for item in diretorio.glob("sclme_*.sqlite3") if _NOME_BACKUP.match(item.name)),
            reverse=True,
        )
    except OSError:
        return []
    tentativas = {}
    for tentativa in BackupTentativa.objects.filter(
        caminho__in=[str(item) for item in caminhos]
    ).order_by("-criada_em", "-pk"):
        tentativas.setdefault(tentativa.caminho, tentativa)
    resultado = []
    for caminho in caminhos:
        try:
            correspondencia = _NOME_BACKUP.match(caminho.name)
            tentativa = tentativas.get(str(caminho))
            stat = caminho.stat()
        except OSError:
            continue
        resultado.append(
            {
                "arquivo": caminho.name,
                "data": date.fromisoformat(correspondencia.group(1)),
                "modificado_em": datetime.fromtimestamp(stat.st_mtime, tz=timezone.get_current_timezone()),
                "tamanho_bytes": stat.st_size,
                "status": tentativa.get_status_display() if tentativa else "Arquivo encontrado",
                "mensagem": tentativa.mensagem if tentativa else "",
            }
        )
    return resultado


def alerta_backup_para_usuario(usuario):
    if not usuario.is_authenticated:
        return None
    disparar_backup_preguicoso()
    if not (usuario.is_staff or usuario.is_superuser):
        return None

    ultima = BackupTentativa.objects.order_by("-criada_em", "-pk").first()
    if ultima and ultima.status == BackupTentativa.Status.ERRO:
        return {
            "mensagem": f"A última tentativa falhou: {ultima.mensagem or 'consulte o registro de backups.'}"
        }

    ultimo_sucesso = BackupTentativa.objects.filter(
        status=BackupTentativa.Status.SUCESSO
    ).order_by("-criada_em", "-pk").first()
    hoje = timezone.localdate()
    if ultimo_sucesso is None:
        return {"mensagem": "Ainda não há uma cópia de segurança concluída."}
    if (hoje - ultimo_sucesso.data_backup).days > 2:
        return {
            "mensagem": f"A cópia mais recente é de {ultimo_sucesso.data_backup:%d/%m/%Y}, há mais de 2 dias."
        }
    return None


def disparar_backup_preguicoso():
    global _ultimo_disparo_preguicoso
    hoje = timezone.localdate()
    with _disparo_lock:
        if _ultimo_disparo_preguicoso == hoje:
            return False
        _ultimo_disparo_preguicoso = hoje

    def executar():
        close_old_connections()
        try:
            fazer_backup(origem=BackupTentativa.Origem.PREGUICOSO)
        finally:
            close_old_connections()

    try:
        threading.Thread(target=executar, name="sclme-backup-diario", daemon=True).start()
    except RuntimeError:
        with _disparo_lock:
            _ultimo_disparo_preguicoso = None
        return False
    return True


def restaurar_backup(arquivo, confirmar_data, *, database_alias="default"):
    correspondencia = _NOME_BACKUP.match(Path(arquivo).name)
    if not correspondencia or Path(arquivo).name != str(arquivo):
        raise ErroBackup("Informe somente o nome de um arquivo de backup válido.")
    data_arquivo = date.fromisoformat(correspondencia.group(1))
    if str(confirmar_data) != data_arquivo.isoformat():
        raise ErroBackup(f"Confirmação incorreta: digite {data_arquivo.isoformat()}.")

    caminho_backup = diretorio_backup() / Path(arquivo).name
    if not caminho_backup.is_file():
        raise ErroBackup("O arquivo de backup não foi encontrado na pasta configurada.")
    _validar_sqlite(caminho_backup)

    conexao = connections[database_alias]
    if conexao.vendor != "sqlite":
        raise ErroBackup("Restauração para PostgreSQL não suportada ainda.")
    nome_banco = conexao.settings_dict["NAME"]
    if str(nome_banco) == ":memory:":
        raise ErroBackup("Não é possível restaurar um banco SQLite em memória.")

    copia_atual = fazer_backup(
        force=True,
        database_alias=database_alias,
        origem=BackupTentativa.Origem.RESTAURACAO,
    )
    if not copia_atual.sucesso or not copia_atual.caminho:
        raise ErroBackup(f"Restauração cancelada: não foi possível copiar o estado atual. {copia_atual.mensagem}")

    conexao.close()
    try:
        with closing(sqlite3.connect(str(caminho_backup))) as fonte, closing(sqlite3.connect(str(nome_banco))) as destino:
            fonte.backup(destino)
            verificacao = destino.execute("PRAGMA integrity_check").fetchone()[0]
            if verificacao != "ok":
                raise ErroBackup(f"A verificação após restaurar retornou: {verificacao}")
    finally:
        conexao.close()
    return ResultadoRestauracao(caminho_backup, copia_atual.caminho)


def caminho_de_backup(arquivo):
    if Path(arquivo).name != str(arquivo) or not _NOME_BACKUP.match(str(arquivo)):
        return None
    caminho = diretorio_backup() / str(arquivo)
    return caminho if caminho.is_file() else None


def _registrar_erro(dia, origem, force, caminho, mensagem):
    try:
        BackupTentativa.objects.create(
            data_backup=dia,
            status=BackupTentativa.Status.ERRO,
            origem=origem,
            forcado=force,
            caminho=str(caminho),
            mensagem=mensagem,
        )
    except Exception:
        pass
    return ResultadoBackup(False, caminho, None, mensagem)


def _nome_arquivo(agora):
    return agora.strftime("sclme_%Y-%m-%d_%H-%M-%S-%f.sqlite3")


def _backups_do_dia(dia, diretorio):
    if not diretorio.is_dir():
        return []
    prefixo = f"sclme_{dia.isoformat()}_"
    return sorted(
        item for item in diretorio.glob(f"{prefixo}*.sqlite3") if _NOME_BACKUP.match(item.name)
    )


def _adquirir_lock(caminho):
    try:
        return os.open(caminho, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        try:
            idade = datetime.now().timestamp() - caminho.stat().st_mtime
            if idade > timedelta(hours=_IDADE_LOCK_HORAS).total_seconds():
                caminho.unlink()
                return os.open(caminho, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except OSError:
            return None
        return None


def _limpar_antigos(diretorio):
    try:
        backups = sorted(
            (item for item in diretorio.glob("sclme_*.sqlite3") if _NOME_BACKUP.match(item.name)),
            reverse=True,
        )
    except OSError as erro:
        return f"A cópia foi criada, mas não foi possível aplicar a retenção: {erro}"
    falhas = []
    for antigo in backups[_RETENCAO:]:
        try:
            antigo.unlink()
        except OSError as erro:
            falhas.append(f"{antigo.name}: {erro}")
    return "" if not falhas else "Falha ao remover cópia antiga: " + "; ".join(falhas)


def _validar_sqlite(caminho):
    try:
        uri = quote(caminho.resolve().as_posix(), safe="/:")
        with closing(sqlite3.connect(f"file:{uri}?mode=ro", uri=True)) as banco:
            resultado = banco.execute("PRAGMA integrity_check").fetchone()[0]
    except sqlite3.Error as erro:
        raise ErroBackup(f"O arquivo não é um banco SQLite legível: {erro}") from erro
    if resultado != "ok":
        raise ErroBackup(f"O banco do backup não passou na verificação de integridade: {resultado}")
