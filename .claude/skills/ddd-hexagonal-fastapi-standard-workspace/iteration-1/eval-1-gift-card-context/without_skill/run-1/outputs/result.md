# Subcontexto `gift_card` en `commerce` (DDD + Hexagonal, FastAPI + SQLAlchemy/PostgreSQL)

Como no me diste el detalle exacto de tu convención interna, sigo el estándar más extendido para este stack (el mismo que usan libros de referencia como *Cosmic Python* / *Implementing DDD*): capas **domain → services (application layer) → adapters**, con inversión de dependencias (el dominio no conoce SQLAlchemy ni FastAPI), un **Repository** como puerto hacia persistencia, un **Unit of Work** para transaccionalidad, y los eventos de dominio recolectados en la agregada y despachados tras el commit. Ajusta nombres si tu codebase ya tiene convenciones propias (p. ej. `orchestrators/`, `use_cases/`, etc.).

## Árbol de archivos

```
commerce/
└── gift_card/
    ├── __init__.py
    ├── domain/
    │   ├── __init__.py
    │   ├── model.py          # Aggregate root GiftCard + Value Objects (Money, GiftCardCode)
    │   ├── events.py         # Eventos de dominio (GiftCardIssued, GiftCardRedeemed, GiftCardExpired)
    │   └── exceptions.py     # Excepciones de dominio
    ├── services/
    │   ├── __init__.py
    │   ├── unit_of_work.py   # Puerto + adaptador SQLAlchemy del UoW
    │   ├── handlers.py       # Casos de uso (comandos) + handlers de eventos
    │   └── message_bus.py    # Despacho de eventos de dominio
    └── adapters/
        ├── __init__.py
        ├── orm.py            # Modelo SQLAlchemy (declarativo) + mapeo hacia/desde el dominio
        ├── repository.py     # Puerto AbstractGiftCardRepository + adaptador SQLAlchemy
        └── entrypoints/
            ├── __init__.py
            └── api.py        # Router FastAPI (adaptador de entrada / "driving adapter")
```

**Regla de dependencias**: `domain` no importa nada de `adapters` ni de `services`. `services` importa `domain` y depende de los *puertos* (interfaces) definidos en `adapters`/`services`, no de sus implementaciones concretas. `adapters` importa `domain` y `services` para implementar los puertos y exponer la API.

---

## 1. Domain

### `commerce/gift_card/domain/exceptions.py`

```python
class GiftCardDomainError(Exception):
    """Clase base para todos los errores de dominio de GiftCard."""


class InvalidGiftCardCodeError(GiftCardDomainError):
    pass


class InvalidRedemptionAmountError(GiftCardDomainError):
    pass


class InsufficientBalanceError(GiftCardDomainError):
    pass


class GiftCardNotActiveError(GiftCardDomainError):
    pass


class GiftCardExpiredError(GiftCardDomainError):
    pass


class CurrencyMismatchError(GiftCardDomainError):
    pass


class GiftCardNotFoundError(GiftCardDomainError):
    pass


class GiftCardCodeAlreadyExistsError(GiftCardDomainError):
    pass
```

### `commerce/gift_card/domain/events.py`

```python
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


class DomainEvent:
    """Clase marcadora para todos los eventos de dominio de este subcontexto."""


@dataclass(frozen=True)
class GiftCardIssued(DomainEvent):
    gift_card_id: uuid.UUID
    code: str
    amount: Decimal
    currency: str
    issued_at: datetime


@dataclass(frozen=True)
class GiftCardRedeemed(DomainEvent):
    """Emitido cuando una gift card es canjeada (total o parcialmente)."""

    gift_card_id: uuid.UUID
    code: str
    amount: Decimal
    currency: str
    remaining_balance: Decimal
    fully_redeemed: bool
    redeemed_at: datetime


@dataclass(frozen=True)
class GiftCardExpired(DomainEvent):
    gift_card_id: uuid.UUID
    code: str
    remaining_balance: Decimal
    currency: str
    expired_at: datetime
```

### `commerce/gift_card/domain/model.py`

```python
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from commerce.gift_card.domain.events import (
    DomainEvent,
    GiftCardExpired,
    GiftCardIssued,
    GiftCardRedeemed,
)
from commerce.gift_card.domain.exceptions import (
    CurrencyMismatchError,
    GiftCardExpiredError,
    GiftCardNotActiveError,
    InsufficientBalanceError,
    InvalidGiftCardCodeError,
    InvalidRedemptionAmountError,
)

_CODE_LENGTH = 16


# ---------------------------------------------------------------------------
# Value Objects
# ---------------------------------------------------------------------------
class Money:
    """Value Object inmutable para representar dinero. Nunca usar float para dinero."""

    __slots__ = ("amount", "currency")

    def __init__(self, amount: Decimal, currency: str = "USD") -> None:
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))
        if amount < Decimal("0"):
            raise ValueError("El monto no puede ser negativo")
        if len(currency) != 3:
            raise ValueError("La moneda debe ser un código ISO-4217 de 3 letras")
        object.__setattr__(self, "amount", amount)
        object.__setattr__(self, "currency", currency.upper())

    def __setattr__(self, key, value):
        raise AttributeError("Money es inmutable")

    def _check_currency(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"No se puede operar entre {self.currency} y {other.currency}"
            )

    def __add__(self, other: "Money") -> "Money":
        self._check_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._check_currency(other)
        result = self.amount - other.amount
        if result < Decimal("0"):
            raise InsufficientBalanceError(
                f"No se puede restar {other.amount} de un balance de {self.amount}"
            )
        return Money(result, self.currency)

    def __gt__(self, other: "Money") -> bool:
        self._check_currency(other)
        return self.amount > other.amount

    def __ge__(self, other: "Money") -> bool:
        self._check_currency(other)
        return self.amount >= other.amount

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, Money)
            and self.amount == other.amount
            and self.currency == other.currency
        )

    def __hash__(self) -> int:
        return hash((self.amount, self.currency))

    def __repr__(self) -> str:
        return f"Money({self.amount}, {self.currency!r})"

    def is_zero(self) -> bool:
        return self.amount == Decimal("0")


class GiftCardCode:
    """Value Object para el código de la tarjeta. Se normaliza y valida en construcción."""

    __slots__ = ("value",)

    def __init__(self, raw_value: str) -> None:
        normalized = (raw_value or "").strip().upper()
        if len(normalized) != _CODE_LENGTH or not normalized.isalnum():
            raise InvalidGiftCardCodeError(
                f"'{raw_value}' no es un código de gift card válido "
                f"(se esperan {_CODE_LENGTH} caracteres alfanuméricos)"
            )
        object.__setattr__(self, "value", normalized)

    def __setattr__(self, key, value):
        raise AttributeError("GiftCardCode es inmutable")

    def __str__(self) -> str:
        return self.value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, GiftCardCode) and self.value == other.value

    def __hash__(self) -> int:
        return hash(self.value)


class GiftCardStatus(str, Enum):
    ACTIVE = "ACTIVE"
    REDEEMED = "REDEEMED"
    EXPIRED = "EXPIRED"


# ---------------------------------------------------------------------------
# Aggregate Root
# ---------------------------------------------------------------------------
class GiftCard:
    """Aggregate root del subcontexto GiftCard.

    Toda invariante de negocio (transiciones de estado, validación de saldo,
    expiración) vive aquí. Es un objeto plano de Python: no conoce SQLAlchemy,
    FastAPI ni ningún detalle de infraestructura.
    """

    def __init__(
        self,
        id: uuid.UUID,
        code: GiftCardCode,
        balance: Money,
        status: GiftCardStatus,
        issued_at: datetime,
        expires_at: datetime,
        redeemed_at: Optional[datetime] = None,
        version: int = 0,
    ) -> None:
        self.id = id
        self.code = code
        self.balance = balance
        self.status = status
        self.issued_at = issued_at
        self.expires_at = expires_at
        self.redeemed_at = redeemed_at
        self.version = version
        self.events: List[DomainEvent] = []

    # -- Factory -------------------------------------------------------
    @classmethod
    def issue(
        cls,
        code: GiftCardCode,
        initial_balance: Money,
        valid_for_days: int = 365,
    ) -> "GiftCard":
        if initial_balance.is_zero():
            raise InvalidRedemptionAmountError(
                "No se puede emitir una gift card con saldo inicial cero"
            )
        now = datetime.now(timezone.utc)
        gift_card = cls(
            id=uuid.uuid4(),
            code=code,
            balance=initial_balance,
            status=GiftCardStatus.ACTIVE,
            issued_at=now,
            expires_at=now + timedelta(days=valid_for_days),
        )
        gift_card.events.append(
            GiftCardIssued(
                gift_card_id=gift_card.id,
                code=str(gift_card.code),
                amount=gift_card.balance.amount,
                currency=gift_card.balance.currency,
                issued_at=now,
            )
        )
        return gift_card

    # -- Comportamiento --------------------------------------------------
    def redeem(self, amount: Money) -> None:
        """Canjea (total o parcialmente) el saldo de la tarjeta.

        Emite GiftCardRedeemed. Si el saldo llega a cero, la tarjeta pasa
        a estado REDEEMED.
        """
        self._expire_if_needed()

        if self.status != GiftCardStatus.ACTIVE:
            raise GiftCardNotActiveError(
                f"La gift card {self.code} no puede canjearse: estado actual {self.status.value}"
            )
        if amount.is_zero():
            raise InvalidRedemptionAmountError("El monto a canjear debe ser mayor a cero")
        if amount > self.balance:
            raise InsufficientBalanceError(
                f"La gift card {self.code} no tiene saldo suficiente: "
                f"solicitado {amount.amount}, disponible {self.balance.amount}"
            )

        self.balance = self.balance - amount
        redeemed_at = datetime.now(timezone.utc)
        fully_redeemed = self.balance.is_zero()

        if fully_redeemed:
            self.status = GiftCardStatus.REDEEMED
            self.redeemed_at = redeemed_at

        self.events.append(
            GiftCardRedeemed(
                gift_card_id=self.id,
                code=str(self.code),
                amount=amount.amount,
                currency=amount.currency,
                remaining_balance=self.balance.amount,
                fully_redeemed=fully_redeemed,
                redeemed_at=redeemed_at,
            )
        )

    def mark_expired(self) -> None:
        """Transición explícita a EXPIRED (usada también por un job/cron periódico)."""
        if self.status == GiftCardStatus.REDEEMED:
            return  # una tarjeta ya canjeada no puede expirar
        if self.status == GiftCardStatus.EXPIRED:
            return
        self.status = GiftCardStatus.EXPIRED
        self.events.append(
            GiftCardExpired(
                gift_card_id=self.id,
                code=str(self.code),
                remaining_balance=self.balance.amount,
                currency=self.balance.currency,
                expired_at=datetime.now(timezone.utc),
            )
        )

    # -- Helpers privados --------------------------------------------------
    def _expire_if_needed(self) -> None:
        if self.status == GiftCardStatus.ACTIVE and datetime.now(timezone.utc) >= self.expires_at:
            self.mark_expired()
        if self.status == GiftCardStatus.EXPIRED:
            raise GiftCardExpiredError(f"La gift card {self.code} está expirada")

    # -- Identidad --------------------------------------------------
    def __eq__(self, other: object) -> bool:
        return isinstance(other, GiftCard) and self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
```

**Notas de diseño del dominio:**
- `Money` y `GiftCardCode` son *Value Objects* inmutables con sus propias invariantes (no dejan existir un `Money` negativo ni un código con formato inválido).
- `GiftCard` es el único punto de entrada para mutar el estado: no hay setters públicos de `status`/`balance`, todo pasa por `redeem()` / `mark_expired()` / `issue()`.
- Los eventos se acumulan en `self.events` dentro de la propia agregada (patrón "eventos recolectados", igual que en Cosmic Python / muchas implementaciones de Evans-DDD) y se drenan después desde la capa de aplicación — así el dominio nunca depende de un bus de eventos concreto.
- La expiración se resuelve de forma perezosa (`_expire_if_needed`) en cada operación de negocio; para que las tarjetas vencidas no queden "activas" en el read model indefinidamente sin que nadie las toque, conviene además un job periódico (ver sección de notas de producción) que recorra tarjetas con `expires_at < now()` y llame `mark_expired()`.

---

## 2. Adapters

### `commerce/gift_card/adapters/orm.py`

```python
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum as SAEnum, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from commerce.gift_card.domain.model import GiftCard, GiftCardCode, GiftCardStatus, Money


class Base(DeclarativeBase):
    pass


class GiftCardModel(Base):
    """Modelo de persistencia (SQLAlchemy). Solo lo importan los adapters,
    nunca el dominio ni los casos de uso.
    """

    __tablename__ = "gift_cards"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    balance_amount: Mapped[Numeric] = mapped_column(Numeric(12, 2), nullable=False)
    balance_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[GiftCardStatus] = mapped_column(
        SAEnum(GiftCardStatus, name="gift_card_status", native_enum=True),
        nullable=False,
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    redeemed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # -- Mapeo dominio <-> persistencia --------------------------------
    def to_domain(self) -> GiftCard:
        return GiftCard(
            id=self.id,
            code=GiftCardCode(self.code),
            balance=Money(self.balance_amount, self.balance_currency),
            status=self.status,
            issued_at=self.issued_at,
            expires_at=self.expires_at,
            redeemed_at=self.redeemed_at,
            version=self.version,
        )

    @classmethod
    def from_domain(cls, gift_card: GiftCard) -> "GiftCardModel":
        return cls(
            id=gift_card.id,
            code=str(gift_card.code),
            balance_amount=gift_card.balance.amount,
            balance_currency=gift_card.balance.currency,
            status=gift_card.status,
            issued_at=gift_card.issued_at,
            expires_at=gift_card.expires_at,
            redeemed_at=gift_card.redeemed_at,
            version=gift_card.version,
        )

    def update_from_domain(self, gift_card: GiftCard) -> None:
        """Sincroniza los campos mutables tras una operación de dominio."""
        self.balance_amount = gift_card.balance.amount
        self.balance_currency = gift_card.balance.currency
        self.status = gift_card.status
        self.redeemed_at = gift_card.redeemed_at
        self.version = gift_card.version
```

**Migración Alembic (referencia mínima):**

```python
# alembic/versions/xxxx_create_gift_cards.py
def upgrade() -> None:
    op.create_table(
        "gift_cards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("balance_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("balance_currency", sa.String(3), nullable=False),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "REDEEMED", "EXPIRED", name="gift_card_status"),
            nullable=False,
        ),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_unique_constraint("uq_gift_cards_code", "gift_cards", ["code"])
    op.create_index("ix_gift_cards_expires_at", "gift_cards", ["expires_at"])


def downgrade() -> None:
    op.drop_table("gift_cards")
    op.execute("DROP TYPE gift_card_status")
```

### `commerce/gift_card/adapters/repository.py`

```python
from __future__ import annotations

import abc
import uuid
from typing import Dict, Optional, Set

from sqlalchemy.orm import Session

from commerce.gift_card.adapters.orm import GiftCardModel
from commerce.gift_card.domain.model import GiftCard, GiftCardCode


class AbstractGiftCardRepository(abc.ABC):
    """Puerto: cómo la capa de aplicación accede a las agregadas GiftCard.

    Trackea las agregadas "vistas" (`seen`) para que el Unit of Work pueda
    luego drenar sus eventos de dominio, sin acoplar el repositorio a un
    bus de eventos concreto.
    """

    def __init__(self) -> None:
        self.seen: Set[GiftCard] = set()

    def add(self, gift_card: GiftCard) -> None:
        self._add(gift_card)
        self.seen.add(gift_card)

    def get(self, code: GiftCardCode) -> Optional[GiftCard]:
        gift_card = self._get(code)
        if gift_card is not None:
            self.seen.add(gift_card)
        return gift_card

    def get_by_id(self, gift_card_id: uuid.UUID) -> Optional[GiftCard]:
        gift_card = self._get_by_id(gift_card_id)
        if gift_card is not None:
            self.seen.add(gift_card)
        return gift_card

    @abc.abstractmethod
    def _add(self, gift_card: GiftCard) -> None: ...

    @abc.abstractmethod
    def _get(self, code: GiftCardCode) -> Optional[GiftCard]: ...

    @abc.abstractmethod
    def _get_by_id(self, gift_card_id: uuid.UUID) -> Optional[GiftCard]: ...


class SqlAlchemyGiftCardRepository(AbstractGiftCardRepository):
    """Adaptador de salida ("driven adapter"): implementación PostgreSQL."""

    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session
        self._identity_map: Dict[uuid.UUID, GiftCardModel] = {}

    def _add(self, gift_card: GiftCard) -> None:
        model = GiftCardModel.from_domain(gift_card)
        self.session.add(model)
        self._identity_map[gift_card.id] = model

    def _get(self, code: GiftCardCode) -> Optional[GiftCard]:
        # with_for_update: lock pesimista de fila para evitar canjes
        # concurrentes sobre la misma tarjeta (double-spend).
        model = (
            self.session.query(GiftCardModel)
            .filter_by(code=str(code))
            .with_for_update()
            .first()
        )
        if model is None:
            return None
        self._identity_map[model.id] = model
        return model.to_domain()

    def _get_by_id(self, gift_card_id: uuid.UUID) -> Optional[GiftCard]:
        model = self.session.get(GiftCardModel, gift_card_id)
        if model is None:
            return None
        self._identity_map[model.id] = model
        return model.to_domain()

    def persist(self, gift_card: GiftCard) -> None:
        """Vuelca los cambios del objeto de dominio sobre la fila ORM
        rastreada, antes del commit. Necesario porque `to_domain()` crea
        un objeto de dominio desconectado de la Session.
        """
        model = self._identity_map.get(gift_card.id)
        if model is not None:
            model.update_from_domain(gift_card)
```

### `commerce/gift_card/adapters/entrypoints/api.py`

```python
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from commerce.gift_card.domain.exceptions import (
    CurrencyMismatchError,
    GiftCardCodeAlreadyExistsError,
    GiftCardExpiredError,
    GiftCardNotActiveError,
    GiftCardNotFoundError,
    InsufficientBalanceError,
    InvalidGiftCardCodeError,
    InvalidRedemptionAmountError,
)
from commerce.gift_card.domain.model import GiftCardCode
from commerce.gift_card.services import handlers, message_bus
from commerce.gift_card.services.unit_of_work import SqlAlchemyUnitOfWork

router = APIRouter(prefix="/gift-cards", tags=["gift-cards"])

_DOMAIN_ERROR_STATUS = {
    InvalidGiftCardCodeError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    InvalidRedemptionAmountError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    CurrencyMismatchError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    GiftCardCodeAlreadyExistsError: status.HTTP_409_CONFLICT,
    GiftCardNotFoundError: status.HTTP_404_NOT_FOUND,
    GiftCardNotActiveError: status.HTTP_409_CONFLICT,
    GiftCardExpiredError: status.HTTP_409_CONFLICT,
    InsufficientBalanceError: status.HTTP_409_CONFLICT,
}


class IssueGiftCardRequest(BaseModel):
    code: str = Field(..., min_length=16, max_length=16)
    amount: Decimal = Field(..., gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    valid_for_days: int = Field(default=365, gt=0)


class IssueGiftCardResponse(BaseModel):
    id: str
    code: str


class RedeemGiftCardRequest(BaseModel):
    amount: Decimal = Field(..., gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)


class GiftCardResponse(BaseModel):
    id: str
    code: str
    balance: Decimal
    currency: str
    status: str


def _raise_as_http(exc: Exception) -> None:
    status_code = _DOMAIN_ERROR_STATUS.get(type(exc), status.HTTP_400_BAD_REQUEST)
    raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post("", response_model=IssueGiftCardResponse, status_code=status.HTTP_201_CREATED)
def issue_gift_card(payload: IssueGiftCardRequest) -> IssueGiftCardResponse:
    cmd = handlers.IssueGiftCard(
        code=payload.code,
        amount=payload.amount,
        currency=payload.currency,
        valid_for_days=payload.valid_for_days,
    )
    try:
        with SqlAlchemyUnitOfWork() as uow:
            gift_card_id = handlers.issue_gift_card(cmd, uow)
            message_bus.dispatch(uow)
    except tuple(_DOMAIN_ERROR_STATUS) as exc:
        _raise_as_http(exc)

    return IssueGiftCardResponse(id=gift_card_id, code=payload.code.upper())


@router.post("/{code}/redeem", status_code=status.HTTP_204_NO_CONTENT)
def redeem_gift_card(code: str, payload: RedeemGiftCardRequest) -> None:
    cmd = handlers.RedeemGiftCard(code=code, amount=payload.amount, currency=payload.currency)
    try:
        with SqlAlchemyUnitOfWork() as uow:
            handlers.redeem_gift_card(cmd, uow)
            message_bus.dispatch(uow)
    except tuple(_DOMAIN_ERROR_STATUS) as exc:
        _raise_as_http(exc)


@router.get("/{code}", response_model=GiftCardResponse)
def get_gift_card(code: str) -> GiftCardResponse:
    try:
        with SqlAlchemyUnitOfWork() as uow:
            gift_card = uow.gift_cards.get(GiftCardCode(code))
            if gift_card is None:
                raise GiftCardNotFoundError(f"Gift card {code} no encontrada")
            return GiftCardResponse(
                id=str(gift_card.id),
                code=str(gift_card.code),
                balance=gift_card.balance.amount,
                currency=gift_card.balance.currency,
                status=gift_card.status.value,
            )
    except tuple(_DOMAIN_ERROR_STATUS) as exc:
        _raise_as_http(exc)
```

Registro en la app principal:

```python
# main.py / app.py
from fastapi import FastAPI
from commerce.gift_card.adapters.entrypoints.api import router as gift_card_router

app = FastAPI()
app.include_router(gift_card_router)
```

---

## 3. Services (capa de aplicación)

### `commerce/gift_card/services/unit_of_work.py`

```python
from __future__ import annotations

import abc
from types import TracebackType
from typing import Iterator, Optional, Type

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from commerce.gift_card.adapters.repository import (
    AbstractGiftCardRepository,
    SqlAlchemyGiftCardRepository,
)
from commerce.gift_card.domain.events import DomainEvent
from config import get_postgres_uri  # ajusta al módulo de config de tu proyecto

DEFAULT_SESSION_FACTORY = sessionmaker(
    bind=create_engine(get_postgres_uri(), isolation_level="READ COMMITTED"),
    expire_on_commit=False,
)


class AbstractUnitOfWork(abc.ABC):
    gift_cards: AbstractGiftCardRepository

    def __enter__(self) -> "AbstractUnitOfWork":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        self.rollback()  # no-op si ya hubo commit; red de seguridad ante excepciones

    @abc.abstractmethod
    def commit(self) -> None: ...

    @abc.abstractmethod
    def rollback(self) -> None: ...

    def collect_new_events(self) -> Iterator[DomainEvent]:
        for gift_card in self.gift_cards.seen:
            while gift_card.events:
                yield gift_card.events.pop(0)


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    def __init__(self, session_factory=DEFAULT_SESSION_FACTORY) -> None:
        self.session_factory = session_factory

    def __enter__(self) -> "SqlAlchemyUnitOfWork":
        self.session: Session = self.session_factory()
        self.gift_cards = SqlAlchemyGiftCardRepository(self.session)
        return super().__enter__()

    def __exit__(self, *args) -> None:
        super().__exit__(*args)
        self.session.close()

    def commit(self) -> None:
        # Sincroniza cada agregada modificada con su fila ORM antes de hacer commit.
        for gift_card in self.gift_cards.seen:
            self.gift_cards.persist(gift_card)
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
```

### `commerce/gift_card/services/handlers.py`

```python
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from commerce.gift_card.domain import events
from commerce.gift_card.domain.exceptions import (
    GiftCardCodeAlreadyExistsError,
    GiftCardNotFoundError,
)
from commerce.gift_card.domain.model import GiftCard, GiftCardCode, Money
from commerce.gift_card.services.unit_of_work import AbstractUnitOfWork

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Comandos (DTOs de entrada para los casos de uso)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class IssueGiftCard:
    code: str
    amount: Decimal
    currency: str = "USD"
    valid_for_days: int = 365


@dataclass(frozen=True)
class RedeemGiftCard:
    code: str
    amount: Decimal
    currency: str = "USD"


# ---------------------------------------------------------------------------
# Casos de uso (application services)
# ---------------------------------------------------------------------------
def issue_gift_card(cmd: IssueGiftCard, uow: AbstractUnitOfWork) -> str:
    with uow:
        code = GiftCardCode(cmd.code)
        if uow.gift_cards.get(code) is not None:
            raise GiftCardCodeAlreadyExistsError(f"La gift card {code} ya existe")

        gift_card = GiftCard.issue(
            code=code,
            initial_balance=Money(cmd.amount, cmd.currency),
            valid_for_days=cmd.valid_for_days,
        )
        uow.gift_cards.add(gift_card)
        uow.commit()
        return str(gift_card.id)


def redeem_gift_card(cmd: RedeemGiftCard, uow: AbstractUnitOfWork) -> None:
    with uow:
        code = GiftCardCode(cmd.code)
        gift_card = uow.gift_cards.get(code)  # lock pesimista via with_for_update
        if gift_card is None:
            raise GiftCardNotFoundError(f"Gift card {code} no encontrada")

        gift_card.redeem(Money(cmd.amount, cmd.currency))
        uow.commit()


# ---------------------------------------------------------------------------
# Handlers de eventos de dominio (efectos secundarios)
# ---------------------------------------------------------------------------
def notify_loyalty_on_redemption(event: events.GiftCardRedeemed) -> None:
    logger.info(
        "Notificando canje a loyalty: gift_card=%s monto=%s %s saldo_restante=%s fully_redeemed=%s",
        event.code, event.amount, event.currency, event.remaining_balance, event.fully_redeemed,
    )
    # p.ej.: loyalty_client.award_points(gift_card_code=event.code, amount=event.amount)


def publish_to_outbox(event: events.DomainEvent) -> None:
    # En producción: serializar el evento y escribirlo en una tabla `outbox`
    # dentro de la MISMA transacción del UoW (ver notas de producción), o
    # publicarlo directo a SQS/EventBridge/Kafka desde un relay.
    logger.info("Publicando evento de dominio: %s", event)
```

### `commerce/gift_card/services/message_bus.py`

```python
from __future__ import annotations

import logging
from typing import Callable, Dict, List, Type

from commerce.gift_card.domain import events
from commerce.gift_card.domain.events import DomainEvent
from commerce.gift_card.services import handlers
from commerce.gift_card.services.unit_of_work import AbstractUnitOfWork

logger = logging.getLogger(__name__)

HANDLERS: Dict[Type[DomainEvent], List[Callable]] = {
    events.GiftCardIssued: [handlers.publish_to_outbox],
    events.GiftCardRedeemed: [
        handlers.notify_loyalty_on_redemption,
        handlers.publish_to_outbox,
    ],
    events.GiftCardExpired: [handlers.publish_to_outbox],
}


def handle(event: DomainEvent) -> None:
    for handler in HANDLERS.get(type(event), []):
        try:
            handler(event)
        except Exception:
            # Un handler de evento nunca debe tumbar el caso de uso principal.
            logger.exception("Error manejando el evento %s", event)


def dispatch(uow: AbstractUnitOfWork) -> None:
    """Drena los eventos de dominio acumulados durante el UoW y los publica."""
    for event in uow.collect_new_events():
        handle(event)
```

---

## Notas de producción (para llevar esto más allá del ejemplo)

1. **Concurrencia / double-spend en el canje**: uso `with_for_update()` (lock pesimista de fila) en `SqlAlchemyGiftCardRepository._get` para que dos requests de canje simultáneos sobre la misma tarjeta no lean el mismo saldo. Alternativa más escalable: control de **concurrencia optimista** con la columna `version` (incrementarla en `update_from_domain` y usarla como filtro en el `UPDATE`, reintentando en caso de conflicto).

2. **Idempotencia del canje**: en un endpoint de dinero, los reintentos de red son peligrosos. Se recomienda exigir un header `Idempotency-Key` en `POST /gift-cards/{code}/redeem`, guardarlo en una tabla `idempotency_keys` (dentro del mismo UoW) y devolver la respuesta cacheada si la key ya fue procesada, en vez de re-ejecutar `redeem()`.

3. **Publicación confiable de eventos (transactional outbox)**: el `message_bus.dispatch(uow)` de este ejemplo despacha en memoria, *después* del commit de la transacción principal — si el proceso muere entre el commit y el dispatch, el evento se pierde. Para garantías reales, persiste el evento en una tabla `outbox` **dentro de la misma transacción** que el cambio de estado (en `uow.commit()`), y un proceso aparte (poller o CDC) lo publica a SQS/EventBridge y lo marca como enviado.

4. **Expiración proactiva**: además de la expiración perezosa en `redeem()`, agrega un job (cron / Lambda programada) que corra `SELECT ... WHERE status = 'ACTIVE' AND expires_at < now()`, llame `gift_card.mark_expired()` por cada una y haga commit — así el estado no depende de que alguien intente canjear la tarjeta para que se refleje como expirada.

5. **Testing**: 
   - Unitarios de dominio: probar `GiftCard.issue/redeem/mark_expired` con un `FakeRepository`/objetos en memoria (sin DB).
   - Integración: `SqlAlchemyGiftCardRepository` contra una PostgreSQL real (o testcontainers), verificando el mapeo `to_domain`/`from_domain`.
   - End-to-end: `TestClient` de FastAPI contra la app completa, verificando el mapeo de excepciones de dominio a códigos HTTP.

6. **Multi-moneda**: si el negocio realmente necesita multi-moneda por tarjeta, considera que `redeem()` ya rechaza mezclar monedas (`CurrencyMismatchError`); si en cambio siempre operas en una sola moneda por tenant/mercado, puedes simplificar `Money` quitando el campo `currency` variable y fijarlo por configuración.
