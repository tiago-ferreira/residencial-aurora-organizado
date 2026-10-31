# Spec Delta

## Purpose

Define como o assistente consulta o regulamento interno do Residencial Aurora para responder dúvidas dos moradores com precisão e economia de contexto, evitando carregar capítulos irrelevantes nas instruções ou nos eventos da sessão.

## ADDED Requirements

### Requirement: Resposta baseada no regulamento interno
O assistente MUST responder às dúvidas sobre normas, horários e regras de convivência com base nas informações oficiais contidas em `dados/regulamento.md`.

#### Scenario: Dúvida sobre horário de funcionamento da piscina aos domingos
- **WHEN** o morador pergunta `"Até que horas a piscina funciona aos domingos?"`
- **THEN** a resposta informa o horário exato de fechamento aos domingos estabelecido em `dados/regulamento.md`

### Requirement: Consulta seletiva sem carregar capítulos não relacionados
O agente principal MUST NOT receber o texto do regulamento em suas instruções, e as consultas realizadas MUST retornar apenas os trechos ou capítulos pertinentes ao assunto perguntado, sem registrar capítulos alheios nos eventos da sessão.

#### Scenario: Verificação de ausência de capítulos irrelevantes nos eventos da sessão
- **WHEN** o morador faz uma pergunta específica sobre o horário da piscina e `GET /sessoes/{session_id}/eventos` é inspecionado
- **THEN** os eventos da sessão contêm apenas o trecho/capítulo pertinente à consulta e nenhum evento contém trechos de capítulos de `dados/regulamento.md` que tratam de outros assuntos
