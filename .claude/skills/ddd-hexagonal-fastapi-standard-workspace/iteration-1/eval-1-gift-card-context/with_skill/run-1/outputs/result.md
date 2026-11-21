# Nuevo subcontexto `gift_card` en `commerce`

## Decisiones antes de escribir código

- **Producto**: `commerce` (ya existe — junto a `stock`/`orders` en el golden path). El
  subcontexto se llama como su agregado, en `snake_case` (§3.1): `commerce/gift_card/`.
- **Agregado único**: `GiftCard`. `code`, `balance` y `status` viven todos en el mismo
  agregado — no hay razón de diseño para separarlos (no tienen ciclo de vida independiente
  entre sí), así que es un único `AggregateRoot`, no varios.
- **¿Orquestador?** No. Recorriendo el árbol de decisión de orquestación (§10): *"¿el caso de
  uso muta exactamente una instancia de agregado?"* → Sí, tanto emitir (`issue`) como canjear
  (`redeem`) tocan solo `GiftCard`. Eso cae directo en **§10.1: se llama la función de
  `services/` del propio subcontexto, sin orquestador.** Envolver esto en un
  "orchestrator" por simetría con otros casos sería el smell *Middle Man* que el estándar
  explícitamente pide evitar.
- **`code`** es la clave de negocio (la que el cliente usa para canjear), separada del `id`
  interno (`GiftCardId`, `UuidV7Id`) — mismo patrón que `Sku` en `Stock`, no un
  `HumanFriendlyId` (ese wrapper es específicamente para el campo `id` de una entidad).
- **`balance`** usa `Money` — concretamente `NonNegativeMoney`, porque un saldo nunca debe
  quedar en negativo pero sí puede llegar a cero (tarjeta agotada). El monto a canjear en cada
  operación usa `PositiveMoney` (no tiene sentido canjear \$0).
- **`status`** es un `enum.StrEnum` con tres estados: `active` / `redeemed` / `expired`.
- **Evento al canjear**: `GiftCardRedeemed`, grabado con `record_event` dentro de `redeem()` y
  publicado al outbox por `services/gift_card.py` en la misma transacción — la regla no
  negociable de §1.6 (todo `record_event` necesita su punto de drenaje documentado en el mismo
  commit).
- Como el enunciado también implica una fecha de expiración (para poder llegar al estado
  `expired`), agregué `expires_at: PosixTime` al agregado y un método `expire()` idempotente
  para uso de un cron de housekeeping — sin este campo, "expirada" no sería alcanzable por
  ninguna regla de negocio real.
- `Money` (`commons/domain/money.py`) tal como está citado en el estándar no expone `__sub__`
  (solo `__add__`/`__mul__`). Lo necesito para descontar el balance, así que lo agrego al
  mismo archivo compartido (mismo patrón que `__add__`), en vez de reinventar la resta a mano
  en el agregado.

No se necesita `ports.py`: `GiftCard` no requiere ninguna llamada síncrona a un sistema
externo ni a otro bounded context.

## Árbol de archivos

```
commerce/gift_card/
├── domain/
│   └── model/
│       ├── aggregate.py
│       ├── value_objects.py
│       ├── exceptions.py
│       └── events.py
├── adapters/
│   ├── orm.py
│   └── repository.py
└── services/
    ├── dto.py
    └── gift_card.py
```

---

## 1. Adición al *shared kernel* — `Money.__sub__`

Necesario porque `redeem()` descuenta saldo y el `Money` citado en el estándar no trae resta.
Mismo criterio que `__add__`: valida moneda, devuelve `Money` base (no el subtipo
restringido — igual que `Order.total`, que también normaliza a `Money` base).

```python
# commons/domain/money.py  (añadir junto a __add__/__mul__ existentes)
class Money(value_objects.ValueObject):
    currency: Currencies
    value: decimal.Decimal

    def __add__(self, other: "Money") -> "Money":
        if self.currency is not other.currency:
            raise exceptions.ValidationError("Can't add different currencies")
        return Money(currency=self.currency, value=self.value + other.value)

    def __sub__(self, other: "Money") -> "Money":
        if self.currency is not other.currency:
            raise exceptions.ValidationError("Can't subtract different currencies")
        return Money(currency=self.currency, value=self.value - other.value)

    # ... resto sin cambios (__mul__, compare, __lt__, is_zero, cop)
```

---

## 2. Dominio — sin I/O, sin `fastapi`/`sqlalchemy`/`boto3`

### `commerce/gift_card/domain/model/value_objects.py`

```python
from commons.domain import id_generator, value_objects
import enum


class GiftCardId(value_objects.UuidV7Id):
    pass


class GiftCardCode(value_objects.ValueObject):
    """Clave de negocio con la que el cliente canjea la tarjeta — distinta de GiftCardId,
    que es la identidad interna del agregado. Se busca por code, nunca por id, en checkout."""
    value: str

    @classmethod
    def generate(cls) -> "GiftCardCode":
        return cls(value=id_generator.generate_short_id())


class GiftCardStatus(enum.StrEnum):
    ACTIVE = "active"
    REDEEMED = "redeemed"
    EXPIRED = "expired"
```

### `commerce/gift_card/domain/model/events.py`

```python
import uuid

import pydantic

from commons.domain import events as domain_events, money
from commons.domain import value_objects as base_value_objects

from commerce.gift_card.domain.model import value_objects

# event_id/occurred_at llevan default_factory en cada evento concreto — así el agregado los
# construye pasando solo los campos propios del hecho de negocio, igual que
# events.StockCreated(stock_id=stock.id, sku=sku) en el golden path.


class GiftCardIssued(domain_events.DomainEvent):
    event_id: uuid.UUID = pydantic.Field(default_factory=uuid.uuid4)
    occurred_at: base_value_objects.PosixTime = pydantic.Field(
        default_factory=base_value_objects.PosixTime.now,
    )
    gift_card_id: value_objects.GiftCardId
    code: value_objects.GiftCardCode
    initial_balance: money.NonNegativeMoney


class GiftCardRedeemed(domain_events.DomainEvent):
    """Se emite cada vez que se canjea saldo de la tarjeta. Se mantiene como DomainEvent
    interno por ahora; si otro bounded context necesita reaccionar a esto (notificaciones,
    contabilidad), se promueve a IntegrationEvent (§11.1) sin tocar este agregado."""
    event_id: uuid.UUID = pydantic.Field(default_factory=uuid.uuid4)
    occurred_at: base_value_objects.PosixTime = pydantic.Field(
        default_factory=base_value_objects.PosixTime.now,
    )
    gift_card_id: value_objects.GiftCardId
    code: value_objects.GiftCardCode
    amount_redeemed: money.PositiveMoney
    remaining_balance: money.NonNegativeMoney


class GiftCardExpired(domain_events.DomainEvent):
    event_id: uuid.UUID = pydantic.Field(default_factory=uuid.uuid4)
    occurred_at: base_value_objects.PosixTime = pydantic.Field(
        default_factory=base_value_objects.PosixTime.now,
    )
    gift_card_id: value_objects.GiftCardId
    code: value_objects.GiftCardCode
```

### `commerce/gift_card/domain/model/exceptions.py`

```python
from commons.domain import exceptions


class GiftCardNotFoundError(exceptions.NotFoundError):
    def __init__(self, *, identifier: object) -> None:
        super().__init__(f"Gift card [{identifier}] not found.", code="GIFT_CARD_NOT_FOUND")


class GiftCardNotActiveError(exceptions.ConflictError):
    def __init__(self, *, gift_card_id: "value_objects.GiftCardId",
                 status: "value_objects.GiftCardStatus") -> None:
        super().__init__(
            f"Gift card [{gift_card_id}] is not active (status=[{status}]).",
            code="GIFT_CARD_NOT_ACTIVE",
        )


class GiftCardExpiredError(exceptions.ConflictError):
    def __init__(self, *, gift_card_id: "value_objects.GiftCardId",
                 expires_at: "base_value_objects.PosixTime") -> None:
        super().__init__(
            f"Gift card [{gift_card_id}] expired at [{expires_at}].",
            code="GIFT_CARD_EXPIRED",
        )


class InsufficientGiftCardBalanceError(exceptions.ConflictError):
    def __init__(self, *, gift_card_id: "value_objects.GiftCardId",
                 requested: "money.Money", available: "money.Money") -> None:
        super().__init__(
            f"Cannot redeem [{requested}] from gift card [{gift_card_id}]: "
            f"only [{available}] available.",
            code="INSUFFICIENT_GIFT_CARD_BALANCE",
        )
```

*(Los tipos entre comillas — `value_objects.GiftCardId`, `base_value_objects.PosixTime`,
`money.Money` — son referencias de tipo hacia adelante; en el archivo real de producción
se agregan como `if typing.TYPE_CHECKING:` con los imports correspondientes, para no crear un
import circular entre `exceptions.py` y `value_objects.py`/`aggregate.py`.)*

### `commerce/gift_card/domain/model/aggregate.py`

```python
from commons.domain import aggregates, money
from commons.domain import value_objects as base_value_objects

from commerce.gift_card.domain.model import events, exceptions, value_objects


class GiftCard(aggregates.AggregateRoot[value_objects.GiftCardId]):
    code: value_objects.GiftCardCode
    balance: money.NonNegativeMoney
    status: value_objects.GiftCardStatus
    expires_at: base_value_objects.PosixTime

    @classmethod
    def issue(cls, *, initial_balance: money.NonNegativeMoney,
              expires_at: base_value_objects.PosixTime) -> "GiftCard":
        """Emite una tarjeta de regalo nueva, ACTIVA, con un code generado internamente."""
        now = base_value_objects.PosixTime.now()
        gift_card = cls(
            id=value_objects.GiftCardId.new(),
            code=value_objects.GiftCardCode.generate(),
            balance=initial_balance,
            status=value_objects.GiftCardStatus.ACTIVE,
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
        )
        gift_card.record_event(events.GiftCardIssued(
            gift_card_id=gift_card.id, code=gift_card.code, initial_balance=gift_card.balance,
        ))
        return gift_card

    def redeem(self, *, amount: money.PositiveMoney) -> None:
        """Descuenta `amount` del saldo. La tarjeta pasa a REDEEMED cuando el saldo llega a
        cero; puede canjearse parcialmente varias veces antes de eso."""
        if self.status is not value_objects.GiftCardStatus.ACTIVE:
            raise exceptions.GiftCardNotActiveError(gift_card_id=self.id, status=self.status)
        if self.expires_at < base_value_objects.PosixTime.now():
            raise exceptions.GiftCardExpiredError(gift_card_id=self.id,
                                                    expires_at=self.expires_at)
        if self.balance.compare(amount) < 0:
            raise exceptions.InsufficientGiftCardBalanceError(
                gift_card_id=self.id, requested=amount, available=self.balance,
            )

        new_balance = self.balance - amount   # Money.__sub__ — nunca desempaquetar .value aquí
        self.balance = money.NonNegativeMoney(currency=new_balance.currency,
                                                value=new_balance.value)
        if self.balance.is_zero():
            self.status = value_objects.GiftCardStatus.REDEEMED
        self.updated_at = base_value_objects.PosixTime.now()

        self.record_event(events.GiftCardRedeemed(
            gift_card_id=self.id, code=self.code,
            amount_redeemed=amount, remaining_balance=self.balance,
        ))

    def expire(self) -> None:
        """Marca la tarjeta EXPIRED. Pensado para un cron de housekeeping una vez pasado
        `expires_at`. Idempotente si ya está EXPIRED; prohibido si ya fue REDEEMED."""
        if self.status is value_objects.GiftCardStatus.REDEEMED:
            raise exceptions.GiftCardNotActiveError(gift_card_id=self.id, status=self.status)
        if self.status is value_objects.GiftCardStatus.EXPIRED:
            return
        self.status = value_objects.GiftCardStatus.EXPIRED
        self.updated_at = base_value_objects.PosixTime.now()
        self.record_event(events.GiftCardExpired(gift_card_id=self.id, code=self.code))
```

Convenciones aplicadas: factories de clase (`issue`) construyen-y-graban-evento en un solo
lugar; los métodos de instancia son comandos con nombre de verbo (`redeem`, `expire`), cada
uno guarda con una excepción de dominio nombrada y angosta, muta estado, y graba exactamente
los eventos que describen lo ocurrido. Nada de infraestructura: `expires_at`/`initial_balance`
llegan como parámetros, no se consulta ninguna base de datos desde aquí.

---

## 3. Adapters

### `commerce/gift_card/adapters/orm.py`

```python
import decimal
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from commons.adapters import orm_base


class GiftCardOrm(orm_base.Base, orm_base.TimestampsMixin):
    __tablename__ = "gift_card"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(sa.Text, unique=True)
    balance_currency: Mapped[str] = mapped_column(sa.Text)
    balance_value: Mapped[decimal.Decimal] = mapped_column(sa.Numeric(18, 2))
    status: Mapped[str] = mapped_column(sa.Text)
    expires_at: Mapped[int] = mapped_column(sa.BigInteger)
    version: Mapped[int] = mapped_column(default=0)

    __mapper_args__ = {"version_id_col": version}
```

`version_id_col` habilita el locking optimista nativo de Postgres (§8.1): cualquier `UPDATE`
concurrente que pisara un canje ya aplicado falla con `StaleDataError` en vez de perder el
descuento de saldo silenciosamente — el escenario exacto que le puede pasar a un `balance`
compartido bajo dos requests casi simultáneos.

### `commerce/gift_card/adapters/repository.py`

```python
import sqlalchemy as sa
import sqlalchemy.orm.exc

from commons.domain import exceptions as commons_exceptions, money, repositories
from commons.domain import value_objects as base_value_objects

from commerce.gift_card.adapters import orm
from commerce.gift_card.domain.model import aggregate, exceptions, value_objects


def _to_orm(gift_card: aggregate.GiftCard) -> orm.GiftCardOrm:
    return orm.GiftCardOrm(
        id=gift_card.id.value,
        code=gift_card.code.value,
        balance_currency=gift_card.balance.currency.value,
        balance_value=gift_card.balance.value,
        status=gift_card.status.value,
        expires_at=gift_card.expires_at.microseconds,
        created_at=gift_card.created_at.microseconds,
        updated_at=gift_card.updated_at.microseconds,
        version=gift_card.version,
    )


def _to_entity(gift_card_orm: orm.GiftCardOrm) -> aggregate.GiftCard:
    return aggregate.GiftCard(
        id=value_objects.GiftCardId(value=gift_card_orm.id),
        code=value_objects.GiftCardCode(value=gift_card_orm.code),
        balance=money.NonNegativeMoney(
            currency=money.Currencies(gift_card_orm.balance_currency),
            value=gift_card_orm.balance_value,
        ),
        status=value_objects.GiftCardStatus(gift_card_orm.status),
        expires_at=base_value_objects.PosixTime(microseconds=gift_card_orm.expires_at),
        created_at=base_value_objects.PosixTime(microseconds=gift_card_orm.created_at),
        updated_at=base_value_objects.PosixTime(microseconds=gift_card_orm.updated_at),
        version=gift_card_orm.version,
    )


class DefaultGiftCardRepository(repositories.Repository[aggregate.GiftCard]):
    def __init__(self, session: "orm.Session") -> None:
        self._session = session

    def get(self, id: "value_objects.GiftCardId") -> aggregate.GiftCard:
        gift_card_orm = self._session.get(orm.GiftCardOrm, id.value)
        if gift_card_orm is None:
            raise exceptions.GiftCardNotFoundError(identifier=id)
        return _to_entity(gift_card_orm)

    def get_by_code(self, code: "value_objects.GiftCardCode") -> aggregate.GiftCard:
        gift_card_orm = self._session.execute(
            sa.select(orm.GiftCardOrm).where(orm.GiftCardOrm.code == code.value)
        ).scalar_one_or_none()
        if gift_card_orm is None:
            raise exceptions.GiftCardNotFoundError(identifier=code)
        return _to_entity(gift_card_orm)

    def put(self, gift_card: aggregate.GiftCard) -> None:
        self._session.merge(_to_orm(gift_card))
        try:
            self._session.flush()   # fuerza el chequeo de versión ya, no al hacer commit
        except sqlalchemy.orm.exc.StaleDataError as exc:
            raise commons_exceptions.ConcurrentModificationError(
                f"Gift card [{gift_card.id}] changed concurrently — reload and retry.",
                code="CONCURRENT_MODIFICATION",
            ) from exc

    def delete(self, id: "value_objects.GiftCardId") -> None:
        gift_card_orm = self._session.get(orm.GiftCardOrm, id.value)
        if gift_card_orm is not None:
            self._session.delete(gift_card_orm)


# Registro del repo — se ejecuta una vez al arrancar (mismo punto donde bold/sona-sso-backend
# registran cada repo concreto):
# unit_of_work.register_repo(aggregate.GiftCard, DefaultGiftCardRepository)
```

`gift_card.id.value`, `.balance.value`, `.expires_at.microseconds` se desempaquetan **solo
aquí** — este par de funciones es el único lugar del codebase autorizado a hacerlo, porque
traducir entre representación de dominio y representación de almacenamiento es su único
propósito (Data Mapper, Fowler). La misma extracción en `domain/` o `services/` sí sería el
anti-patrón que el estándar prohíbe.

`code` se genera aleatoriamente (`GiftCardCode.generate()`) y tiene constraint `unique=True`
en la tabla — mismo riesgo de colisión que un `HumanFriendlyId`; en producción, `put()` para
una tarjeta recién emitida se envolvería con
`commons.adapters.repository_helpers.insert_with_id_retry` en vez de un `put()` directo.

---

## 4. Application layer — `services/`

### `commerce/gift_card/services/dto.py`

```python
import decimal

import pydantic

from commons.domain import money

from commerce.gift_card.domain.model import aggregate


class IssueGiftCardInputDTO(pydantic.BaseModel):
    initial_balance: decimal.Decimal
    currency: money.Currencies
    valid_days: int


class RedeemGiftCardInputDTO(pydantic.BaseModel):
    code: str
    amount: decimal.Decimal
    currency: money.Currencies


class GiftCardOutputDTO(pydantic.BaseModel):
    id: str
    code: str
    balance: decimal.Decimal
    currency: money.Currencies
    status: str
    expires_at: int

    @classmethod
    def from_entity(cls, gift_card: "aggregate.GiftCard") -> "GiftCardOutputDTO":
        return cls(
            id=str(gift_card.id.value),
            code=gift_card.code.value,
            balance=gift_card.balance.value,
            currency=gift_card.balance.currency,
            status=gift_card.status.value,
            expires_at=gift_card.expires_at.microseconds,
        )
```

### `commerce/gift_card/services/gift_card.py`

```python
import datetime

from commons.adapters import logs, unit_of_work
from commons.domain import aggregates, money
from commons.domain import value_objects as base_value_objects

from commerce.gift_card.domain.model import aggregate, value_objects
from commerce.gift_card.services import dto

_LOGGER = logs.get_logger()


def issue_gift_card(*, uow: "unit_of_work.UnitOfWork",
                     input_dto: dto.IssueGiftCardInputDTO) -> dto.GiftCardOutputDTO:
    """Emite una tarjeta de regalo nueva, válida por `input_dto.valid_days` días."""
    expires_at = base_value_objects.PosixTime.from_datetime(
        datetime.datetime.now(tz=datetime.UTC)
        + datetime.timedelta(days=input_dto.valid_days)
    )
    with uow.transaction():
        gift_card = aggregate.GiftCard.issue(
            initial_balance=money.NonNegativeMoney(currency=input_dto.currency,
                                                     value=input_dto.initial_balance),
            expires_at=expires_at,
        )
        uow.repo(aggregate.GiftCard).put(gift_card)
        _publish_events(uow, gift_card)
    _LOGGER.info("Gift card [%s] issued with code [%s]", gift_card.id, gift_card.code)
    return dto.GiftCardOutputDTO.from_entity(gift_card)


def redeem_gift_card(*, uow: "unit_of_work.UnitOfWork",
                      input_dto: dto.RedeemGiftCardInputDTO) -> dto.GiftCardOutputDTO:
    """Canjea `input_dto.amount` de la tarjeta identificada por `input_dto.code`."""
    with uow.transaction():
        code = value_objects.GiftCardCode(value=input_dto.code)
        gift_card = uow.repo(aggregate.GiftCard).get_by_code(code)
        gift_card.redeem(amount=money.PositiveMoney(currency=input_dto.currency,
                                                       value=input_dto.amount))
        uow.repo(aggregate.GiftCard).put(gift_card)
        _publish_events(uow, gift_card)
    _LOGGER.info("Gift card [%s] redeemed [%s %s]", gift_card.id,
                 input_dto.amount, input_dto.currency)
    return dto.GiftCardOutputDTO.from_entity(gift_card)


def get_gift_card(*, uow: "unit_of_work.UnitOfWork",
                   gift_card_id: "value_objects.GiftCardId") -> dto.GiftCardOutputDTO:
    """Lectura pura — no hay mutación ni eventos que publicar."""
    with uow.transaction():
        gift_card = uow.repo(aggregate.GiftCard).get(gift_card_id)
    return dto.GiftCardOutputDTO.from_entity(gift_card)


def _publish_events(uow: "unit_of_work.UnitOfWork",
                     entity: "aggregates.AggregateRoot") -> None:
    for event in entity.pull_events():
        uow.outbox.record(event)   # misma transacción — nunca fire-and-forget
```

Reglas aplicadas: una función por caso de uso, nombrada como verbo, `uow` siempre explícito
por parámetro (nada de DI de framework aquí), y **este módulo es el único lugar autorizado a
llamar `uow.repo(aggregate.GiftCard)` o `gift_card.redeem(...)`** — ni un futuro
`orchestrators/` ni un `entrypoints/` pueden saltarse esto.

---

## 5. Entrypoint (sin orquestador — llamada directa al servicio)

Como `issue_gift_card`/`redeem_gift_card` mutan un solo agregado, la ruta llama la función de
`services/` directo, sin capa de orquestación intermedia (§10.1):

```python
# commerce/entrypoints/web/public.py  (rutas añadidas al FastAPI app existente de commerce)
from typing import Annotated

import fastapi

from commerce.gift_card.services import dto, gift_card

app: "fastapi.FastAPI"   # ya existe, definido junto a orders/stock


@app.post("/gift-cards", response_model=dto.GiftCardOutputDTO, status_code=201)
def issue_gift_card(
    body: dto.IssueGiftCardInputDTO,
    idempotency_key: Annotated[str | None, fastapi.Header(alias="Idempotency-Key")] = None,
    uow: Annotated["unit_of_work.UnitOfWork", fastapi.Depends(get_uow)] = ...,
) -> dto.GiftCardOutputDTO:
    with uow.transaction(idempotency_key=idempotency_key):
        return gift_card.issue_gift_card(uow=uow, input_dto=body)


@app.post("/gift-cards/redeem", response_model=dto.GiftCardOutputDTO)
def redeem_gift_card(
    body: dto.RedeemGiftCardInputDTO,
    idempotency_key: Annotated[str | None, fastapi.Header(alias="Idempotency-Key")] = None,
    uow: Annotated["unit_of_work.UnitOfWork", fastapi.Depends(get_uow)] = ...,
) -> dto.GiftCardOutputDTO:
    with uow.transaction(idempotency_key=idempotency_key):
        return gift_card.redeem_gift_card(uow=uow, input_dto=body)
```

`Idempotency-Key` se agrega también en `redeem`, no solo en `issue`: la excepción del
estándar ("suspend/resume/delete son naturalmente idempotentes") no aplica acá — un reintento
de `redeem` sin key descontaría saldo dos veces, así que sí necesita la key igual que una
creación. La ruta abre su propia `uow.transaction(idempotency_key=...)` alrededor de la
llamada al servicio; como `issue_gift_card`/`redeem_gift_card` abren su propio
`with uow.transaction():` interno, ese segundo `with` simplemente se une a la transacción ya
abierta (re-entrancia de §8) — un solo commit.

---

## 6. Lo que falta para dejarlo productivo (no incluido arriba, pero es el siguiente paso)

1. **Migración**: `alembic revision --autogenerate -m "add gift_card table"` — nunca escrita
   a mano.
2. **Import-linter**: `gift_card` recibe los mismos 6 contratos que cualquier otro
   subcontexto (pureza de dominio, layering, independencia entre subcontextos, independencia
   de `commons`, entrypoints delgados, orquestadores delgados) — no un subconjunto.
3. **Tests**: unitarios de `GiftCard.redeem()`/`.expire()` contra un `FakeGiftCardRepository`
   (sin DB), e integración de `_to_orm`/`_to_entity` y `version_id_col` contra Postgres real
   vía testcontainers — nunca SQLite.
