# Cancelar orden y liberar stock reservado de forma atómica

## Idea general

"Atómico" aquí significa: **la transición de estado de `Order` a `CANCELLED` y la liberación de las reservas en `Stock` se confirman juntas, en la misma transacción de base de datos, o ninguna de las dos**. Eso descarta hacerlo con dos llamadas independientes a dos repositorios con dos `commit()` — si el segundo falla, te quedas con una orden cancelada pero el stock nunca liberado (o viceversa).

La forma estándar de resolver esto en hexagonal/DDD es:

1. La lógica de negocio (transición de estado, reglas de "¿puedo cancelar esto?", liberar cantidades) vive en los **agregados** (`Order`, `Stock`), no en el service.
2. Un **application service** (caso de uso) orquesta: carga los agregados via repositorios, invoca sus métodos de dominio, y no contiene reglas de negocio él mismo.
3. Todo el caso de uso corre dentro de un **Unit of Work**, que es el único que abre transacción y hace `commit()`/`rollback()`. Un solo `commit()` al final ⇒ atomicidad garantizada por la transacción de Postgres.
4. Se usa **bloqueo optimista** (columna `version`) en `Stock` para que dos cancelaciones/reservas concurrentes sobre el mismo SKU no se pisen.
5. `Order.cancel()` y `Stock.release_reservation()` son **idempotentes** para que reintentos (timeouts de red, reintentos de consumidor, doble click del usuario) no rompan nada ni lancen error.

Esto asume que `Order` y `Stock` viven en el mismo servicio/base de datos (mismo bounded context o al menos mismo esquema Postgres), que es el caso típico. Al final dejo la nota de qué cambia si `Stock` fuera un servicio/BD distinta.

---

## 1. Dominio

### 1.1 Agregado `Order`

```python
# orders/domain/model.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    DELIVERED = "DELIVERED"


class InvalidOrderTransition(Exception):
    """La orden no puede pasar al estado solicitado desde su estado actual."""


@dataclass
class OrderLine:
    sku: str
    quantity: int
    reservation_id: UUID  # id de la reserva creada en Stock al confirmar la línea


@dataclass
class Order:
    """Aggregate root. Consistency boundary: sus propias líneas y estado."""

    id: UUID
    customer_id: UUID
    status: OrderStatus
    lines: list[OrderLine]
    version: int = 0
    events: list[object] = field(default_factory=list, repr=False)

    _CANCELLABLE_STATES = {OrderStatus.PENDING, OrderStatus.CONFIRMED}

    def cancel(self, reason: str = "") -> None:
        if self.status == OrderStatus.CANCELLED:
            # idempotente: cancelar dos veces no es un error, es un no-op
            return

        if self.status not in self._CANCELLABLE_STATES:
            raise InvalidOrderTransition(
                f"No se puede cancelar una orden en estado {self.status.value}"
            )

        self.status = OrderStatus.CANCELLED
        self.events.append(
            OrderCancelled(
                order_id=self.id,
                reason=reason,
                lines=[(l.sku, l.quantity, l.reservation_id) for l in self.lines],
                occurred_at=datetime.now(timezone.utc),
            )
        )
```

```python
# orders/domain/events.py
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class OrderCancelled:
    order_id: UUID
    reason: str
    lines: list[tuple[str, int, UUID]]  # (sku, quantity, reservation_id)
    occurred_at: datetime
```

Notar: `Order` **no sabe nada de `Stock`**. No importa el módulo de stock, no llama a nada de stock. Su único trabajo es decidir si la transición es válida y registrar el hecho de dominio (`OrderCancelled`). El acoplamiento entre los dos agregados vive en la capa de aplicación, no en el dominio.

### 1.2 Agregado `Stock`

```python
# stock/domain/model.py
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID


class InsufficientStock(Exception):
    pass


@dataclass
class Reservation:
    id: UUID
    order_id: UUID
    quantity: int
    released: bool = False


@dataclass
class Stock:
    """Aggregate root por SKU. version = bloqueo optimista."""

    sku: str
    quantity_on_hand: int
    quantity_reserved: int
    reservations: dict[UUID, Reservation]
    version: int = 0
    events: list[object] = field(default_factory=list, repr=False)

    @property
    def quantity_available(self) -> int:
        return self.quantity_on_hand - self.quantity_reserved

    def reserve(self, reservation_id: UUID, order_id: UUID, quantity: int) -> None:
        if quantity > self.quantity_available:
            raise InsufficientStock(f"Stock insuficiente para SKU {self.sku}")
        self.quantity_reserved += quantity
        self.reservations[reservation_id] = Reservation(reservation_id, order_id, quantity)

    def release_reservation(self, reservation_id: UUID) -> None:
        """Libera una reserva. Idempotente: si no existe o ya se liberó, no hace nada."""
        reservation = self.reservations.get(reservation_id)
        if reservation is None or reservation.released:
            return

        reservation.released = True
        self.quantity_reserved -= reservation.quantity
        self.events.append(
            StockReleased(
                sku=self.sku,
                reservation_id=reservation_id,
                quantity=reservation.quantity,
            )
        )
```

```python
# stock/domain/events.py
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class StockReleased:
    sku: str
    reservation_id: UUID
    quantity: int
```

La liberación se hace **por `reservation_id`**, no restando "a ojo" una cantidad del total. Esto es clave: si guardás únicamente un contador (`quantity_reserved -= n`) sin trackear qué reserva es cuál, un reintento del caso de uso restaría dos veces y te dejaría con stock fantasma. Modelar la reserva como una entidad dentro del agregado `Stock` es lo que te da la idempotencia gratis.

---

## 2. Puertos (repositorios + Unit of Work)

```python
# shared/unit_of_work.py
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol
from uuid import UUID

from orders.domain.model import Order
from stock.domain.model import Stock


class OrderRepository(Protocol):
    async def get(self, order_id: UUID) -> Order | None: ...
    def add(self, order: Order) -> None: ...


class StockRepository(Protocol):
    async def get_by_sku(self, sku: str) -> Stock | None: ...
    def add(self, stock: Stock) -> None: ...


class ConcurrencyConflict(Exception):
    """Otro proceso modificó el mismo agregado (Stock/Order) en paralelo."""


class AbstractUnitOfWork(ABC):
    orders: OrderRepository
    stock: StockRepository

    async def __aenter__(self) -> "AbstractUnitOfWork":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.rollback()

    @abstractmethod
    async def commit(self) -> None: ...

    @abstractmethod
    async def rollback(self) -> None: ...
```

El punto de este puerto: **`commit()` sólo se llama una vez, al final del caso de uso**, después de tocar ambos agregados. Si nunca se llega a llamar (excepción en el medio), `__aexit__` hace rollback y no queda nada a medias en la base.

---

## 3. Application service (caso de uso)

```python
# orders/application/cancel_order.py
from uuid import UUID

from orders.domain.model import InvalidOrderTransition
from shared.unit_of_work import AbstractUnitOfWork


class OrderNotFound(Exception):
    pass


async def cancel_order(order_id: UUID, uow: AbstractUnitOfWork, reason: str = "") -> None:
    async with uow:
        order = await uow.orders.get(order_id)
        if order is None:
            raise OrderNotFound(str(order_id))

        order.cancel(reason=reason)  # regla de negocio + emite OrderCancelled

        for line in order.lines:
            stock = await uow.stock.get_by_sku(line.sku)
            if stock is None:
                # dato inconsistente preexistente; no debería frenar la cancelación
                continue
            stock.release_reservation(line.reservation_id)

        await uow.commit()  # <- único punto de confirmación: Order + N Stock juntos
```

Esto es toda la orquestación. Fijate qué **no** hace: no valida reglas de negocio (`InvalidOrderTransition` la lanza el propio `Order`), no calcula cantidades (`Stock` lo hace), no abre transacciones manualmente. Solo carga agregados, llama métodos de dominio y confirma. Si `order.cancel()` lanza `InvalidOrderTransition`, el `async with uow` nunca llega a `commit()` y hace rollback automáticamente al salir por excepción — así que aunque ya se hubiera tocado algún `Stock` antes de la excepción, nada se persiste.

---

## 4. Infraestructura: Unit of Work + repositorios con SQLAlchemy async

```python
# shared/sqlalchemy_uow.py
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from orders.adapters.repository import SqlAlchemyOrderRepository
from stock.adapters.repository import SqlAlchemyStockRepository
from shared.unit_of_work import AbstractUnitOfWork


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        self.session: AsyncSession = self._session_factory()
        self.orders = SqlAlchemyOrderRepository(self.session)
        self.stock = SqlAlchemyStockRepository(self.session)
        return await super().__aenter__()

    async def __aexit__(self, *exc_info) -> None:
        await super().__aexit__(*exc_info)
        await self.session.close()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
```

```python
# stock/adapters/repository.py
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from stock.domain.model import Stock


class SqlAlchemyStockRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_sku(self, sku: str) -> Stock | None:
        # Asumiendo mapeo imperativo Stock <-> tabla stock (ver más abajo)
        return await self.session.get(Stock, sku)

    def add(self, stock: Stock) -> None:
        self.session.add(stock)
```

```python
# orders/adapters/repository.py
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from orders.domain.model import Order


class SqlAlchemyOrderRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, order_id: UUID) -> Order | None:
        return await self.session.get(Order, order_id)

    def add(self, order: Order) -> None:
        self.session.add(order)
```

### Bloqueo optimista en `stock`

```python
# stock/adapters/orm.py
from sqlalchemy import Table, Column, String, Integer, MetaData
from sqlalchemy.orm import registry

metadata = MetaData()
mapper_registry = registry(metadata=metadata)

stock_table = Table(
    "stock",
    metadata,
    Column("sku", String, primary_key=True),
    Column("quantity_on_hand", Integer, nullable=False),
    Column("quantity_reserved", Integer, nullable=False),
    Column("version", Integer, nullable=False, server_default="0"),
)

mapper_registry.map_imperatively(
    Stock,
    stock_table,
    version_id_col=stock_table.c.version,  # <- clave: SQLAlchemy incrementa
    version_id_generator=False,            # version y agrega WHERE version = :v
)
```

Con `version_id_col`, cada `UPDATE` que SQLAlchemy genera al hacer `commit()` incluye `WHERE version = <version cargada>`. Si otro proceso ya modificó esa fila (por ejemplo, otra cancelación concurrente sobre el mismo SKU, o una nueva reserva), el `UPDATE` afecta 0 filas y SQLAlchemy lanza `StaleDataError`. Es la forma estándar de proteger un agregado contra *lost updates* sin tomar locks explícitos.

Conviene traducir esa excepción de infraestructura a algo del dominio/aplicación en el borde del adaptador:

```python
# shared/sqlalchemy_uow.py (extendido)
from sqlalchemy.orm.exc import StaleDataError
from shared.unit_of_work import ConcurrencyConflict

class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    ...
    async def commit(self) -> None:
        try:
            await self.session.commit()
        except StaleDataError as exc:
            await self.session.rollback()
            raise ConcurrencyConflict from exc
```

**Alternativa (o complemento):** si tu SKU tiene mucha contención (muchas reservas/liberaciones concurrentes), en vez de optimista podés bloquear la fila al leerla dentro de la misma transacción con `SELECT ... FOR UPDATE`:

```python
await self.session.execute(
    select(Stock).where(Stock.sku == sku).with_for_update()
)
```

Esto serializa el acceso a ese SKU durante la transacción en vez de fallar-y-reintentar. Para el flujo de "cancelar y liberar" (que reduce contención, no la aumenta) el bloqueo optimista suele ser suficiente y más barato; `FOR UPDATE` lo reservaría para el camino de *reservar* stock, que es el que compite de verdad.

---

## 5. Adaptador de entrada: endpoint FastAPI

```python
# orders/entrypoints/fastapi_routes.py
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from orders.application.cancel_order import cancel_order, OrderNotFound
from orders.domain.model import InvalidOrderTransition
from shared.unit_of_work import ConcurrencyConflict
from shared.dependencies import get_uow  # provee un SqlAlchemyUnitOfWork por request

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("/{order_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_order_endpoint(
    order_id: UUID,
    uow=Depends(get_uow),
) -> None:
    try:
        await cancel_order(order_id, uow)
    except OrderNotFound:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    except InvalidOrderTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ConcurrencyConflict:
        raise HTTPException(
            status_code=409,
            detail="Conflicto de concurrencia liberando stock, reintente",
        )
```

Como `Order.cancel()` y `Stock.release_reservation()` son idempotentes, este endpoint **también es idempotente**: si el cliente reintenta por timeout, la segunda llamada devuelve 204 sin duplicar ninguna liberación. No hace falta una tabla de idempotencia adicional para este caso puntual porque el propio modelo de dominio absorbe el reintento; si quisieras protegerte además de reintentos con distinto payload (ej. distinta `reason`), agregá un `Idempotency-Key` de header persistido aparte, pero para este caso de uso no es necesario.

---

## 6. Por qué esto es atómico

- Un único `AsyncSession` / transacción Postgres para todo el caso de uso: `order` y cada `stock` tocado se agregan a la misma `Session`, y `await uow.commit()` es el único `COMMIT` SQL que se ejecuta. Postgres garantiza que ese `COMMIT` es todo-o-nada.
- Si `Stock.release_reservation` para la segunda línea de una orden de 3 líneas explota (por ejemplo `StaleDataError` en la línea 2), nunca se llega a `uow.commit()`, y `__aexit__` hace `rollback()` — la línea 1, que sí se había mutado en memoria/flush, también se revierte porque no se confirmó nada en disco.
- El bloqueo optimista (`version`) evita que dos transacciones concurrentes sobre el mismo SKU (p. ej. cancelar la orden A libera 5 unidades del SKU X justo cuando se está reservando stock del SKU X para la orden B) produzcan un *lost update* silencioso.
- La idempotencia en el dominio evita que una **misma** operación reintentada rompa la aritmética del stock.

---

## 7. Test del caso de uso (con repos fake, sin DB)

```python
# tests/unit/test_cancel_order.py
import pytest
from uuid import uuid4

from orders.application.cancel_order import cancel_order, OrderNotFound
from orders.domain.model import Order, OrderLine, OrderStatus
from stock.domain.model import Stock, Reservation


class FakeOrderRepository:
    def __init__(self, orders):
        self._orders = {o.id: o for o in orders}

    async def get(self, order_id):
        return self._orders.get(order_id)

    def add(self, order):
        self._orders[order.id] = order


class FakeStockRepository:
    def __init__(self, stocks):
        self._stocks = {s.sku: s for s in stocks}

    async def get_by_sku(self, sku):
        return self._stocks.get(sku)

    def add(self, stock):
        self._stocks[stock.sku] = stock


class FakeUnitOfWork:
    def __init__(self, orders, stock):
        self.orders = orders
        self.stock = stock
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        pass

    async def commit(self):
        self.committed = True

    async def rollback(self):
        pass


@pytest.mark.asyncio
async def test_cancel_order_releases_reserved_stock():
    order_id, reservation_id = uuid4(), uuid4()
    order = Order(
        id=order_id,
        customer_id=uuid4(),
        status=OrderStatus.CONFIRMED,
        lines=[OrderLine(sku="SKU-1", quantity=3, reservation_id=reservation_id)],
    )
    stock = Stock(
        sku="SKU-1",
        quantity_on_hand=10,
        quantity_reserved=3,
        reservations={reservation_id: Reservation(reservation_id, order_id, 3)},
    )
    uow = FakeUnitOfWork(FakeOrderRepository([order]), FakeStockRepository([stock]))

    await cancel_order(order_id, uow)

    assert order.status == OrderStatus.CANCELLED
    assert stock.quantity_reserved == 0
    assert stock.quantity_available == 10
    assert uow.committed is True


@pytest.mark.asyncio
async def test_cancel_order_not_found_raises():
    uow = FakeUnitOfWork(FakeOrderRepository([]), FakeStockRepository([]))
    with pytest.raises(OrderNotFound):
        await cancel_order(uuid4(), uow)


@pytest.mark.asyncio
async def test_cancel_order_is_idempotent():
    order_id, reservation_id = uuid4(), uuid4()
    order = Order(
        id=order_id,
        customer_id=uuid4(),
        status=OrderStatus.CANCELLED,  # ya cancelada
        lines=[OrderLine(sku="SKU-1", quantity=3, reservation_id=reservation_id)],
    )
    stock = Stock(
        sku="SKU-1",
        quantity_on_hand=10,
        quantity_reserved=0,
        reservations={reservation_id: Reservation(reservation_id, order_id, 3, released=True)},
    )
    uow = FakeUnitOfWork(FakeOrderRepository([order]), FakeStockRepository([stock]))

    await cancel_order(order_id, uow)  # no debe lanzar

    assert stock.quantity_reserved == 0
```

---

## 8. Si `Stock` estuviera en otro bounded context / microservicio

Todo lo anterior asume que `Order` y `Stock` comparten base de datos y por lo tanto una transacción ACID real. Si en tu arquitectura `Stock` es un servicio aparte (otra base de datos, quizás otro equipo), **no existe una transacción distribuida real** salvo que metas 2PC (que casi nadie usa por buenas razones). Ahí el patrón estándar cambia:

1. `cancel_order` sólo toca el agregado `Order` y, dentro de la **misma transacción** que lo persiste, inserta el evento `OrderCancelled` en una tabla **outbox** (patrón *Transactional Outbox*). Esto sigue siendo atómico porque `Order` + outbox están en la misma base.
2. Un relay/publisher (poller o CDC tipo Debezium) publica ese evento a un broker (SQS/Kafka/etc.) de forma asíncrona.
3. El servicio de `Stock` consume `OrderCancelled` de forma **idempotente** (usando `reservation_id` como clave de deduplicación, igual que hace `release_reservation` acá) y libera el stock en su propia transacción.
4. Si necesitás confirmar que el stock efectivamente se liberó (por ejemplo para notificar al cliente), el consumidor publica `StockReleased` y quien lo necesite reacciona a eso — o adoptás explícitamente un patrón de **Saga** con pasos de compensación si hay más de dos pasos encadenados.

Esto te da **atomicidad local en cada paso + consistencia eventual global**, que es lo mejor que se puede lograr entre bounded contexts separados sin acoplarlos con una transacción distribuida. La clave para que "eventual" no se sienta como "roto" es la idempotencia de los consumidores (ya la tenés modelada en el dominio de este mismo ejemplo) y tener un job de reconciliación/alerta para sagas que se queden a mitad de camino.

---

## Resumen de las piezas y dónde poner cada cosa

| Capa | Responsabilidad | Archivo de ejemplo |
|---|---|---|
| Dominio `Order` | Reglas de transición de estado, emite `OrderCancelled` | `orders/domain/model.py` |
| Dominio `Stock` | Reglas de reserva/liberación, idempotencia por `reservation_id`, emite `StockReleased` | `stock/domain/model.py` |
| Application service | Orquesta: carga agregados, invoca métodos de dominio, un solo `commit()` | `orders/application/cancel_order.py` |
| Unit of Work | Único punto de `commit()`/`rollback()`, límite de transacción | `shared/unit_of_work.py`, `shared/sqlalchemy_uow.py` |
| Repositorios | Persistencia de cada agregado, bloqueo optimista vía `version` | `orders/adapters/repository.py`, `stock/adapters/repository.py` |
| Entrypoint FastAPI | Traduce excepciones de dominio/aplicación a HTTP | `orders/entrypoints/fastapi_routes.py` |

La atomicidad no la da ningún "truco" especial: la da que **el caso de uso completo vive dentro de un único `async with uow` con un único `commit()` al final**, que las reglas de negocio estén en los agregados (así el service no puede "olvidarse" de validar algo), y que tanto la transición de `Order` como la liberación en `Stock` sean idempotentes para que los reintentos no generen inconsistencias incluso fuera de la transacción (por ejemplo, si el cliente HTTP reintenta después de un timeout de red aunque el commit ya haya sucedido del lado del servidor).
