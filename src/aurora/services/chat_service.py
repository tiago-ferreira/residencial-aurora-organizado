"""Orquestrador de sessões, execução do Runner ADK e confirmações persistidas (Garantias 1, 2 e 3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from google.adk.apps.app import App
from google.adk.events.event import Event
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, Session
from google.adk.utils._function_call_names import (
    REQUEST_CONFIRMATION_FUNCTION_CALL_NAME,
)
from google.genai import types

from aurora.db import ConfirmacaoRepository, get_session_factory

DEFAULT_USER_ID = "morador"


class SessionNotFoundError(Exception):
    """Exceção disparada quando o session_id informado não existe."""


class ConfirmationConflictError(Exception):
    """Exceção disparada quando o id de confirmação não está pendente na sessão (409)."""


@dataclass(frozen=True, slots=True)
class _ExtractedConfirmation:
    confirmacao_id: str
    invocation_id: str
    acao: str
    detalhes: dict[str, Any]
    hint: str


def _extract_event_text(event: Event) -> str:
    if event.partial or event.author == "user" or not event.content or not event.content.parts:
        return ""
    texts = [part.text.strip() for part in event.content.parts if part.text and part.text.strip()]
    return "\n".join(texts).strip()


def _extract_confirmations_from_event(event: Event) -> list[_ExtractedConfirmation]:
    extracted: list[_ExtractedConfirmation] = []
    for fc in event.get_function_calls():
        if fc.name != REQUEST_CONFIRMATION_FUNCTION_CALL_NAME or not fc.id:
            continue
        args = fc.args if isinstance(fc.args, dict) else {}
        tool_conf = args.get("toolConfirmation")
        tool_conf_dict = tool_conf if isinstance(tool_conf, dict) else {}
        orig_fc = args.get("originalFunctionCall")
        orig_fc_dict = orig_fc if isinstance(orig_fc, dict) else {}

        payload = tool_conf_dict.get("payload")
        payload_dict = payload if isinstance(payload, dict) else {}

        acao = str(
            payload_dict.get("acao")
            or orig_fc_dict.get("name")
            or "confirmar_acao"
        )
        raw_detalhes = payload_dict.get("detalhes")
        if isinstance(raw_detalhes, dict):
            detalhes = dict(raw_detalhes)
        else:
            orig_args = orig_fc_dict.get("args")
            detalhes = dict(orig_args) if isinstance(orig_args, dict) else {}

        hint = str(tool_conf_dict.get("hint") or "").strip()
        extracted.append(
            _ExtractedConfirmation(
                confirmacao_id=fc.id,
                invocation_id=event.invocation_id,
                acao=acao,
                detalhes=detalhes,
                hint=hint,
            )
        )
    return extracted


class ChatService:
    """Serviço de conversação e retomada de confirmações sobre DatabaseSessionService."""

    def __init__(
        self,
        *,
        app: App | None = None,
        session_service: BaseSessionService | None = None,
        runner: Runner | None = None,
    ) -> None:
        from aurora.agents import aurora_app, create_runner, create_session_service

        self.app = app or aurora_app
        self.session_service = session_service or create_session_service()
        self.runner = runner or create_runner(
            session_service=self.session_service,
            app=self.app,
        )

    async def close(self) -> None:
        """Fecha conexões do serviço de sessão quando aplicável."""
        close_fn = getattr(self.session_service, "close", None)
        if callable(close_fn):
            await close_fn()

    async def criar_sessao(self, apartamento: str) -> str:
        """Cria uma nova sessão persistida vinculada permanentemente ao apartamento."""
        apt = str(apartamento).strip()
        session = await self.session_service.create_session(
            app_name=self.app.name,
            user_id=DEFAULT_USER_ID,
            state={"apartamento": apt},
        )
        return session.id

    async def _obter_sessao_obrigatoria(self, session_id: str) -> Session:
        session = await self.session_service.get_session(
            app_name=self.app.name,
            user_id=DEFAULT_USER_ID,
            session_id=session_id,
        )
        if session is None:
            raise SessionNotFoundError(f"Sessão '{session_id}' não encontrada.")
        return session

    async def _executar_turno(
        self,
        *,
        session_id: str,
        apartamento: str,
        new_message: types.Content,
        invocation_id: str | None = None,
    ) -> dict[str, Any]:
        last_agent_text = ""
        novas_confirmacoes: list[_ExtractedConfirmation] = []

        async for event in self.runner.run_async(
            user_id=DEFAULT_USER_ID,
            session_id=session_id,
            invocation_id=invocation_id,
            new_message=new_message,
        ):
            texto_evento = _extract_event_text(event)
            if texto_evento:
                last_agent_text = texto_evento
            novas_confirmacoes.extend(_extract_confirmations_from_event(event))

        session_factory = get_session_factory()
        async with session_factory() as db_session:
            for item in novas_confirmacoes:
                await ConfirmacaoRepository.registrar_pendente(
                    db_session,
                    confirmacao_id=item.confirmacao_id,
                    session_id=session_id,
                    apartamento=apartamento,
                    invocation_id=item.invocation_id,
                    acao=item.acao,
                    detalhes=item.detalhes,
                )
            pendentes = await ConfirmacaoRepository.listar_pendentes_da_sessao(
                db_session, session_id
            )

        resposta = last_agent_text
        if not resposta and novas_confirmacoes:
            resposta = novas_confirmacoes[-1].hint

        return {
            "resposta": resposta,
            "confirmacoes_pendentes": pendentes,
        }

    async def enviar_mensagem(self, session_id: str, texto: str) -> dict[str, Any]:
        """Envia mensagem de texto do morador na sessão e retorna resposta + confirmações pendentes."""
        session = await self._obter_sessao_obrigatoria(session_id)
        apartamento = str(session.state.get("apartamento", "")).strip()
        new_message = types.Content(
            role="user",
            parts=[types.Part.from_text(text=texto)],
        )
        return await self._executar_turno(
            session_id=session_id,
            apartamento=apartamento,
            new_message=new_message,
            invocation_id=None,
        )

    async def responder_confirmacao(
        self,
        session_id: str,
        confirmacao_id: str,
        confirmado: bool,
    ) -> dict[str, Any]:
        """Consome confirmação pendente de forma atômica e retoma a invocação pausada no ADK."""
        session = await self._obter_sessao_obrigatoria(session_id)
        apartamento = str(session.state.get("apartamento", "")).strip()

        session_factory = get_session_factory()
        async with session_factory() as db_session:
            consumida = await ConfirmacaoRepository.consumir_pendente(
                db_session,
                session_id=session_id,
                confirmacao_id=confirmacao_id,
                confirmado=confirmado,
            )

        if consumida is None:
            raise ConfirmationConflictError(
                f"Confirmação '{confirmacao_id}' não está pendente nesta sessão."
            )

        confirmation_message = types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        id=confirmacao_id,
                        name=REQUEST_CONFIRMATION_FUNCTION_CALL_NAME,
                        response={"confirmed": bool(confirmado)},
                    )
                )
            ],
        )
        return await self._executar_turno(
            session_id=session_id,
            apartamento=apartamento,
            new_message=confirmation_message,
            invocation_id=consumida.invocation_id,
        )

    async def listar_eventos(self, session_id: str) -> list[dict[str, Any]]:
        """Retorna todos os eventos completos gravados na sessão em ordem cronológica."""
        session = await self._obter_sessao_obrigatoria(session_id)
        return [
            event.model_dump(mode="json", exclude_none=True)
            for event in session.events
        ]
