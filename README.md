# SCLME

Plataforma de controle documental de engenharia para organizar contratos, documentos, emissões, análises e pendências. Cada contrato pode ter um **perfil configurável**, que define sua estrutura de códigos, valores e regras documentais.

## Plataforma em desenvolvimento

A aplicação em evolução fica em `plataforma/` e usa Django com HTMX. O SQLite é o banco padrão para desenvolvimento; PostgreSQL é uma opção via `plataforma/docker-compose.yml`.

### Iniciar localmente

Com o ambiente Python e as dependências preparados, execute na raiz do repositório:

```powershell
cd plataforma
..\.venv\Scripts\python.exe manage.py migrate
..\.venv\Scripts\python.exe manage.py createsuperuser
..\.venv\Scripts\python.exe manage.py runserver
```

A aplicação abre em `http://127.0.0.1:8000`. Para a alternativa PostgreSQL e detalhes de configuração, consulte [plataforma/README.md](plataforma/README.md). Também existe `scripts/ligar_plataforma.ps1`.

### Testes

```powershell
# Na raiz do repositório
pytest tests -q

# Dentro de plataforma/
pytest -q
```

## Mapa do repositório

- `plataforma/` — aplicação Django, configuração, telas, modelos e testes da Plataforma.
- `core/` — regras e utilitários compartilhados com o sistema legado.
- `docs/` — decisões de produto, documentação e [guia de uso](docs/GUIA_DE_USO.md).
- `tests/` — testes da aplicação legada e de regras compartilhadas.
- `scripts/` — comandos auxiliares do projeto.
- `main.py`, `pages/` — entrada e páginas da aplicação Streamlit legada.

## Legado

A aplicação Streamlit (`main.py`, `pages/`, `core/`) continua no repositório. O produto em evolução é a Plataforma Django em `plataforma/`.

Para orientação de navegação e permissões, veja o [Guia de uso da Plataforma](docs/GUIA_DE_USO.md).