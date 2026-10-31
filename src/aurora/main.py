"""Servidor HTTP FastAPI do Assistente Virtual do Residencial Aurora."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from aurora.config import get_settings
from aurora.db import (
    ReservaRepository,
    VisitanteRepository,
    dispose_engine,
    get_engine,
    get_session_factory,
)
from aurora.db.seed import ensure_seeded_if_empty
from aurora.services import (
    ChatService,
    ConfirmationConflictError,
    SessionNotFoundError,
    get_regulamento_index,
)


class CriarSessaoRequest(BaseModel):
    apartamento: str = Field(..., min_length=1)


class CriarSessaoResponse(BaseModel):
    session_id: str


class EnviarMensagemRequest(BaseModel):
    texto: str


class ConfirmacaoPendenteItem(BaseModel):
    id: str
    acao: str
    detalhes: dict[str, Any]


class MensagemOuConfirmacaoResponse(BaseModel):
    resposta: str
    confirmacoes_pendentes: list[ConfirmacaoPendenteItem]


class ResponderConfirmacaoRequest(BaseModel):
    id: str
    confirmado: bool


class ReservaItemResponse(BaseModel):
    codigo: str
    area: str
    data: str


class VisitanteItemResponse(BaseModel):
    nome: str
    data: str


def get_chat_service(request: Request) -> ChatService:
    svc = getattr(request.app.state, "chat_service", None)
    if svc is None:
        svc = ChatService()
        request.app.state.chat_service = svc
    return svc


def create_fastapi_app(chat_service: ChatService | None = None) -> FastAPI:
    """Cria a aplicação FastAPI com lifespan integrado ao PostgreSQL."""
    owns_chat_service = chat_service is None

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
        settings = get_settings()
        await ensure_seeded_if_empty(get_engine(), settings.dados_dir)
        get_regulamento_index()
        app_instance.state.chat_service = (
            chat_service if chat_service is not None else ChatService()
        )
        try:
            yield
        finally:
            if owns_chat_service:
                svc = getattr(app_instance.state, "chat_service", None)
                if svc is not None:
                    await svc.close()
            await dispose_engine()

    fastapi_app = FastAPI(
        title="Residencial Aurora — Assistente Virtual",
        version="0.1.0",
        lifespan=lifespan,
    )

    @fastapi_app.exception_handler(SessionNotFoundError)
    async def _handle_session_not_found(
        _request: Request, exc: SessionNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(exc)},
        )

    @fastapi_app.exception_handler(ConfirmationConflictError)
    async def _handle_confirmation_conflict(
        _request: Request, exc: ConfirmationConflictError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(exc)},
        )

    @fastapi_app.post(
        "/sessoes",
        status_code=status.HTTP_201_CREATED,
        response_model=CriarSessaoResponse,
    )
    async def criar_sessao_endpoint(
        payload: CriarSessaoRequest,
        svc: ChatService = Depends(get_chat_service),
    ) -> CriarSessaoResponse:
        session_id = await svc.criar_sessao(payload.apartamento)
        return CriarSessaoResponse(session_id=session_id)

    @fastapi_app.post(
        "/sessoes/{session_id}/mensagens",
        status_code=status.HTTP_200_OK,
        response_model=MensagemOuConfirmacaoResponse,
    )
    async def enviar_mensagem_endpoint(
        session_id: str,
        payload: EnviarMensagemRequest,
        svc: ChatService = Depends(get_chat_service),
    ) -> MensagemOuConfirmacaoResponse:
        resultado = await svc.enviar_mensagem(session_id, payload.texto)
        return MensagemOuConfirmacaoResponse(**resultado)

    @fastapi_app.post(
        "/sessoes/{session_id}/confirmacoes",
        status_code=status.HTTP_200_OK,
        response_model=MensagemOuConfirmacaoResponse,
    )
    async def responder_confirmacao_endpoint(
        session_id: str,
        payload: ResponderConfirmacaoRequest,
        svc: ChatService = Depends(get_chat_service),
    ) -> MensagemOuConfirmacaoResponse:
        resultado = await svc.responder_confirmacao(
            session_id=session_id,
            confirmacao_id=payload.id,
            confirmado=payload.confirmado,
        )
        return MensagemOuConfirmacaoResponse(**resultado)

    @fastapi_app.get(
        "/sessoes/{session_id}/eventos",
        status_code=status.HTTP_200_OK,
    )
    async def listar_eventos_endpoint(
        session_id: str,
        svc: ChatService = Depends(get_chat_service),
    ) -> list[dict[str, Any]]:
        return await svc.listar_eventos(session_id)

    @fastapi_app.get(
        "/apartamentos/{apartamento}/reservas",
        status_code=status.HTTP_200_OK,
        response_model=list[ReservaItemResponse],
    )
    async def listar_reservas_apartamento_endpoint(
        apartamento: str,
    ) -> list[ReservaItemResponse]:
        session_factory = get_session_factory()
        async with session_factory() as db_session:
            reservas = await ReservaRepository.listar_ativas_por_apartamento(
                db_session, apartamento.strip()
            )
        return [ReservaItemResponse(**item) for item in reservas]

    @fastapi_app.get(
        "/apartamentos/{apartamento}/visitantes",
        status_code=status.HTTP_200_OK,
        response_model=list[VisitanteItemResponse],
    )
    async def listar_visitantes_apartamento_endpoint(
        apartamento: str,
    ) -> list[VisitanteItemResponse]:
        session_factory = get_session_factory()
        async with session_factory() as db_session:
            visitantes = await VisitanteRepository.listar_por_apartamento(
                db_session, apartamento.strip()
            )
        return [VisitanteItemResponse(**item) for item in visitantes]

    return fastapi_app


app = create_fastapi_app()
