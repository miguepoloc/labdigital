# Por qué `record_event()` no llega a SQS (y cómo arreglarlo)

Cuando un evento se registra en el agregado pero nunca aparece en SQS, casi siempre es porque **"registrar" el evento y "publicarlo" son dos pasos distintos**, y algo en la cadena que va de uno a otro se está rompiendo silenciosamente. `record_event()` normalmente solo hace esto:

```python
class Aggregate:
    def __init__(self):
        self.events: list[DomainEvent] = []

    def record_event(self, event: DomainEvent) -> None:
        self.events.append(event)
```

Es decir: el evento queda **en memoria, colgado del objeto Python**. Nada lo saca de ahí automáticamente. Para que llegue a SQS tiene que pasar por una cadena de responsabilidades que, en un sistema DDD + UoW típico, se ve así:

```
Aggregate.record_event()
    -> UoW.commit() recolecta eventos de los agregados "vistos" (Repository.seen)
    -> UoW/MessageBus despacha cada evento a sus handlers
    -> un handler serializa el evento y lo publica en SQS
```

Cualquier eslabón roto en esa cadena produce exactamente el síntoma que describís: el evento se crea, pero nunca sale.

## Checklist de diagnóstico (en orden de probabilidad)

### 1. El repositorio no está trackeando el agregado (`seen`/`_seen`)

El patrón UoW clásico (estilo Cosmic Python) recolecta eventos iterando sobre los agregados que el **repositorio** marcó como "vistos" durante la unit of work — típicamente cualquier agregado que pasó por `repo.add()` o `repo.get()`:

```python
class AbstractRepository:
    def __init__(self):
        self.seen: set[Aggregate] = set()

    def add(self, aggregate: Aggregate) -> None:
        self._add(aggregate)
        self.seen.add(aggregate)

    def get(self, *args, **kwargs) -> Aggregate:
        aggregate = self._get(*args, **kwargs)
        if aggregate:
            self.seen.add(aggregate)
        return aggregate

    @abc.abstractmethod
    def _add(self, aggregate: Aggregate): ...

    @abc.abstractmethod
    def _get(self, *args, **kwargs) -> Aggregate: ...
```

```python
class AbstractUnitOfWork(abc.ABC):
    repo: AbstractRepository

    def collect_new_events(self):
        for aggregate in self.repo.seen:
            while aggregate.events:
                yield aggregate.events.pop(0)
```

**Bug clásico:** el caso de uso obtiene el agregado con un método propio, un query directo, o un repo distinto al que expone `.seen` (por ejemplo, hace `session.get(Model, id)` a mano en vez de `uow.repo.get(id)`, o usa un segundo repositorio "de lectura" para cargarlo). En ese caso el agregado nunca entra al set `seen`, `collect_new_events()` no lo recorre, y el evento muere en el garbage collector aunque `record_event()` se haya ejecutado perfectamente.

👉 **Verificá**: ¿el agregado sobre el que llamaste `record_event()` es el mismo objeto que obtuviste vía `uow.repo.get(...)` / `uow.repo.add(...)` dentro de ese `with uow:`? Si lo recargaste, lo clonaste, o lo construiste aparte, ese es tu bug.

### 2. `UoW.commit()` no llama a `collect_new_events()` / no publica

Revisá el `commit()` real de tu UoW. La forma correcta separa "confirmar la transacción de DB" de "publicar eventos", pero **ambas cosas tienen que pasar**:

```python
class AbstractUnitOfWork(abc.ABC):
    def __enter__(self) -> "AbstractUnitOfWork":
        return self

    def __exit__(self, *args):
        self.rollback()  # no-op si ya hubo commit

    def commit(self):
        self._commit()

    @abc.abstractmethod
    def _commit(self): ...

    @abc.abstractmethod
    def rollback(self): ...
```

Y quien orquesta la publicación normalmente es el **message bus**, no el UoW directamente:

```python
def handle(message: Command | DomainEvent, uow: AbstractUnitOfWork):
    queue = [message]
    while queue:
        message = queue.pop(0)
        if isinstance(message, DomainEvent):
            handle_event(message, queue, uow)
        elif isinstance(message, Command):
            handle_command(message, queue, uow)


def handle_event(event: DomainEvent, queue: list, uow: AbstractUnitOfWork):
    for handler in EVENT_HANDLERS[type(event)]:
        handler(event)
        queue.extend(uow.collect_new_events())
```

**Bug clásico:** en el caso de uso, se llama `uow.commit()` (que hace el `COMMIT` de PostgreSQL) pero **nunca se invoca** `uow.collect_new_events()` después, o el caso de uso hace `return` antes de llegar a esa línea (por ejemplo, en un `try/except` mal ubicado, o en un endpoint FastAPI que arma la respuesta y sale temprano).

👉 **Verificá**: ¿existe, después del `commit()`, un `for event in uow.collect_new_events(): bus.handle(event)` (o equivalente)? ¿Ese bucle se ejecuta siempre, incluso en el camino feliz más corto del endpoint?

### 3. No hay handler registrado para ese tipo de evento

Aunque el evento sí llegue al message bus, si no hay un handler mapeado para su clase, el bus simplemente no hace nada (o lanza `KeyError`/lo ignora según cómo esté implementado el `EVENT_HANDLERS` dict):

```python
EVENT_HANDLERS: dict[type[DomainEvent], list[Callable]] = {
    ProvisionAmountCalculated: [publish_provision_amount_to_sqs],
    # <-- ¿tu evento nuevo está acá?
}
```

**Bug clásico:** se creó una clase de evento nueva (`ProvisionAmountCalculated`, `LoanDisbursed`, lo que sea) pero se olvidó registrar el handler correspondiente en el diccionario/registro central. Es el típico "funciona en local para el evento viejo, pero el nuevo nunca sale" — porque el código nuevo del dominio se escribió, pero el "cableado" en la capa de aplicación no.

👉 **Verificá**: buscá el registro central de handlers (`EVENT_HANDLERS`, `bootstrap.py`, `injector`, o como se llame en tu proyecto) y confirmá que el tipo exacto de tu evento está mapeado a una función que publique a SQS.

### 4. El handler de SQS está fallando silenciosamente

Si el evento sí llega al handler, pero el `try/except` alrededor de la publicación traga la excepción sin loggear (o loggea a un nivel que nadie mira):

```python
def publish_provision_amount_to_sqs(event: ProvisionAmountCalculated, sqs_client=Depends(get_sqs_client)):
    try:
        sqs_client.send_message(
            QueueUrl=settings.PROVISION_QUEUE_URL,
            MessageBody=event.json(),
        )
    except Exception:
        pass  # <-- esto es tu bug
```

Causas típicas del fallo real debajo del `except`:
- `QueueUrl` mal configurado o apuntando a otra región/cuenta (credenciales de IAM sin permiso `sqs:SendMessage` en esa cola).
- El evento no es serializable (`event.json()` explota por un `Decimal`, `datetime`, o value object sin encoder).
- Body de mensaje que excede 256KB.

👉 **Verificá**: quitá el `try/except` genérico (o al menos loggeá con `logger.exception(...)` y stacktrace completo) y volvé a reproducir. Revisá CloudWatch/logs de la app en el momento exacto del commit.

### 5. El evento se publica *antes* del commit, y el commit falla o hace rollback (dual-write problem)

Si en algún lugar la publicación a SQS se dispara **dentro** del mismo bloque que hace `record_event()`, pero *antes* de que el `commit()` de la transacción se confirme, tenés el problema inverso: a veces publica de más (evento sin persistencia real) o, más común en tu caso, el orden de ejecución hace que la publicación dependa de un estado que se revierte:

```python
# ANTI-PATRÓN: no hacer esto
def some_use_case(uow, sqs_client):
    with uow:
        aggregate = uow.repo.get(id)
        aggregate.do_something()
        aggregate.record_event(SomethingHappened(...))
        sqs_client.send_message(...)  # se publica ANTES del commit
        uow.commit()                  # si esto falla, ya publicaste igual
```

o el escenario que más suele explicar "nunca llega":

```python
def some_use_case(uow):
    with uow:
        aggregate = uow.repo.get(id)
        aggregate.do_something()
        aggregate.record_event(SomethingHappened(...))
        raise SomeValidationError(...)  # excepción DESPUÉS de record_event
        uow.commit()  # nunca se alcanza -> rollback -> commit() nunca corre
                       # -> collect_new_events() nunca corre
```

Si hay una excepción (de negocio o infraestructura) entre `record_event()` y `commit()`, el `__exit__` del UoW hace `rollback()`, `commit()` nunca corre, y el evento —que vive solo en memoria dentro del objeto `aggregate`— se pierde junto con el objeto cuando termina el `with`. Esto es *correcto* si la intención es "no hay transacción, no hay evento", pero muchas veces el bug real es que la excepción es inesperada (una validación tardía, un `flush()` de SQLAlchemy que dispara una constraint) y pasa desapercibida porque el endpoint la atrapa y devuelve un 200 igual, o el error se loggea en un nivel que nadie revisa.

👉 **Verificá**: ¿tu caso de uso realmente llega a `uow.commit()`, o hay una excepción / return temprano entre el `record_event()` y el `commit()`? Poné un breakpoint o log justo antes del `commit()` y confirmá que se ejecuta en el request que estás probando.

## El fix según el estándar (outbox transaccional)

Publicar directo a SQS desde el handler, aunque esté bien cableado, tiene un problema estructural: es un **dual write** — estás escribiendo a PostgreSQL y a SQS en dos operaciones separadas no atómicas. Si el commit a DB tiene éxito pero el `send_message` a SQS falla (timeout de red, throttling, IAM revocado a mitad de deploy), perdés el evento para siempre aunque todo el código de arriba esté "bien". Ese es, en la práctica, la causa más frecuente de "a veces sí, a veces no" en producción.

La solución estándar en DDD/event-driven es el **transactional outbox**: en vez de publicar a SQS directamente dentro del handler de dominio, escribís el evento en una tabla `outbox` **dentro de la misma transacción de PostgreSQL** que persiste el agregado. Un proceso aparte (poller o CDC) lee la tabla y publica a SQS con reintentos, por fuera de la transacción de negocio.

```python
class OutboxRecord(Base):
    __tablename__ = "outbox"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    aggregate_id: Mapped[str]
    event_type: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    published_at: Mapped[datetime | None] = mapped_column(default=None)


def persist_events_to_outbox(event: DomainEvent, uow: SqlAlchemyUnitOfWork):
    # corre DENTRO de la misma transacción del commit del agregado
    uow.session.add(
        OutboxRecord(
            aggregate_id=event.aggregate_id,
            event_type=type(event).__name__,
            payload=event.dict(),
        )
    )
```

```python
# Worker/cron separado, con retry e idempotencia
def publish_pending_outbox_events(session: Session, sqs_client) -> None:
    pending = session.execute(
        select(OutboxRecord)
        .where(OutboxRecord.published_at.is_(None))
        .order_by(OutboxRecord.occurred_at)
        .with_for_update(skip_locked=True)
    ).scalars().all()

    for record in pending:
        sqs_client.send_message(
            QueueUrl=queue_url_for(record.event_type),
            MessageBody=json.dumps(record.payload),
            MessageAttributes={"event_type": {"DataType": "String", "StringValue": record.event_type}},
        )
        record.published_at = datetime.utcnow()
        session.commit()
```

Con esto:
- El evento **nunca se pierde** entre el `commit()` de dominio y la publicación, porque ambos ocurren en la misma transacción de DB (o el evento directamente no existe si el commit falla).
- La publicación a SQS es **idempotente y reintentable** independientemente del ciclo de vida del request HTTP.
- Ganás trazabilidad: podés consultar la tabla `outbox` para ver exactamente qué eventos se generaron, cuándo, y si se publicaron.

## Resumen accionable

1. Confirmá que el agregado con el evento pasó por `uow.repo.get()`/`uow.repo.add()` (para que esté en `repo.seen`).
2. Confirmá que después de `uow.commit()` se llama a `uow.collect_new_events()` y que ese loop no se corta por un `return`/excepción temprana.
3. Confirmá que existe un handler registrado para el tipo exacto de tu evento en el mapa `EVENT_HANDLERS`.
4. Sacá cualquier `except: pass` silencioso alrededor del `send_message` y mirá logs/CloudWatch.
5. Verificá que no haya una excepción entre `record_event()` y `commit()` que esté forzando un rollback silencioso.
6. Si esto ya te pasó una vez en producción de forma intermitente, no lo dejes en "publicar directo desde el handler" — migrá a **outbox transaccional**, que es la única forma de garantizar entrega consistente entre la escritura en Postgres y la publicación en SQS.
