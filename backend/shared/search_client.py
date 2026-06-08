import os
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchFieldDataType,
    SearchableField,
    SearchField,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
)
from azure.core.credentials import AzureKeyCredential


VECTOR_DIMENSIONS = 1536  # text-embedding-ada-002


def _credential():
    return AzureKeyCredential(os.environ["AZURE_SEARCH_API_KEY"])


def _endpoint():
    return os.environ["AZURE_SEARCH_ENDPOINT"]


def _index_name():
    return os.environ["AZURE_SEARCH_INDEX_NAME"]


def ensure_index():
    """Create the search index if it doesn't exist."""
    index_client = SearchIndexClient(endpoint=_endpoint(), credential=_credential())
    index_name = _index_name()

    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SimpleField(name="document_id", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="document_name", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=VECTOR_DIMENSIONS,
            vector_search_profile_name="default-profile",
        ),
    ]

    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="default-hnsw")],
        profiles=[VectorSearchProfile(name="default-profile", algorithm_configuration_name="default-hnsw")],
    )

    index = SearchIndex(name=index_name, fields=fields, vector_search=vector_search)
    index_client.create_or_update_index(index)


def upsert_chunks(chunks: list[dict]):
    """Upload chunk documents to the search index."""
    client = SearchClient(endpoint=_endpoint(), index_name=_index_name(), credential=_credential())
    client.upload_documents(documents=chunks)


def vector_search(query_vector: list[float], top_k: int = 5) -> list[dict]:
    """Search for the most relevant chunks by vector similarity."""
    from azure.search.documents.models import VectorizedQuery

    client = SearchClient(endpoint=_endpoint(), index_name=_index_name(), credential=_credential())
    vector_query = VectorizedQuery(
        vector=query_vector,
        k_nearest_neighbors=top_k,
        fields="content_vector",
    )
    results = client.search(search_text=None, vector_queries=[vector_query])
    return [
        {"id": r["id"], "document_name": r["document_name"], "content": r["content"]}
        for r in results
    ]
