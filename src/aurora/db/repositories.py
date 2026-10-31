"""Repositórios transacionais PostgreSQL para reservas, visitantes e confirmações."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import exists, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from aurora.db.models import (
    AreaModel,
    ConfirmacaoPendenteModel,
    ReservaModel,
    VisitanteModel,
    reserva_codigo_seq,
)


@dataclass(frozen=True, slots=True)
class CriacaoReservaResultado:
    """Resultado determinístico da tentativa de gravação de uma reserva."""

    sucesso: bool
    codigo: str | None = None
    area: str | None = None
    data: str | None = None
    motivo: str | None = None


@dataclass(frozen=True, slots=True)
class CancelamentoReservaResultado:
    """Resultado determinístico do cancelamento de reserva própria."""

    sucesso: bool
    codigo: str | None = None
    area: str | None = None
    data: str | None = None
    motivo: str | None = None


class AreaRepository:
    """Consultas às áreas comuns do condomínio."""

    @staticmethod
    async def listar_areas(session: AsyncSession) -> list[dict[str, Any]]:
        stmt = select(AreaModel).order_by(AreaModel.id.asc())
        rows = (await session.scalars(stmt)).all()
        return [
            {"id": area.id, "nome": area.nome, "taxa": float(area.taxa)}
            for area in rows
        ]

    @staticmethod
    async def obter_area(
        session: AsyncSession, area_id: str
    ) -> AreaModel | None:
        return await session.get(AreaModel, area_id)


class ReservaRepository:
    """Operações atômicas e isoladas por apartamento para reservas."""

    @staticmethod
    async def verificar_disponibilidade(
        session: AsyncSession, area_id: str, data_reserva: date
    ) -> bool:
        """Retorna True se a área está livre na data, sem carregar codigo ou apartamento."""
        ocupada_stmt = select(
            exists(
                select(1).where(
                    ReservaModel.area_id == area_id,
                    ReservaModel.data == data_reserva,
                    ReservaModel.ativa.is_(True),
                )
            )
        )
        ocupada = bool(await session.scalar(ocupada_stmt))
        return not ocupada

    @staticmethod
    async def listar_ativas_por_apartamento(
        session: AsyncSession, apartamento: str
    ) -> list[dict[str, str]]:
        """Lista apenas reservas ativas pertencentes ao apartamento informado."""
        stmt = (
            select(
                ReservaModel.codigo,
                ReservaModel.area_id,
                ReservaModel.data,
            )
            .where(
                ReservaModel.apartamento == apartamento,
                ReservaModel.ativa.is_(True),
            )
            .order_by(ReservaModel.data.asc(), ReservaModel.codigo.asc())
        )
        rows = (await session.execute(stmt)).all()
        return [
            {
                "codigo": row.codigo,
                "area": row.area_id,
                "data": row.data.isoformat(),
            }
            for row in rows
        ]

    @staticmethod
    async def criar_atomica(
        session: AsyncSession,
        *,
        apartamento: str,
        area_id: str,
        data_reserva: date,
    ) -> CriacaoReservaResultado:
        """Grava reserva com código sequencial inédito e exclusividade no INSERT."""
        area = await AreaRepository.obter_area(session, area_id)
        if area is None:
            return CriacaoReservaResultado(
                sucesso=False,
                motivo="area_inexistente",
            )

        seq_num = await session.scalar(select(reserva_codigo_seq.next_value()))
        codigo = f"RSV-{seq_num}"

        nova_reserva = ReservaModel(
            codigo=codigo,
            apartamento=apartamento,
            area_id=area_id,
            data=data_reserva,
            ativa=True,
        )
        session.add(nova_reserva)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return CriacaoReservaResultado(
                sucesso=False,
                area=area_id,
                data=data_reserva.isoformat(),
                motivo="data_indisponivel",
            )

        return CriacaoReservaResultado(
            sucesso=True,
            codigo=codigo,
            area=area_id,
            data=data_reserva.isoformat(),
        )

    @staticmethod
    async def cancelar_do_apartamento(
        session: AsyncSession,
        *,
        apartamento: str,
        area_id: str | None = None,
        data_reserva: date | None = None,
        codigo: str | None = None,
    ) -> CancelamentoReservaResultado:
        """Cancela reserva ativa exclusivamente se pertencer ao apartamento da sessão."""
        if not codigo and not (area_id and data_reserva):
            return CancelamentoReservaResultado(
                sucesso=False,
                motivo="criterio_insuficiente",
            )

        conditions = [
            ReservaModel.apartamento == apartamento,
            ReservaModel.ativa.is_(True),
        ]
        if codigo:
            conditions.append(ReservaModel.codigo == codigo)
        if area_id:
            conditions.append(ReservaModel.area_id == area_id)
        if data_reserva:
            conditions.append(ReservaModel.data == data_reserva)

        stmt = (
            update(ReservaModel)
            .where(*conditions)
            .values(ativa=False)
            .returning(
                ReservaModel.codigo,
                ReservaModel.area_id,
                ReservaModel.data,
            )
        )
        row = (await session.execute(stmt)).first()
        if row is None:
            await session.rollback()
            return CancelamentoReservaResultado(
                sucesso=False,
                motivo="reserva_nao_encontrada",
            )

        await session.commit()
        return CancelamentoReservaResultado(
            sucesso=True,
            codigo=row.codigo,
            area=row.area_id,
            data=row.data.isoformat(),
        )


class VisitanteRepository:
    """Operações de leitura e autorização de visitantes por apartamento."""

    @staticmethod
    async def listar_por_apartamento(
        session: AsyncSession, apartamento: str
    ) -> list[dict[str, str]]:
        stmt = (
            select(VisitanteModel.nome, VisitanteModel.data)
            .where(VisitanteModel.apartamento == apartamento)
            .order_by(VisitanteModel.data.asc(), VisitanteModel.id.asc())
        )
        rows = (await session.execute(stmt)).all()
        return [
            {"nome": row.nome, "data": row.data.isoformat()} for row in rows
        ]

    @staticmethod
    async def autorizar(
        session: AsyncSession,
        *,
        apartamento: str,
        nome: str,
        data_visita: date,
    ) -> dict[str, str]:
        visitante = VisitanteModel(
            apartamento=apartamento,
            nome=nome.strip(),
            data=data_visita,
        )
        session.add(visitante)
        await session.commit()
        return {"nome": visitante.nome, "data": data_visita.isoformat()}


class ConfirmacaoRepository:
    """Controle atômico de confirmações pendentes por sessão."""

    @staticmethod
    async def registrar_pendente(
        session: AsyncSession,
        *,
        confirmacao_id: str,
        session_id: str,
        apartamento: str,
        invocation_id: str,
        acao: str,
        detalhes: dict[str, Any],
    ) -> None:
        existente = await session.get(ConfirmacaoPendenteModel, confirmacao_id)
        if existente is not None:
            return
        registro = ConfirmacaoPendenteModel(
            id=confirmacao_id,
            session_id=session_id,
            apartamento=apartamento,
            invocation_id=invocation_id,
            acao=acao,
            detalhes=detalhes,
            status="PENDENTE",
        )
        session.add(registro)
        await session.commit()

    @staticmethod
    async def listar_pendentes_da_sessao(
        session: AsyncSession, session_id: str
    ) -> list[dict[str, Any]]:
        stmt = (
            select(ConfirmacaoPendenteModel)
            .where(
                ConfirmacaoPendenteModel.session_id == session_id,
                ConfirmacaoPendenteModel.status == "PENDENTE",
            )
            .order_by(ConfirmacaoPendenteModel.created_at.asc())
        )
        rows = (await session.scalars(stmt)).all()
        return [
            {
                "id": item.id,
                "acao": item.acao,
                "detalhes": item.detalhes,
            }
            for item in rows
        ]

    @staticmethod
    async def consumir_pendente(
        session: AsyncSession,
        *,
        session_id: str,
        confirmacao_id: str,
        confirmado: bool,
    ) -> ConfirmacaoPendenteModel | None:
        novo_status = "APROVADA" if confirmado else "NEGADA"
        stmt = (
            update(ConfirmacaoPendenteModel)
            .where(
                ConfirmacaoPendenteModel.id == confirmacao_id,
                ConfirmacaoPendenteModel.session_id == session_id,
                ConfirmacaoPendenteModel.status == "PENDENTE",
            )
            .values(status=novo_status, responded_at=func.now())
            .returning(ConfirmacaoPendenteModel)
        )
        item = (await session.scalars(stmt)).first()
        if item is None:
            await session.rollback()
            return None
        await session.commit()
        return item
