import sqlite3
from datetime import timedelta

import pytest
from django.db import connections
from django.urls import reverse
from django.utils import timezone

from backups.models import BackupTentativa
from backups.services import fazer_backup, restaurar_backup


@pytest.fixture
def pasta_backup(settings, tmp_path):
    destino = tmp_path / "backups"
    settings.SCLME_BACKUP_DIR = destino
    return destino


@pytest.mark.django_db(transaction=True)
def test_backup_criado_e_legivel(pasta_backup):
    resultado = fazer_backup()

    assert resultado.sucesso
    assert resultado.caminho.parent == pasta_backup
    assert resultado.caminho.is_file()
    with sqlite3.connect(resultado.caminho) as copia:
        assert copia.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert copia.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='backups_backuptentativa'"
        ).fetchone()
    tentativa = BackupTentativa.objects.get(caminho=str(resultado.caminho))
    assert tentativa.status == BackupTentativa.Status.SUCESSO
    assert tentativa.tamanho_bytes == resultado.caminho.stat().st_size


@pytest.mark.django_db(transaction=True)
def test_retencao_mantem_as_30_copias_mais_recentes(pasta_backup):
    pasta_backup.mkdir()
    agora = timezone.localtime()
    for dias_atras in range(31, 1, -1):
        data = (agora - timedelta(days=dias_atras)).strftime("%Y-%m-%d")
        (pasta_backup / f"sclme_{data}_12-00-00-000000.sqlite3").write_bytes(b"copia antiga")

    resultado = fazer_backup()

    assert resultado.sucesso
    arquivos = list(pasta_backup.glob("sclme_*.sqlite3"))
    assert len(arquivos) == 30
    assert resultado.caminho in arquivos
    assert min(arquivo.name for arquivo in arquivos) > "sclme_" + (agora - timedelta(days=31)).strftime("%Y-%m-%d")


@pytest.mark.django_db(transaction=True)
def test_faz_uma_copia_por_dia_a_menos_que_seja_forcado(pasta_backup):
    primeira = fazer_backup()
    segunda = fazer_backup()

    assert primeira.sucesso and not primeira.ignorado
    assert segunda.sucesso and segunda.ignorado
    assert segunda.caminho == primeira.caminho
    assert len(list(pasta_backup.glob("sclme_*.sqlite3"))) == 1

    forcada = fazer_backup(force=True)
    assert forcada.sucesso and not forcada.ignorado
    assert len(list(pasta_backup.glob("sclme_*.sqlite3"))) == 2


@pytest.mark.django_db(transaction=True)
def test_erro_de_pasta_fica_registrado_e_gera_alerta(pasta_backup, settings, tmp_path, monkeypatch, django_user_model):
    from backups import services

    bloqueio = tmp_path / "arquivo-no-lugar-da-pasta"
    bloqueio.write_text("bloqueio", encoding="utf-8")
    settings.SCLME_BACKUP_DIR = bloqueio / "backups"
    monkeypatch.setattr(services, "disparar_backup_preguicoso", lambda: False)

    resultado = fazer_backup()
    administrador = django_user_model.objects.create_user(
        username="admin-backup", password="senha-segura", is_staff=True
    )
    alerta = services.alerta_backup_para_usuario(administrador)

    assert not resultado.sucesso
    assert BackupTentativa.objects.filter(status=BackupTentativa.Status.ERRO).exists()
    assert "última tentativa falhou" in alerta["mensagem"].lower()


@pytest.mark.django_db(transaction=True)
def test_alerta_quando_a_copia_tem_mais_de_dois_dias(monkeypatch, django_user_model):
    from backups import services

    monkeypatch.setattr(services, "disparar_backup_preguicoso", lambda: False)
    BackupTentativa.objects.create(
        data_backup=timezone.localdate() - timedelta(days=3),
        status=BackupTentativa.Status.SUCESSO,
        origem=BackupTentativa.Origem.COMANDO,
        caminho="copia-antiga.sqlite3",
        tamanho_bytes=100,
    )
    administrador = django_user_model.objects.create_user(
        username="admin-backup-atrasado", password="senha-segura", is_staff=True
    )

    alerta = services.alerta_backup_para_usuario(administrador)

    assert "mais de 2 dias" in alerta["mensagem"]


@pytest.mark.django_db(transaction=True)
def test_tela_de_restauracao_exige_superusuario_e_data_confirmada(
    client, pasta_backup, django_user_model
):
    data = timezone.localdate().isoformat()
    arquivo = f"sclme_{data}_12-00-00-000000.sqlite3"
    pasta_backup.mkdir(exist_ok=True)
    (pasta_backup / arquivo).write_bytes(b"arquivo listado")
    url = reverse("backups:restaurar", args=(arquivo,))
    usuario = django_user_model.objects.create_user(
        username="staff-backup", password="senha-segura", is_staff=True
    )
    client.force_login(usuario)
    assert client.get(url).status_code == 403

    superusuario = django_user_model.objects.create_superuser(
        username="root-backup", password="senha-segura", email="root@example.com"
    )
    client.force_login(superusuario)
    resposta = client.post(url, {"confirmacao": "2000-01-01"})
    assert resposta.status_code == 200
    assert "Digite exatamente" in resposta.content.decode()

    resposta = client.post(url, {"confirmacao": data})
    assert resposta.status_code == 200
    assert "restaurar_backup" in resposta.content.decode()
    assert "Pare o servidor Django" in resposta.content.decode()


@pytest.mark.django_db(transaction=True)
def test_restauracao_copia_o_estado_atual_antes_de_substituir(pasta_backup):
    alias = "backup_restore_test"
    banco_atual = pasta_backup.parent / "estado-atual.sqlite3"
    fonte = pasta_backup / "sclme_2026-01-02_12-00-00-000000.sqlite3"
    pasta_backup.mkdir(exist_ok=True)
    with sqlite3.connect(banco_atual) as banco:
        banco.execute("CREATE TABLE estado (valor TEXT NOT NULL)")
        banco.execute("INSERT INTO estado VALUES ('atual')")
    with sqlite3.connect(fonte) as banco:
        banco.execute("CREATE TABLE estado (valor TEXT NOT NULL)")
        banco.execute("INSERT INTO estado VALUES ('restaurado')")

    configuracao = connections.databases["default"].copy()
    configuracao["NAME"] = str(banco_atual)
    connections.databases[alias] = configuracao
    # O pytest-django bloqueia o primeiro ensure_connection de aliases criados depois do setup.
    connections[alias].connect()
    try:
        resultado = restaurar_backup(fonte.name, "2026-01-02", database_alias=alias)
    finally:
        connections[alias].close()
        connections.databases.pop(alias, None)

    assert resultado.backup_seguranca.is_file()
    with sqlite3.connect(resultado.backup_seguranca) as copia_atual:
        assert copia_atual.execute("SELECT valor FROM estado").fetchone()[0] == "atual"
    with sqlite3.connect(banco_atual) as banco_restaurado:
        assert banco_restaurado.execute("SELECT valor FROM estado").fetchone()[0] == "restaurado"
