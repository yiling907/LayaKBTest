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
    SemanticConfiguration,
    SemanticSearch,
    SemanticPrioritizedFields,
    SemanticField,
)
from azure.search.documents.models import VectorizedQuery, QueryType
from azure.core.credentials import AzureKeyCredential

VECTOR_DIMENSIONS = 1536  # text-embedding-ada-002


def _credential():
    return AzureKeyCredential(os.environ["AZURE_SEARCH_API_KEY"])


def _endpoint():
    return os.environ["AZURE_SEARCH_ENDPOINT"]


def _index_name():
    return os.environ["AZURE_SEARCH_INDEX_NAME"]


def ensure_index():
    """Create or update the search index with the full insurance schema."""
    index_client = SearchIndexClient(endpoint=_endpoint(), credential=_credential())
    index_name   = _index_name()

    fields = [
        SimpleField(name="id",               type=SearchFieldDataType.String,  key=True),
        SimpleField(name="document_id",      type=SearchFieldDataType.String,  filterable=True),
        SimpleField(name="source_blob_path", type=SearchFieldDataType.String,  filterable=True),
        SimpleField(name="source_file_name", type=SearchFieldDataType.String,  filterable=True),
        SimpleField(name="page_number",      type=SearchFieldDataType.Int32,   filterable=True, retrievable=True),
        SimpleField(name="sheet_name",       type=SearchFieldDataType.String,  filterable=True),
        SimpleField(name="doc_type",         type=SearchFieldDataType.String,  filterable=True),
        SimpleField(name="product_name",     type=SearchFieldDataType.String,  filterable=True),
        SimpleField(name="last_updated",     type=SearchFieldDataType.String,  filterable=True),
        SearchableField(name="content",      type=SearchFieldDataType.String),
        SearchableField(name="cleaning_notes", type=SearchFieldDataType.String, retrievable=True),
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

    semantic_config = SemanticConfiguration(
        name="insurance-semantic-config",
        prioritized_fields=SemanticPrioritizedFields(
            content_fields=[SemanticField(field_name="content")],
            keywords_fields=[
                SemanticField(field_name="product_name"),
                SemanticField(field_name="doc_type"),
            ],
        ),
    )

    index = SearchIndex(
        name=index_name,
        fields=fields,
        vector_search=vector_search,
        semantic_search=SemanticSearch(configurations=[semantic_config]),
    )
    index_client.create_or_update_index(index)


def upsert_chunks(chunks: list[dict]):
    client = SearchClient(endpoint=_endpoint(), index_name=_index_name(), credential=_credential())
    client.upload_documents(documents=chunks)


def vector_search(query_vector: list[float], top_k: int = 5) -> list[dict]:
    from azure.search.documents.models import VectorizedQuery
    client = SearchClient(endpoint=_endpoint(), index_name=_index_name(), credential=_credential())
    vector_query = VectorizedQuery(vector=query_vector, k_nearest_neighbors=top_k, fields="content_vector")
    results = client.search(search_text=None, vector_queries=[vector_query])
    return [
        {
            "id":               r["id"],
            "document_name":    r.get("source_file_name", ""),
            "source_blob_path": r.get("source_blob_path", ""),
            "source_file_name": r.get("source_file_name", ""),
            "page_number":      r.get("page_number"),
            "sheet_name":       r.get("sheet_name"),
            "doc_type":         r.get("doc_type", ""),
            "product_name":     r.get("product_name", ""),
            "content":          r["content"],
        }
        for r in results
    ]


def hybrid_search(query: str, query_vector: list[float], top_k: int = 5, filter_expr: str = None) -> list[dict]:
    """Hybrid search: keyword + vector + semantic reranker."""
    client = SearchClient(endpoint=_endpoint(), index_name=_index_name(), credential=_credential())
    vector_query = VectorizedQuery(vector=query_vector, k_nearest_neighbors=50, fields="content_vector")

    try:
        results = client.search(
            search_text=query,
            vector_queries=[vector_query],
            query_type=QueryType.SEMANTIC,
            semantic_configuration_name="insurance-semantic-config",
            select=[
                "id", "content", "source_blob_path", "source_file_name",
                "page_number", "sheet_name", "doc_type", "product_name",
            ],
            filter=filter_expr,
            top=top_k,
        )
    except Exception:
        # Fallback to basic hybrid without semantic reranker
        results = client.search(
            search_text=query,
            vector_queries=[vector_query],
            select=[
                "id", "content", "source_blob_path", "source_file_name",
                "page_number", "sheet_name", "doc_type", "product_name",
            ],
            filter=filter_expr,
            top=top_k,
        )

    return [
        {
            "id":               r["id"],
            "content":          r["content"],
            "source_blob_path": r.get("source_blob_path", ""),
            "source_file_name": r.get("source_file_name", ""),
            "page_number":      r.get("page_number"),
            "sheet_name":       r.get("sheet_name"),
            "doc_type":         r.get("doc_type", ""),
            "product_name":     r.get("product_name", ""),
            "score":            r.get("@search.score", 0),
        }
        for r in results
    ]
