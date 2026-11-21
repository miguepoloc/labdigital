# Por qué tu evento nunca llega a SQS

`record_event()` **solo mete el evento en una lista en memoria del agregado** (`AggregateRoot._events`, ver `commons/domain/aggregates.py`). No escribe nada en la base de datos, no toca el outbox, no publica nada. Es literalmente:

```python
class AggregateRoot[IdT](entities.Entity[IdT]):
    _events: list[domain_events.DomainEvent] = pydantic.PrivateAttr(default_factory=list)

    def record_event(self, event: domain_events.DomainEvent) -> None:
        self._events.append(event)
```

Así que "el evento se registra pero nunca llega a SQS" no es un bug raro — es el comportamiento *esperado* de `record_event()` en solitario. El pipeline completo, según el estándar, es:

```
aggregate.record_event(...)          # 1. en memoria
  → service.pull_events()            # 2. lo saca del agregado
  → uow.outbox.record(event)         # 3. INSERT en outbox_events, misma transacción
  → relay (cron)                     # 4. lee filas sin publicar, publica a SNS/EventBridge
  → SNS topic → SQS queue filtrada   # 5. fan-out al consumidor
```

Si ves el evento registrado pero nunca en SQS, el corte está en alguno de los pasos 2–5. En orden de probabilidad:

## Causa más común: falta el paso 2+3 (pull_events + outbox.record)

Esta es la causa que el propio estándar marca como el error #1 a vigilar — está en sus "non-negotiables":

> Un `record_event(...)` sin su correspondiente `pull_events()` + escritura al outbox en la misma transacción está mal, siempre — es código muerto que parece vivo (`sona-sso-backend` lo mandó a producción exactamente así).

Revisa tu `services/<subcontext>.py`. Si tu función de caso de uso hace esto:

```python
# MAL — el evento se registra en el agregado y ahí muere
def reserve_stock(*, uow, sku, quantity: int) -> None:
    with uow.transaction():
        stock = uow.repo(aggregate.Stock).get_by_sku(sku)
        stock.reserve(quantity)          # dentro de reserve() hay un record_event()
        uow.repo(aggregate.Stock).put(stock)
    # <- nunca se llama pull_events(), nunca se escribe al outbox
```

...el evento queda atrapado en `stock._events` y se pierde cuando el objeto sale de scope. Nadie lo lee jamás.

**Arreglo** — añade el drenaje dentro de la misma transacción:

```python
# BIEN
def reserve_stock(*, uow: "unit_of_work.UnitOfWork", sku: "commerce_value_objects.Sku",
                   quantity: int) -> None:
    with uow.transaction():
        stock = uow.repo(aggregate.Stock).get_by_sku(sku)
        stock.reserve(quantity)                 # raises InsufficientStockError → rollback
        uow.repo(aggregate.Stock).put(stock)
        _publish_events(uow, stock)              # <- esto faltaba


def _publish_events(uow: "unit_of_work.UnitOfWork", entity: "aggregates.AggregateRoot") -> None:
    for event in entity.pull_events():
        uow.outbox.record(event)   # INSERT en outbox_events, misma transacción con uow.transaction()
```

Puntos clave de este fix:

- `pull_events()` y `uow.outbox.record(event)` deben ir **dentro** del mismo bloque `with uow.transaction():` que la mutación del agregado. Si el commit del agregado tiene éxito pero el outbox no se escribe (o viceversa), pierdes atomicidad — exactamente el modo de fallo que el patrón Outbox existe para evitar en Postgres (que no te da un write transaccional cruzado contra una cola externa).
- `services/<subcontext>.py` es el **único** lugar permitido para llamar `uow.repo(...)` o métodos del agregado — así que también es el único lugar correcto para drenar los eventos. Si el `record_event` vive en un agregado invocado desde un orquestador, el orquestador nunca debe tocar `pull_events()` directamente: debe ser la función de `services/` la que lo haga, como parte de su propia transacción.

## Segunda causa posible: el evento no es un `IntegrationEvent`

El outbox y el relay **solo publican filas cuyo evento es un `IntegrationEvent`**, no cualquier `DomainEvent`:

```python
class DomainEvent(value_objects.ValueObject):
    event_id: uuid.UUID
    occurred_at: value_objects.PosixTime
    ...

class IntegrationEvent(DomainEvent):
    """A DomainEvent promoted to cross a bounded-context boundary — su propia clase, un
    contrato público, no el evento interno reusado tal cual. Solo las subclases de
    IntegrationEvent son relayed fuera del outbox."""
```

Si tu clase de evento hereda directo de `DomainEvent` (para consumo puramente interno del propio agregado/subcontexto) en lugar de `IntegrationEvent`, el relay la va a ignorar aunque sí esté en la tabla `outbox_events` — nunca sale del proceso hacia SNS/SQS.

**Arreglo** — si este evento necesita salir del bounded context (que es el caso si esperas verlo en SQS), su clase debe heredar de `IntegrationEvent`, no de `DomainEvent`:

```python
# commerce/stock/domain/model/events.py
from commons.domain import events as domain_events


class StockReserved(domain_events.IntegrationEvent):   # <- IntegrationEvent, no DomainEvent
    stock_id: "value_objects.StockId"
    sku: "commerce_value_objects.Sku"
    quantity: int
```

## Tercera causa posible: el relay no está corriendo, o el filtro SQS no matchea

Si ya confirmaste que la fila sí llega a `outbox_events` (`published_at IS NULL`) y el evento sí es un `IntegrationEvent`, el problema está aguas abajo del código de dominio/aplicación:

1. **El relay (cron) no está desplegado o no está corriendo.** Es el único componente que lee `outbox_events` y publica a SNS/EventBridge — sin él, las filas se acumulan con `published_at = NULL` para siempre. Revisa que el cron/lambda del relay exista y tenga logs recientes.
2. **La política de filtro de la suscripción SQS no matchea `event_type`.** El fan-out es "SNS topic por producto, cola SQS filtrada por consumidor" — si la suscripción SQS→SNS tiene un filter policy que no incluye el `event_type` de tu nuevo evento (recuerda: `event_type` es un `computed_field` = nombre de la clase), el mensaje se publica al tópico pero nunca llega a tu cola.
3. **Confundir "publicado" con "consumido".** Si el relay sí publicó pero el Lambda consumidor está fallando silenciosamente (o la DLQ se lo llevó), el mensaje "llegó a SQS" en el sentido de haber pasado por la cola, pero puede parecer que nunca llegó si solo estás mirando logs del consumidor. Revisa la cola y su DLQ directamente en la consola, no solo los logs de aplicación.

## Checklist de diagnóstico, en orden

1. ¿El evento aparece en la tabla `outbox_events`? Si no → falta `pull_events()` + `uow.outbox.record(event)` en la misma transacción (causa #1, la más común).
2. Si aparece pero `published_at` sigue `NULL` para siempre → o el evento no es `IntegrationEvent` (causa #2) y el relay lo ignora a propósito, o el relay no está corriendo (causa #3.1).
3. Si `published_at` ya tiene timestamp (o sea, sí se publicó a SNS/EventBridge) pero no aparece en tu cola SQS → revisa el filter policy de la suscripción (causa #3.2) y la DLQ (causa #3.3).

En el 90% de los casos que este estándar ha visto en producción (`sona-sso-backend` lo hizo exactamente así), la causa es la #1: `record_event()` sin su `pull_events()` correspondiente. Empieza ahí.
