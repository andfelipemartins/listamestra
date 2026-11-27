# Plataforma Django

Fundação web da Lista Mestra, em paralelo à aplicação Streamlit.

## SQLite (desenvolvimento)

Na raiz do repositório, use o Python do ambiente virtual:

```powershell
cd plataforma
..\.venv\Scripts\python.exe manage.py migrate
..\.venv\Scripts\python.exe manage.py createsuperuser
..\.venv\Scripts\python.exe manage.py runserver
```

A aplicação fica em `http://127.0.0.1:8000`. O SQLite é criado em `plataforma/dev.sqlite3`.

## PostgreSQL 16 (desenvolvimento)

Com Docker instalado:

```powershell
cd plataforma
docker compose up -d db
$env:DATABASE_URL = "postgres://sclme:sclme-dev@localhost:5432/sclme"
..\.venv\Scripts\python.exe manage.py migrate
..\.venv\Scripts\python.exe manage.py createsuperuser
..\.venv\Scripts\python.exe manage.py runserver
```

Configure `SCLME_SECRET_KEY`, `SCLME_DEBUG=False` e `SCLME_ALLOWED_HOSTS` no ambiente antes de qualquer deploy.
Sem `SCLME_SECRET_KEY`, a configuração em modo de desenvolvimento emite um aviso e usa uma
chave local de desenvolvimento.


## Guia de uso

Consulte o [Guia de uso da Plataforma](../docs/GUIA_DE_USO.md) para conhecer as telas e os acessos.