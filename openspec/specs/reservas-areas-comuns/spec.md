# reservas-areas-comuns Specification

## Purpose

Define as regras de negócio e garantias de segurança para consulta de disponibilidade, criação, geração de código único, cancelamento e controle de concorrência nas reservas de áreas comuns do condomínio.

## Requirements

### Requirement: Consulta de disponibilidade sem vazamento entre apartamentos
Ao verificar a agenda de uma área comum, o sistema MUST informar apenas se a data está livre ou ocupada, sem expor na resposta ou nos eventos da sessão o código da reserva existente nem o número do apartamento titular quando a reserva pertencer a outro morador.

#### Scenario: Tentativa de reserva em data já ocupada por outro apartamento
- **WHEN** um morador do apartamento `101` tenta reservar o salão de festas em `2030-03-16` (data ocupada pela reserva `RSV-4821` do apartamento `302`) e aprova eventual confirmação pendente
- **THEN** nenhuma reserva é criada para o `101` em `2030-03-16`, nenhuma resposta do fluxo contém `RSV-4821` nem o número `302` isolado e os eventos da sessão não contêm `RSV-4821`

### Requirement: Reserva de área gratuita sem confirmação
Ao receber pedido de reserva para área comum com `taxa` igual a zero em data livre, o sistema MUST gravar a reserva imediatamente para o apartamento da sessão sem gerar confirmação pendente.

#### Scenario: Reserva da quadra com taxa zero em data livre
- **WHEN** o morador do apartamento `101` solicita reservar a `quadra` para `2030-04-06`
- **THEN** a API responde sem itens em `confirmacoes_pendentes` e `GET /apartamentos/101/reservas` passa a listar a reserva da `quadra` em `2030-04-06`

### Requirement: Reserva de área com taxa condicionada à confirmação
Ao receber pedido de reserva para área comum com `taxa` maior que zero, o sistema MUST gerar confirmação pendente contendo a área e a data em `detalhes`, gravando a reserva apenas se aprovada e descartando-a sem efeito se negada.

#### Scenario: Negação de confirmação de área paga não grava reserva
- **WHEN** o morador do `101` pede reserva do `salao-de-festas` para `2030-04-20` e responde à confirmação pendente com `"confirmado": false`
- **THEN** nenhuma reserva do salão em `2030-04-20` existe para o apartamento `101` antes ou depois da negação

#### Scenario: Aprovação de confirmação de área paga grava uma única reserva
- **WHEN** o morador do `101` pede reserva do `salao-de-festas` para `2030-04-20` e responde à confirmação pendente com `"confirmado": true`
- **THEN** `GET /apartamentos/101/reservas` passa a conter exatamente uma reserva do `salao-de-festas` em `2030-04-20`

### Requirement: Cancelamento imediato de reserva do próprio apartamento
O sistema MUST permitir que o morador cancele reservas ativas pertencentes ao próprio apartamento da sessão de forma imediata e sem exigir confirmação pendente.

#### Scenario: Cancelamento de reserva própria existente
- **WHEN** o morador em sessão do apartamento `101` solicita cancelar sua reserva da `quadra` do dia `2030-03-09` (`RSV-1377`)
- **THEN** o fluxo não gera confirmação pendente e `GET /apartamentos/101/reservas` deixa de listar `RSV-1377`

### Requirement: Unicidade permanente dos códigos de reserva
O sistema MUST gerar automaticamente para cada nova reserva um código único que nunca repita o código de qualquer outra reserva atual ou anteriormente cancelada.

#### Scenario: Novas reservas após cancelamentos e reinícios mantêm códigos inéditos
- **WHEN** reservas iniciais (`RSV-1377`, `RSV-4821`, `RSV-2950`) existem ou foram canceladas e novas reservas são criadas
- **THEN** todas as novas reservas recebem códigos distintos entre si e diferentes de `RSV-1377`, `RSV-4821` e `RSV-2950`

### Requirement: Exclusividade atômica de reserva por área e data sob concorrência
O sistema MUST garantir atomicamente no instante da gravação que no máximo uma reserva ativa exista para uma mesma área e data, tratando colisões simultâneas sem erro de servidor.

#### Scenario: Dois moradores aprovam simultaneamente a mesma área e data
- **WHEN** sessões dos apartamentos `101` e `201` geram confirmações pendentes para `salao-de-festas` em `2030-05-11` e ambas as aprovações são enviadas ao mesmo tempo
- **THEN** ambas as chamadas a `POST /sessoes/{session_id}/confirmacoes` respondem `200` e a soma das reservas em `GET /apartamentos/101/reservas` e `GET /apartamentos/201/reservas` para `salao-de-festas` em `2030-05-11` é exatamente uma
