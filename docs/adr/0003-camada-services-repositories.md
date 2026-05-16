# ADR 0003: Camada de Services e Repositories

Data: 2026-05-16

Status: Aceita

## Contexto

A analise arquitetural mostrou que o SCLME possui SQL direto em `main.py` e em paginas Streamlit. Algumas paginas tambem acumulam responsabilidades de controller, service e repository.

Essa estrutura foi aceitavel para acelerar o MVP, mas cria risco para crescimento e migracao futura.

## Decisao

Criar camada explicita de services e repositories antes de novas features grandes.

## Objetivos

- remover SQL direto das paginas;
- reduzir dependencia de Streamlit;
- preparar troca futura de banco/interface;
- organizar regra de negocio;
- melhorar testabilidade;
- reduzir risco de migracao para Django ou outra stack.

## Diretrizes

- `pages/` devem apenas capturar input e exibir output.
- Services concentram regras de aplicacao e orquestracao.
- Repositories concentram acesso ao banco.
- `core` nao deve depender de Streamlit.
- Pandas deve continuar em importacao/exportacao, mas nao como contrato universal de dominio.
- Refatoracoes devem preservar comportamento atual.
- Cada extracao deve ser pequena, testavel e reversivel.

## Ordem Recomendada de Refatoracao

1. `ContratosRepository`;
2. `ImportacoesRepository`;
3. `DocumentosRepository`;
4. `RevisoesRepository`;
5. `DocumentoService`;
6. `CadastroService`;
7. `DashboardService`;
8. `ArquivosService`;
9. separacao de `core/auth` puro e `app/auth` UI;
10. remocao gradual de `sys.path.insert`.

## Responsabilidades Esperadas

### Repositories

Repositories devem encapsular queries e comandos SQL.

Exemplos:

- listar contratos;
- criar contrato;
- buscar documento;
- listar revisoes;
- buscar ultima importacao;
- listar arquivos;
- listar GRDs;
- salvar revisao.

### Services

Services devem orquestrar casos de uso.

Exemplos:

- preparar dados do dashboard;
- montar detalhe de documento;
- validar e salvar cadastro manual;
- executar fluxo de importacao;
- preparar comparacao para exibicao/exportacao.

## Consequencias Positivas

- Paginas Streamlit ficam menores.
- Regras ficam mais testaveis.
- SQL fica centralizado.
- Migração futura para Django/PostgreSQL fica mais viavel.
- O dominio fica menos dependente da interface atual.

## Consequencias Negativas

- A refatoracao adiciona camadas.
- O beneficio aparece gradualmente, nao imediatamente.
- Exige disciplina para nao criar services apenas como repasse mecanico.

## Regra de Qualidade

Uma nova camada so deve existir se reduzir acoplamento real, melhorar testabilidade ou concentrar uma responsabilidade clara.

