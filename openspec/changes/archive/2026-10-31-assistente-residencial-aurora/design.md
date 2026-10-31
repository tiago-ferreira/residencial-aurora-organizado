# Design

## Context

O projeto parte de um repositório greenfield que conterá os arquivos de estado inicial imutáveis em `dados/` (provenientes de `devfullcycle/mba-ia-desafio-criacao-agente`) e deve expor em `http://localhost:8000` uma API REST em Python (`>=3.12`, gerenciada por `uv`) integrando Google ADK (`>=2.2.0,<3.0.0`) e modelos Gemini. Consulte `proposal.md` para a motivação e `specs/` para os contratos comportamentais.

A restrição arquitetural determinante é que as cinco garantias do condomínio precisam ser impostas deterministamente pelo código e pelo banco de dados (PostgreSQL via Docker Compose), nunca apenas por instruções de prompt, resistindo a *prompt injection*, reenvio de confirmações, reinícios de processo e aprovações simultâneas.

## Goals / Non-Goals

**Goals:**
- Garantir que a retomada de confirmações de tools no Google ADK funcione de ponta a ponta com sessão persistida em PostgreSQL, inclusive após reiniciar o processo da API.
- Isolar estruturalmente a identidade do apartamento no `state` da sessão, eliminando parâmetros de apartamento controláveis pelo LLM nas assinaturas das tools.
- Assegurar exclusividade de reservas por `(area, data)` no motor transacional do PostgreSQL e unicidade perpétua de códigos `RSV-*` mesmo para reservas canceladas.
- Manter o consumo de tokens e os eventos da sessão livres de capítulos irrelevantes de `dados/regulamento.md`.

**Non-Goals:**
- Interface gráfica web/mobile, autenticação real via JWT/OAuth ou integração financeira de cobrança.
- Regras de horário por faixa, antecedência mínima/máxima ou validação de datas no passado (explicitamente fora de escopo do desafio).
- Uso de extensões vetoriais pesadas (`pgvector`/embeddings externos) para um documento único estruturado em Markdown (`dados/regulamento.md`).

## Decisions

### 1. Topologia Multiagente com `sub_agents` Nativos e `ResumabilityConfig`
- **Decisão**: Estruturar o `App` do Google ADK com `ResumabilityConfig(is_resumable=True)` contendo um `root_agent` (`morador_orchestrator`) e três especialistas acoplados via `sub_agents`:
  1. `reservas_agent`: consulta disponibilidade, lista reservas do apartamento, cria reservas e cancela reservas próprias.
  2. `visitantes_agent`: lista visitantes do apartamento e solicita autorização de novos visitantes.
  3. `regulamento_agent`: pesquisa e responde dúvidas estritamente com base nas seções pertinentes do regulamento.
- **Racional**: No Google ADK 2.x, encapsular especialistas como `AgentTool` cria sessões internas efêmeras isoladas da sessão principal, quebrando ou silenciando a pausa/retomada de confirmações (`adk_request_confirmation`) quando a sessão é persistida em banco. Usar `sub_agents` nativos sem bloquear transferências indevidas mantém todos os eventos, chamadas de tool e pedidos de confirmação na mesma sessão persistida (`DatabaseSessionService`), permitindo que o `Runner` roteie o `FunctionResponse` da confirmação exatamente ao especialista (`author` / `invocation_id`) que a solicitou.
- **Alternativas consideradas**:
  - *Especialistas via `AgentTool`*: descartado pelo risco elevado de falha silenciosa na retomada de `ToolConfirmation` em banco persistido e ocultação de chamadas internas de tools nos eventos principais da sessão.
  - *Apenas dois especialistas (operacional + regulamento)*: viável, mas separar `reservas_agent` e `visitantes_agent` reduz o conjunto de tools por agente, melhora a precisão de roteamento e deixa as responsabilidades documentadas no `README.md` mais claras.

### 2. Ciclo de Confirmação Híbrido (ADK `ToolConfirmation` + Controle Transacional de Pendências)
- **Decisão**: Usar o mecanismo nativo `tool_context.request_confirmation(...)` / `tool_context.tool_confirmation` do Google ADK combinado com uma tabela `confirmacoes_pendentes` no PostgreSQL sincronizada na camada de serviço da API:
  - Tools gratuitas (`quadra`, `taxa == 0`) e `cancelar_minha_reserva` executam direto sem chamar `request_confirmation`.
  - `criar_reserva` (quando `area.taxa > 0`) e `autorizar_visitante` verificam `tool_context.tool_confirmation`:
    - Se `None`, disparam `tool_context.request_confirmation(hint=..., payload={"acao": ..., "detalhes": ...})` e encerram sem gravar efeito colateral.
    - Se `confirmed == False`, retornam cancelamento amigável sem gravar no banco.
    - Se `confirmed == True`, executam a gravação transacional no PostgreSQL.
  - Ao final de `POST /sessoes/{session_id}/mensagens`, o serviço inspeciona novos eventos `FunctionCall` com `name == "adk_request_confirmation"` e registra cada pendência em `confirmacoes_pendentes` (`id`, `session_id`, `invocation_id`, `acao`, `detalhes`, `status = 'PENDENTE'`).
  - Em `POST /sessoes/{session_id}/confirmacoes`, o serviço executa `UPDATE confirmacoes_pendentes SET status = :novo_status WHERE id = :id AND session_id = :session_id AND status = 'PENDENTE' RETURNING invocation_id`. Se nenhuma linha for afetada, responde imediatamente HTTP `409` sem invocar o `Runner`. Se atualizado, envia o `FunctionResponse` de `adk_request_confirmation` ao `Runner.run_async` informando o `invocation_id` original para retomar o especialista exato.
- **Racional**: Impede que texto do morador ("já confirmei") ative o ramo `confirmed == True` (pois `tool_confirmation` só é preenchido pelo runtime do ADK via `FunctionResponse` de sistema) e garante atomicamente o HTTP `409` em IDs inexistentes, de outra sessão ou reenviados.
- **Alternativas consideradas**:
  - *Rastrear pendências apenas varrendo eventos do ADK em memória*: mais propenso a ambiguidades de estado em reenvios ou após reinício; a tabela auxiliar no mesmo PostgreSQL torna a transição `PENDENTE -> RESPONDIDA` atômica e auditável.

### 3. Isolamento de Apartamento por Injeção de `ToolContext` (Zero Confiança no Modelo)
- **Decisão**: Gravar `{"apartamento": payload.apartamento}` em `session.state` uma única vez em `POST /sessoes`. Nenhuma tool do sistema terá parâmetro `apartamento` em sua assinatura Python; todas extraem `apartamento = tool_context.state["apartamento"]`.
- ** Sanitização de Consultas Compartilhadas**:
  - `consultar_disponibilidade_area(area: str, data: str)` executa apenas `SELECT EXISTS(SELECT 1 FROM reservas WHERE area_id = :area AND data = :data AND ativa = TRUE)`, retornando somente `{"area": area, "data": data, "disponivel": bool}`. Códigos (`RSV-*`) e números de outros apartamentos jamais saem do PostgreSQL.
  - `cancelar_minha_reserva(area: str, data: str)` (ou por código opcional validado) filtra obrigatoriamente `WHERE apartamento = :apartamento_sessao AND ativa = TRUE`, retornando apenas mensagem genérica de não encontrada caso a reserva pertença a terceiro.
- **Racional**: Elimina na raiz a superfície para *prompt injection*: mesmo que o LLM seja convencido de que o morador é do `302`, ele não dispõe de ferramenta capaz de ler ou alterar dados fora do `state["apartamento"]`.

### 4. Persistência Unificada em PostgreSQL (Docker Compose) e Exclusividade no `INSERT`
- **Decisão**: Subir uma instância PostgreSQL 16 via `docker-compose.yml` com volume nomeado persistente, compartilhada entre:
  - `DatabaseSessionService` do Google ADK (tabelas gerenciadas pelo ADK via SQLAlchemy URL).
  - Esquema de domínio da aplicação (`apartamentos`, `areas`, `reservas`, `visitantes`, `confirmacoes_pendentes` e `SEQUENCE reserva_codigo_seq`).
- **Controle de Concorrência e Códigos Únicos**:
  - Tabela `reservas` possui `codigo VARCHAR PRIMARY KEY`, `ativa BOOLEAN NOT NULL DEFAULT TRUE` e índice único parcial:
    `CREATE UNIQUE INDEX uq_reservas_area_data_ativa ON reservas (area_id, data) WHERE ativa = TRUE;`
  - Cancelar uma reserva executa `UPDATE reservas SET ativa = FALSE` (soft-cancel) e novos códigos vêm de `nextval('reserva_codigo_seq')` inicializada acima do maior sufixo numérico de `dados/reservas.json` (ex.: iniciando em `5000` → `RSV-5000`, `RSV-5001`...). Isso garante simultaneamente unicidade perpétua de códigos (inclusive cancelados) e bloqueio atômico no índice único parcial em aprovações concorrentes.
  - Na colisão concorrente (`IntegrityError` / `UniqueViolation`), a tool faz `rollback` da transação de domínio e devolve `{"sucesso": False, "motivo": "data_indisponivel"}` para o especialista responder cordialmente com HTTP `200`.
- **Alternativas consideradas**:
  - *`SELECT` prévio seguido de `INSERT` sem constraint parcial*: vulnerável a *race condition* (TOCTOU) no passo 14 do fluxo do avaliador.
  - *Lock em memória (`asyncio.Lock`)*: funciona apenas em worker único no mesmo processo e não comprova garantia na camada de armazenamento.

### 5. Indexação Seletiva por Seções para `dados/regulamento.md`
- **Decisão**: Fazer o *parse* de `dados/regulamento.md` em seções/capítulos delimitados pelos cabeçalhos Markdown (`#`, `##`, `###`) na inicialização da aplicação (somente leitura). O `regulamento_agent` recebe tools enxutas:
  - `buscar_capitulo_regulamento(consulta: str)`: ranqueia os capítulos/seções por correspondência léxica normalizada (sem acentos, *stemming* simples/tokens de título e corpo) e retorna **exclusivamente** o capítulo/seção pertinente (com limite estrito de `top_k=1` seção mais relevante, ou lista apenas dos títulos das seções caso nenhum termo coincida, permitindo nova chamada pelo identificador da seção).
  - `ler_secao_regulamento(secao_id: str)`: retorna apenas o texto da seção solicitada.
- **Racional**: Nem o `root_agent` nem o `regulamento_agent` trazem o regulamento nas instruções do sistema, e o retorno da tool registrado nos eventos da sessão (`GET /sessoes/{id}/eventos`) conterá somente o capítulo do assunto perguntado (ex.: piscina), jamais trechos de outros capítulos.

### 6. Estrutura do Projeto e CLI de Restauração
- **Decisão**: Organizar o código em pacote Python gerenciado por `uv`:
  - `dados/`: arquivos JSON e Markdown idênticos ao repositório base (`apartamentos.json`, `areas.json`, `reservas.json`, `visitantes.json`, `regulamento.md`).
  - `src/aurora/` (ou `app/`): `main.py` (FastAPI), `config.py` (Pydantic Settings lendo `.env`), `db/` (modelos SQLAlchemy, engine PostgreSQL e repositórios), `agents/` (`root`, `reservas`, `visitantes`, `regulamento`), `tools/` (tools ADK isoladas por domínio), `services/` (execução do `Runner`, extração de eventos e orquestração de confirmações) e `cli.py` (comando de restauração/seed).
  - Na subida da API, se o banco estiver vazio (primeiro boot), carrega automaticamente o seed inicial de `dados/` sem sobrescrever dados já existentes em reinícios subsequentes; o comando explícito de restauração limpa tabelas de domínio (e sessões) e recarrega exatamente o estado de `dados/`.

## Risks / Trade-offs

- **[Risco] Retomada silenciosa de confirmação no ADK com `DatabaseSessionService` em PostgreSQL** → **Mitigação**: Configurar `ResumabilityConfig(is_resumable=True)`, usar `sub_agents` diretos sem `AgentTool`, persistir e reenviar o `invocation_id` exato ao `Runner.run_async`, e validar com teste de integração que aprova confirmação antes e depois de reiniciar o servidor Uvicorn.
- **[Risco] Incompatibilidade de driver assíncrono SQLAlchemy no `DatabaseSessionService` do ADK** → **Mitigação**: Verificar na versão exata fixada do `google-adk` (`>=2.2.0`) o dialeto esperado (`postgresql+asyncpg://` vs `postgresql+psycopg://`) e alinhar dependências no `pyproject.toml`.
- **[Risco] Busca léxica simples no regulamento retornar mais de um capítulo quando termos genéricos aparecem na pergunta** → **Mitigação**: Filtrar *stopwords* em português (ex.: `"ate"`, `"horas"`, `"funciona"`, `"dias"`, `"condominio"`), dar peso maior aos títulos dos capítulos/seções e retornar apenas a seção de maior pontuação (`top_k=1`), expondo `ler_secao_regulamento(secao_id)` como *fallback* preciso por título.
- **[Risco] Numeração do apartamento aparecer acidentalmente em mensagem de erro ou código gerado** → **Mitigação**: Gerar códigos com sequência numérica alta (`RSV-5000+`, fora da faixa de apartamentos `101`–`404`) e nunca selecionar `apartamento` ou `codigo` nas queries de disponibilidade.

## Migration Plan

1. Obter os arquivos originais de `dados/` do repositório base (`devfullcycle/mba-ia-desafio-criacao-agente`) preservando bytes e hashes originais.
2. Subir PostgreSQL via `docker compose up -d`.
3. Instalar dependências fixadas com `uv sync`.
4. Executar o comando de restauração/seed inicial (`uv run aurora-reset` ou equivalente documentado no `README.md`) para criar tabelas, índices e popular dados iniciais.
5. Iniciar a API em `http://localhost:8000` (`uv run uvicorn ...`). Para rollback/reset completo em avaliação, basta reexecutar o comando de restauração.
