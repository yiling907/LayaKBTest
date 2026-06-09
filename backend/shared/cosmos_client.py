import os
from azure.cosmos import CosmosClient, PartitionKey


def _get_container():
    client = CosmosClient(
        url=os.environ["AZURE_COSMOS_ENDPOINT"],
        credential=os.environ["AZURE_COSMOS_KEY"],
    )
    db = client.get_database_client(os.environ["AZURE_COSMOS_DATABASE"])
    return db.get_container_client(os.environ["AZURE_COSMOS_CONTAINER"])


def save_document_metadata(doc: dict):
    container = _get_container()
    container.upsert_item(doc)


def get_document_metadata(doc_id: str) -> dict | None:
    container = _get_container()
    try:
        return container.read_item(item=doc_id, partition_key=doc_id)
    except Exception:
        return None


def list_documents() -> list[dict]:
    container = _get_container()
    return list(container.query_items(
        query="SELECT c.id, c.name, c.size, c.status, c.chunks, c._ts FROM c",
        enable_cross_partition_query=True,
    ))
