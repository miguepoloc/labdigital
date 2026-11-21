from backend.commons.domain import events as domain_events
from backend.files.blobs.domain.model import value_objects


class BlobUploaded(domain_events.DomainEvent):
    blob_id: value_objects.BlobId
    owner_id: value_objects.OwnerId
    size: int
