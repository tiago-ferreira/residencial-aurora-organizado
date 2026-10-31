# Spec Delta

## Purpose

Define o contrato HTTP REST da API do Residencial Aurora em `http://localhost:8000`, as garantias de idempotência de confirmações, a persistência durável frente a reinícios e a restauração limpa dos dados iniciais do condomínio.

## ADDED Requirements

### Requirement: Criação de sessão vinculada ao apartamento
A rota `POST /sessoes` MUST receber `{"apartamento": "<numero>"}` em JSON, persistir uma nova sessão associada permanentemente àquele apartamento e responder com HTTP `201` contendo `{"session_id": "<id>"}`.

#### Scenario: Criação bem-sucedida de sessão para apartamento
- **WHEN** um cliente envia `POST /sessoes` com payload `{"apartamento": "101"}`
- **THEN** a API responde HTTP `201` com JSON contendo um `session_id` não vazio vinculado ao apartamento `101`

### Requirement: Envio de mensagens e retorno de confirmações pendentes
A rota `POST /sessoes/{session_id}/mensagens` MUST receber `{"texto": "..."}` e responder HTTP `200` com `{"resposta": "...", "confirmacoes_pendentes": [...]}`, listando todas as confirmações pendentes atuais da sessão ou lista vazia quando não houver nenhuma.

#### Scenario: Mensagem com confirmação pendente retorna estrutura contratual
- **WHEN** uma mensagem resulta em ação pendente de confirmação na sessão
- **THEN** a API responde HTTP `200` com `resposta` (string, podendo ser vazia) e `confirmacoes_pendentes` contendo objetos com `id`, `acao` e `detalhes`

### Requirement: Resolução idempotente de confirmações pendentes
A rota `POST /sessoes/{session_id}/confirmacoes` MUST aceitar `{"id": "...", "confirmado": <bool>}` apenas para um `id` atualmente pendente naquela sessão (respondendo HTTP `200` no mesmo formato da rota de mensagens) e MUST rejeitar com HTTP `409` qualquer `id` inexistente, de outra sessão ou já respondido.

#### Scenario: Reenvio de confirmação já respondida retorna 409 sem reexecutar ação
- **WHEN** o cliente envia novamente `POST /sessoes/{session_id}/confirmacoes` com o mesmo `id` de uma confirmação já aprovada anteriormente
- **THEN** a API responde HTTP `409` e nenhuma reserva ou autorização duplicada é executada

#### Scenario: Envio de id de confirmação inexistente retorna 409
- **WHEN** o cliente envia `POST /sessoes/{session_id}/confirmacoes` com `{"id": "id-inexistente", "confirmado": true}`
- **THEN** a API responde HTTP `409` e os dados do apartamento permanecem inalterados

### Requirement: Exposição ordenada dos eventos completos da sessão
A rota `GET /sessoes/{session_id}/eventos` MUST responder HTTP `200` com uma lista JSON contendo todos os eventos gravados na sessão em ordem cronológica, incluindo chamadas e respostas de tools com seu conteúdo completo.

#### Scenario: Listagem de eventos reflete histórico de mensagens e tools
- **WHEN** o cliente chama `GET /sessoes/{session_id}/eventos` após interagir com o assistente
- **THEN** a API responde HTTP `200` com a lista ordenada de todos os eventos registrados na sessão até aquele momento

### Requirement: Tratamento de sessão inexistente com status 404
Todas as rotas que recebem `{session_id}` no caminho (`POST /sessoes/{session_id}/mensagens`, `POST /sessoes/{session_id}/confirmacoes` e `GET /sessoes/{session_id}/eventos`) MUST responder HTTP `404` quando a sessão informada não existir.

#### Scenario: Consulta de eventos para sessão inexistente
- **WHEN** o cliente chama `GET /sessoes/sessao-inexistente/eventos`
- **THEN** a API responde HTTP `404`

### Requirement: Rotas administrativas de verificação de reservas e visitantes
A API MUST expor `GET /apartamentos/{apartamento}/reservas` (retornando lista de `{"codigo", "area", "data"}` ativas) e `GET /apartamentos/{apartamento}/visitantes` (retornando lista de `{"nome", "data"}`), lendo diretamente o armazenamento persistente sem passar pelo modelo e formatando datas como `AAAA-MM-DD`.

#### Scenario: Consulta direta aos dados iniciais do condomínio
- **WHEN** o banco foi inicializado/restaurado e o cliente chama `GET /apartamentos/101/reservas` e `GET /apartamentos/302/visitantes`
- **THEN** ambas respondem HTTP `200` listando respectivamente `RSV-1377` (`quadra`, `2030-03-09`) e `Marina Duarte` (`2030-03-16`)

### Requirement: Persistência de sessões e dados após reinício da API
O sistema MUST persistir sessões, eventos, reservas, cancelamentos e visitantes fora da memória volátil do processo da API para que reiniciar a API preserve integralmente o estado e permita continuar conversas existentes.

#### Scenario: Continuidade de sessão e preservação de dados após reiniciar o processo da API
- **WHEN** a API é encerrada e iniciada novamente sem executar o comando de restauração
- **THEN** `GET /sessoes/{session_id}/eventos` devolve exatamente a mesma quantidade e conteúdo de eventos anteriores, novas mensagens em `{session_id}` respondem HTTP `200` incrementando os eventos e as rotas de verificação mantêm todas as alterações anteriores

### Requirement: Restauração dos dados iniciais sem alterar os arquivos base
O projeto MUST fornecer comando dedicado que restaura reservas e visitantes no banco de dados ao estado exato dos arquivos em `dados/`, mantendo todos os arquivos originais do diretório `dados/` estritamente inalterados.

#### Scenario: Execução do comando de restauração
- **WHEN** o comando de restauração documentado no `README.md` é executado após criações e cancelamentos
- **THEN** as reservas e os visitantes voltam ao estado inicial definido em `dados/reservas.json` e `dados/visitantes.json`, e `git diff dados/` permanece vazio
