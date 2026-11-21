# Cancelar una orden liberando stock reservado, atómicamente

## Qué tier de orquestación es esto

Recorriendo el árbol de decisión (§10, `entrypoints-and-orchestration.md`):

```
¿La orden muta exactamente un agregado?
└── NO — muta Order (status → CANCELLED) Y Stock (available_quantity += qty)
    └── ¿Mismo producto? SÍ (ambos viven en `commerce/`)
        → §10.2: orquestador a nivel de producto, transacción atómica
          vía `uow.transaction()` anidado.
```

Es el mismo tier que "confirmar una orden" (que reserva stock) — pero **no es el mismo
código invertido**. Hay una diferencia de negocio real que hay que respetar:

> **Solo se libera stock si efectivamente se había reservado.** El stock se reserva en
> `confirm_order`, cuando la orden pasa a `CONFIRMED`. Si una orden todavía está `PENDING`
> (nunca confirmada) y se cancela, no hay nada que liberar — liberar stock en ese caso
> incrementaría `available_quantity` sin que nunca se hubiera decrementado, corrompiendo el
> inventario. El orquestador tiene que mirar el estado *antes* de cancelar para decidir si el
> segundo agregado (`Stock`) participa o no en esta transacción.

Y la regla que nunca se relaja (§1.5 / import-linter contract 6, restated en §10.2): **el
orquestador llama funciones de `services/` de cada subcontexto — nunca `uow.repo(...)` ni un
método del agregado directamente.** Todo el código de abajo respeta eso: el orquestador solo
importa `orders` y `stock` (los módulos de servicio), nunca `aggregate.Order`/`aggregate.Stock`.

---

## 1. Dominio — `commerce/orders`

`Stock.release(quantity)` **ya existe** en el agregado `Stock` del golden path (ver
`domain-and-application.md` §5.3) — no hay que tocar `commerce/stock/domain/`. Lo que falta es
el lado de `Order`: el método de comando `cancel()`, su excepción de transición inválida, y el
evento.

```python
# commerce/orders/domain/model/exceptions.py
from commons.domain import exceptions


class OrderCannotBeCancelledError(exceptions.ConflictError):
    def __init__(self, *, order_id: "value_objects.OrderId",
                 status: "value_objects.OrderStatus") -> None:
        super().__init__(
            f"Order [{order_id}] cannot be cancelled from status [{status}].",
            code="ORDER_CANNOT_BE_CANCELLED",
        )
```

```python
# commerce/orders/domain/model/events.py  (excerpt — añadido a lo ya existente)
from commons.domain import events as domain_events

from commerce.orders.domain.model import value_objects


class OrderCancelled(domain_events.DomainEvent):
    order_id: value_objects.OrderId
    lines: list[value_objects.OrderLine]
    previous_status: value_objects.OrderStatus
```

```python
# commerce/orders/domain/model/aggregate.py  (excerpt — añadido a Order)
from commerce.orders.domain.model import events, exceptions, value_objects

_CANCELLABLE_STATUSES = (value_objects.OrderStatus.PENDING, value_objects.OrderStatus.CONFIRMED)


class Order(aggregates.AggregateRoot[value_objects.OrderId]):
    lines: list[value_objects.OrderLine]
    status: value_objects.OrderStatus

    def cancel(self) -> None:
        if self.status not in _CANCELLABLE_STATUSES:
            raise exceptions.OrderCannotBeCancelledError(order_id=self.id, status=self.status)
        previous_status = self.status
        self.status = value_objects.OrderStatus.CANCELLED
        self.record_event(events.OrderCancelled(
            order_id=self.id, lines=self.lines, previous_status=previous_status,
        ))
```

Igual que `Stock.reserve`/`Stock.release`: guarda con una excepción de dominio nombrada, muta
estado, registra el evento — sin I/O, sin `uow`, sin sesión. `previous_status` viaja en el
evento porque el orquestador lo necesita para decidir si libera stock (ver más abajo) sin tener
que volver a leer el agregado.

---

## 2. Application layer — `services/`

Cada función nueva sigue siendo la única autorizada a llamar `uow.repo(...)` o un método del
agregado *de su propio subcontexto*.

```python
# commerce/orders/services/orders.py  (excerpt — añadido a lo ya existente)
from commerce.orders.domain.model import aggregate
from commerce.orders.services import dto


def cancel_order(*, uow: "unit_of_work.UnitOfWork",
                  order_id: "value_objects.OrderId") -> dto.OrderOutputDTO:
    with uow.transaction():
        order = uow.repo(aggregate.Order).get(order_id)
        order.cancel()                      # raises OrderCannotBeCancelledError → rollback
        uow.repo(aggregate.Order).put(order)
        _publish_events(uow, order)
    _LOGGER.info("Order [%s] cancelled", order.id)
    return dto.OrderOutputDTO.from_entity(order)
```

```python
# commerce/stock/services/stock.py  (excerpt — añadido a lo ya existente, simétrico a reserve_stock)
def release_stock(*, uow: "unit_of_work.UnitOfWork", sku: "commerce_value_objects.Sku",
                   quantity: int) -> None:
    with uow.transaction():
        stock = uow.repo(aggregate.Stock).get_by_sku(sku)
        stock.release(quantity)
        uow.repo(aggregate.Stock).put(stock)
        _publish_events(uow, stock)
```

Cada una abre su propio `with uow.transaction():` — cuando se llaman dentro de una transacción
ya abierta por el orquestador, esa llamada simplemente hace join a la transacción externa
(§8: `if self._session is not None: yield; return`). Fuera de un orquestador, cada función
sigue siendo perfectamente utilizable de forma standalone y atómica por sí misma.

---

## 3. Orquestador — `commerce/services/cancel_order_orchestrator.py`

```python
# commerce/services/cancel_order_orchestrator.py
from commons.adapters import logs, unit_of_work

from commerce.orders.domain.model import value_objects as order_value_objects
from commerce.orders.services import dto, orders
from commerce.stock.services import stock

_LOGGER = logs.get_logger()


def cancel_order(*, uow: unit_of_work.UnitOfWork,
                  order_id: "order_value_objects.OrderId") -> dto.OrderOutputDTO:
    with uow.transaction():
        order_before = orders.get_order(uow=uow, order_id=order_id)
        had_reserved_stock = order_before.status is order_value_objects.OrderStatus.CONFIRMED

        cancelled_order = orders.cancel_order(uow=uow, order_id=order_id)

        if had_reserved_stock:
            for line in cancelled_order.lines:
                stock.release_stock(uow=uow, sku=line.sku, quantity=line.quantity)

        return cancelled_order
```

Notar la simetría deliberada con `confirm_order_orchestrator.py` del golden path, y la única
diferencia real:

- En `confirm_order`, el orden es reservar-stock-primero, confirmar-al-final: si
  `stock.reserve_stock` falla por `InsufficientStockError`, `Order` nunca llega a confirmarse.
- En `cancel_order`, el orden es cancelar-primero, liberar-después: la validación de negocio
  que puede fallar (¿esta orden está en un estado cancelable?) vive en `Order`, así que
  `orders.cancel_order` corre primero — si lanza `OrderCannotBeCancelledError`, nunca se toca
  `Stock`. La liberación de stock, condicionada a `had_reserved_stock`, es la parte que
  virtualmente no falla en operación normal.
- `had_reserved_stock` se decide leyendo el estado **antes** de cancelar, dentro de la misma
  transacción — evita el bug de liberar stock de una orden que nunca pasó por `confirm_order`
  y por lo tanto nunca reservó nada.

Igual que en el ejemplo de `confirm_order`: el orquestador nunca ve `Order` ni `Stock` como
objetos de dominio, solo sus DTOs (`cancelled_order`, `order_before`) y sus excepciones. Si
`orders.cancel_order` o `stock.release_stock` lanzan una excepción, todo el bloque hace
rollback atómicamente — la orden nunca queda `CANCELLED` con el stock sin liberar, ni viceversa.

**Concurrencia:** si otra request modificó `Stock` o `Order` entre la lectura y el `put()`,
`version_id_col` hace que `flush()` lance `StaleDataError` → el repositorio lo traduce a
`ConcurrentModificationError` (§8.1) → propaga, rollback de toda la cadena, HTTP 409 al cliente.
No hay riesgo de pisar una reserva/liberación concurrente en silencio.

---

## 4. Entrypoint

Como toca dos agregados, el router llama al orquestador — **no** a `orders.cancel_order`
directamente (eso sería saltarse §10.2 y dejar el stock sin liberar).

```python
# commerce/orders/entrypoints/web/public.py  (excerpt — añadido a lo ya existente)
import uuid
from typing import Annotated

import fastapi

from commerce.orders.domain.model import value_objects as order_value_objects
from commerce.orders.services import dto
from commerce.services import cancel_order_orchestrator


@app.post("/orders/{order_id}/cancel", response_model=dto.OrderOutputDTO)
def cancel_order(
    order_id: uuid.UUID,
    user: Annotated["authentication.AuthenticatedUser", fastapi.Depends(require_jwt)],
    uow: Annotated["unit_of_work.UnitOfWork", fastapi.Depends(get_uow)],
) -> dto.OrderOutputDTO:
    return cancel_order_orchestrator.cancel_order(
        uow=uow, order_id=order_value_objects.OrderId(value=order_id),
    )
```

Ruteo sigue siendo delgado: parsea el input, llama exactamente una función (el orquestador,
que a su vez es la única capa autorizada a coordinar los dos subcontextos), retorna el DTO. Sin
import de `domain/` aquí — contrato 5 de import-linter sigue intacto.

---

## Resumen de por qué está estructurado así

| Decisión | Regla del estándar que la justifica |
|---|---|
| Orquestador en `commerce/services/`, no en `orders/` ni `stock/` | §10.2 — coordinación multi-agregado del mismo producto vive a nivel de producto |
| Orquestador llama `orders.cancel_order`/`stock.release_stock`, nunca `uow.repo(...)` | §1.5 y §10.2, enforced por import-linter contract 6 |
| Todo dentro de un solo `with uow.transaction():` | §8 — nested transactions: la llamada interna hace join, un solo commit/rollback |
| `Stock.release` no se toca (ya existe) | §5.3 del golden path — el comando ya estaba modelado simétrico a `reserve` |
| `had_reserved_stock` se evalúa antes de cancelar | Regla de negocio: solo se libera lo que realmente se reservó (en `confirm_order`) |
| Excepciones narrow (`OrderCannotBeCancelledError`) | §5.5 — una clase por transición inválida, no un enum de estados genérico |
| `version_id_col` protege ambos `put()` | §8.1 — optimistic concurrency en cada `AggregateRoot`, no solo en `Stock` |
