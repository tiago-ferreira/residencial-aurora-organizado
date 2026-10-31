# Spec Delta

## Purpose

Define o comportamento observável para consulta e autorização de entrada de visitantes no condomínio, assegurando escopo estrito ao apartamento autenticado na sessão e confirmação obrigatória via sistema.

## ADDED Requirements

### Requirement: Consulta de visitantes restrita ao apartamento da sessão
O sistema MUST consultar e retornar apenas os visitantes vinculados ao apartamento associado à sessão atual, nunca expondo autorizações de outros apartamentos.

#### Scenario: Morador consulta os próprios visitantes autorizados
- **WHEN** o morador solicita listar os visitantes autorizados em sua sessão
- **THEN** o sistema utiliza exclusivamente o apartamento fixado na sessão e retorna apenas visitantes daquele apartamento

### Requirement: Autorização de entrada condicionada à confirmação de sistema
Toda solicitação para autorizar visitante MUST gerar confirmação pendente contendo o nome do visitante e a data da visita em `detalhes`, efetivando o registro somente após aprovação explícita na rota de confirmações.

#### Scenario: Fluxo completo de autorização de visitante com aprovação
- **WHEN** o morador do apartamento `101` solicita liberar `Joana Ribeiro` em `2030-04-21` e em seguida aprova a confirmação pendente com `"confirmado": true`
- **THEN** antes da aprovação `GET /apartamentos/101/visitantes` não lista `Joana Ribeiro`, e após a aprovação passa a listar `{"nome": "Joana Ribeiro", "data": "2030-04-21"}`

#### Scenario: Negação da confirmação de visitante descarta o registro
- **WHEN** o morador solicita liberar a entrada de um visitante e responde à confirmação pendente com `"confirmado": false`
- **THEN** nenhum registro é adicionado aos visitantes do apartamento da sessão
