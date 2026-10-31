# Proposal

## Why

O aplicativo dos moradores do Residencial Aurora precisa de um assistente conversacional capaz de gerenciar reservas de áreas comuns, autorizar a entrada de visitantes e responder dúvidas sobre o regulamento interno sem permitir que qualquer mensagem (incluindo tentativas de *prompt injection* ou concorrência entre moradores) viole as regras críticas do condomínio. Concentrar regras de negócio apenas em instruções de prompt é frágil; por isso, este projeto implementa o assistente com Google ADK e API HTTP garantindo em código isolamento por apartamento, confirmação explícita para cobrança/acesso, persistência em reinícios, consulta enxuta ao regulamento e exclusividade atômica de reservas.

## What Changes

- Bootstrap do projeto Python (`>=3.12`) gerenciado com `uv` (`pyproject.toml` e `uv.lock`), incorporando os arquivos originais imutáveis de `dados/` do repositório base do desafio, variáveis de ambiente seguras (`.env.example` sem chaves versionadas) e infraestrutura PostgreSQL via Docker Compose.
- Criação da arquitetura multiagente com Google ADK (série 2, versão exata fixada `>=2.2.0`), composta por um agente principal orquestrador e agentes especialistas dedicados (reservas, visitantes e regulamento interno).
- Implementação determinística das cinco garantias de segurança e consistência em código:
  - **Garantia 1 (Confirmação de sistema):** ações que geram cobrança (áreas com `taxa > 0`) ou liberam acesso (autorização de visitantes) ficam pendentes até aprovação explícita em rota dedicada, ignorando confirmações textuais na conversa.
  - **Garantia 2 (Isolamento por apartamento):** vínculo imutável da sessão ao apartamento informado na criação, lido exclusivamente do estado da sessão pelas tools, sem vazamento de códigos de reserva, nomes de visitantes ou números de outros apartamentos na resposta ou nos eventos.
  - **Garantia 3 (Persistência no reinício):** armazenamento durável de sessões/eventos do ADK e dados transacionais do condomínio em PostgreSQL, preservando histórico e estado após reinicialização da API, acompanhado de comando explícito de restauração para o estado inicial de `dados/`.
  - **Garantia 4 (Consulta seletiva ao regulamento):** indexação/busca por capítulos ou seções de `dados/regulamento.md` sob demanda via tool, mantendo o regulamento fora das instruções do agente principal e impedindo que capítulos não relacionados entrem nos eventos da sessão.
  - **Garantia 5 (Exclusividade concorrente de reservas):** controle atômico no banco de dados (PostgreSQL) no instante da gravação para impedir reservas duplicadas de mesma área e data em aprovações simultâneas, retornando resposta HTTP `200` normal para ambos os moradores.
- Exposição da API HTTP em `http://localhost:8000` (FastAPI) seguindo integralmente o contrato de rotas de sessão, mensagens, confirmações, eventos e rotas administrativas de verificação.
- Substituição/entrega do `README.md` na raiz contendo as seções obrigatórias **Arquitetura**, **Garantias** (apontando arquivos e trechos reais do código) e **Como rodar**.

## Capabilities

### New Capabilities
- `orquestracao-agentes`: Topologia multiagente no Google ADK (agente principal e especialistas), isolamento de identidade do apartamento via estado da sessão e fluxo de pausa/retomada para confirmações pendentes de tools.
- `reservas-areas-comuns`: Regras e tools de consulta de disponibilidade, criação de reservas (gratuitas diretas e pagas sob confirmação), geração de códigos únicos irrepetíveis, cancelamento sem confirmação das próprias reservas e exclusividade atômica sob concorrência.
- `autorizacao-visitantes`: Regras e tools de listagem e autorização de entrada de visitantes vinculadas ao apartamento da sessão, com exigência obrigatória de confirmação via rota de sistema.
- `consulta-regulamento`: Consulta estruturada e seletiva ao arquivo `dados/regulamento.md` restrita aos capítulos pertinentes à dúvida do morador, sem carregar o documento integral no prompt ou nos eventos da sessão.
- `api-sessoes-persistencia`: Contrato HTTP REST em `http://localhost:8000`, persistência durável de sessões ADK e dados do condomínio em PostgreSQL (Docker Compose), preservação pós-reinício e utilitário CLI de restauração do estado inicial a partir de `dados/`.

### Modified Capabilities
<!-- Nenhuma capability existente está sendo modificada (projeto greenfield). -->

## Impact

- **Código e Estrutura**: Criação da aplicação Python (camadas de API FastAPI, runtime/agentes/tools Google ADK, repositórios PostgreSQL e CLI de seed/reset), arquivos `dados/` sincronizados do repositório base (`devfullcycle/mba-ia-desafio-criacao-agente`), `docker-compose.yml`, `.env.example`, `.gitignore` e `README.md`.
- **APIs Expostas**: `POST /sessoes`, `POST /sessoes/{session_id}/mensagens`, `POST /sessoes/{session_id}/confirmacoes`, `GET /sessoes/{session_id}/eventos`, `GET /apartamentos/{apartamento}/reservas` e `GET /apartamentos/{apartamento}/visitantes`.
- **Dependências e Sistemas**: Python `>=3.12`, `uv`, `google-adk` (versão exata `>=2.2.0,<3.0.0`), `fastapi`, `uvicorn`, driver/ORM PostgreSQL (`sqlalchemy`, `asyncpg`/`psycopg`), PostgreSQL em container Docker e Google AI Studio API (`GEMINI_API_KEY` / `GOOGLE_API_KEY`).
