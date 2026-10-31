"""Camada de persistência PostgreSQL do Residencial Aurora."""

from aurora.db.engine import (
    create_db_engine,
    dispose_engine,
    get_engine,
    get_session_factory,
)
from aurora.db.models import (
    ApartamentoModel,
    AreaModel,
    ConfirmacaoPendenteModel,
    DomainBase,
    ReservaModel,
    VisitanteModel,
    init_domain_schema,
    reserva_codigo_seq,
)
from aurora.db.repositories import (
    AreaRepository,
    CancelamentoReservaResultado,
    ConfirmacaoRepository,
    CriacaoReservaResultado,
    ReservaRepository,
    VisitanteRepository,
)
from aurora.db.seed import ensure_seeded_if_empty, restore_initial_data

__all__ = [
    "ApartamentoModel",
    "AreaModel",
    "AreaRepository",
    "CancelamentoReservaResultado",
    "ConfirmacaoPendenteModel",
    "ConfirmacaoRepository",
    "CriacaoReservaResultado",
    "DomainBase",
    "ReservaModel",
    "ReservaRepository",
    "VisitanteModel",
    "VisitanteRepository",
    "create_db_engine",
    "dispose_engine",
    "ensure_seeded_if_empty",
    "get_engine",
    "get_session_factory",
    "init_domain_schema",
    "reserva_codigo_seq",
    "restore_initial_data",
]
