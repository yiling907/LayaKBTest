import os
import logging
from azure.search.documents.indexes import SearchIndexerClient
from azure.search.documents.indexes.models import (
    SearchIndexerDataSourceConnection,
    SearchIndexerDataContainer,
    SearchIndexer,
    SearchIndexerSkillset,
    OcrSkill,
    MergeSkill,
    SplitSkill,
    AzureOpenAIEmbeddingSkill,
    WebApiSkill,
    InputFieldMappingEntry,
    OutputFieldMappingEntry,
    IndexingParameters,
    IndexingParametersConfiguration,
    BlobIndexerDataToExtract,
    SearchIndexerIndexProjection,
    SearchIndexerIndexProjectionSelector,
    SearchIndexerIndexProjectionsParameters,
    FieldMapping,
)
from azure.core.credentials import AzureKeyCredential

logger = logging.getLogger(__name__)

_EXCEL_EXTENSIONS    = ".xlsx,.xls"
_DOCUMENT_EXTENSIONS = ".pdf,.docx,.doc,.pptx,.ppt,.png,.jpg,.jpeg,.tiff,.bmp,.gif,.txt,.md,.html,.htm,.csv"


def setup_indexer_pipeline():
    endpoint   = os.environ["AZURE_SEARCH_ENDPOINT"]
    key        = os.environ["AZURE_SEARCH_API_KEY"]
    index_name = os.environ["AZURE_SEARCH_INDEX_NAME"]
    func_url   = os.environ.get("FUNCTION_APP_URL", "").rstrip("/")
    credential = AzureKeyCredential(key)
    client     = SearchIndexerClient(endpoint=endpoint, credential=credential)

    _create_data_source(client)
    _create_excel_skillset(client, func_url)
    _create_document_skillset(client, func_url)
    _create_excel_indexer(client, index_name)
    _create_document_indexer(client, index_name)

    client.run_indexer("excel-indexer")
    client.run_indexer("document-indexer")
    logger.info("Both indexers created and started")


def _create_data_source(client: SearchIndexerClient):
    ds = SearchIndexerDataSourceConnection(
        name="blob-datasource",
        type="azureblob",
        connection_string=os.environ["AZURE_STORAGE_CONNECTION_STRING"],
        container=SearchIndexerDataContainer(name=os.environ["AZURE_STORAGE_CONTAINER_NAME"]),
    )
    client.create_or_update_data_source_connection(ds)


# ── Excel Skillset ────────────────────────────────────────────────────────────

def _create_excel_skillset(client: SearchIndexerClient, func_url: str):
    skills = [
        # ① Parse Excel → array of row objects
        WebApiSkill(
            name="excel-parse",
            uri=f"{func_url}/api/excel_skill",
            context="/document",
            http_method="POST",
            timeout="PT120S",
            inputs=[
                InputFieldMappingEntry(name="source_blob_path", source="/document/metadata_storage_path"),
                InputFieldMappingEntry(name="source_file_name", source="/document/metadata_storage_name"),
            ],
            outputs=[
                OutputFieldMappingEntry(name="excel_rows", target_name="excel_rows"),
            ],
        ),
        # ② Clean each row
        WebApiSkill(
            name="excel-clean",
            uri=f"{func_url}/api/clean_document",
            context="/document/excel_rows/*",
            http_method="POST",
            timeout="PT30S",
            inputs=[
                InputFieldMappingEntry(name="content",  source="/document/excel_rows/*/content"),
                InputFieldMappingEntry(name="doc_type", source="/document/excel_rows/*/doc_type"),
            ],
            outputs=[
                OutputFieldMappingEntry(name="cleaned_content", target_name="cleaned_content"),
                OutputFieldMappingEntry(name="cleaning_notes",  target_name="cleaning_notes"),
            ],
        ),
        # ③ Split cleaned content
        SplitSkill(
            name="excel-split",
            context="/document/excel_rows/*",
            text_split_mode="pages",
            maximum_page_length=500,
            page_overlap_length=50,
            inputs=[
                InputFieldMappingEntry(name="text", source="/document/excel_rows/*/cleaned_content"),
            ],
            outputs=[
                OutputFieldMappingEntry(name="textItems", target_name="chunks"),
            ],
        ),
        # ④ Embed each chunk
        AzureOpenAIEmbeddingSkill(
            name="excel-embed",
            context="/document/excel_rows/*/chunks/*",
            resource_uri=os.environ["AZURE_OPENAI_ENDPOINT"],
            deployment_id=os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"],
            model_name="text-embedding-ada-002",
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            inputs=[InputFieldMappingEntry(name="text", source="/document/excel_rows/*/chunks/*")],
            outputs=[OutputFieldMappingEntry(name="embedding", target_name="content_vector")],
        ),
    ]
    client.create_or_update_skillset(SearchIndexerSkillset(
        name="excel-skillset",
        description="Excel → row parse → clean → split → embed",
        skills=skills,
    ))


# ── Document Skillset (PDF / Word / Image) ───────────────────────────────────

def _create_document_skillset(client: SearchIndexerClient, func_url: str):
    skills = [
        # ① OCR for scanned/image documents
        OcrSkill(
            name="doc-ocr",
            context="/document/normalized_images/*",
            default_language_code="en",
            inputs=[InputFieldMappingEntry(name="image", source="/document/normalized_images/*")],
            outputs=[OutputFieldMappingEntry(name="text", target_name="ocr_text")],
        ),
        # ② Merge native text + OCR text
        MergeSkill(
            name="doc-merge",
            context="/document",
            insert_pre_tag=" ",
            insert_post_tag=" ",
            inputs=[
                InputFieldMappingEntry(name="text",          source="/document/content"),
                InputFieldMappingEntry(name="itemsToInsert", source="/document/normalized_images/*/ocr_text"),
            ],
            outputs=[OutputFieldMappingEntry(name="mergedText", target_name="merged_text")],
        ),
        # ③ Data cleaning
        WebApiSkill(
            name="doc-clean",
            uri=f"{func_url}/api/clean_document",
            context="/document",
            http_method="POST",
            timeout="PT60S",
            inputs=[
                InputFieldMappingEntry(name="content",  source="/document/merged_text"),
                InputFieldMappingEntry(name="doc_type", source="/document/metadata_storage_content_type"),
            ],
            outputs=[
                OutputFieldMappingEntry(name="cleaned_content", target_name="cleaned_content"),
                OutputFieldMappingEntry(name="cleaning_notes",  target_name="cleaning_notes"),
            ],
        ),
        # ④ Split into chunks
        SplitSkill(
            name="doc-split",
            context="/document",
            text_split_mode="pages",
            maximum_page_length=2000,
            page_overlap_length=200,
            inputs=[InputFieldMappingEntry(name="text", source="/document/cleaned_content")],
            outputs=[OutputFieldMappingEntry(name="textItems", target_name="chunks")],
        ),
        # ⑤ Embed each chunk
        AzureOpenAIEmbeddingSkill(
            name="doc-embed",
            context="/document/chunks/*",
            resource_uri=os.environ["AZURE_OPENAI_ENDPOINT"],
            deployment_id=os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"],
            model_name="text-embedding-ada-002",
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            inputs=[InputFieldMappingEntry(name="text", source="/document/chunks/*")],
            outputs=[OutputFieldMappingEntry(name="embedding", target_name="content_vector")],
        ),
    ]
    client.create_or_update_skillset(SearchIndexerSkillset(
        name="document-skillset",
        description="PDF/Word/Image → OCR → merge → clean → split → embed",
        skills=skills,
    ))


# ── Indexers ─────────────────────────────────────────────────────────────────

def _excel_projections(index_name: str) -> SearchIndexerIndexProjection:
    return SearchIndexerIndexProjection(
        selectors=[
            SearchIndexerIndexProjectionSelector(
                target_index_name=index_name,
                parent_key_field_name="document_id",
                source_context="/document/excel_rows/*/chunks/*",
                mappings=[
                    InputFieldMappingEntry(name="content",        source="/document/excel_rows/*/chunks/*"),
                    InputFieldMappingEntry(name="content_vector", source="/document/excel_rows/*/chunks/*/content_vector"),
                    InputFieldMappingEntry(name="cleaning_notes", source="/document/excel_rows/*/cleaning_notes"),
                    InputFieldMappingEntry(name="sheet_name",     source="/document/excel_rows/*/sheet_name"),
                    InputFieldMappingEntry(name="doc_type",       source="/document/excel_rows/*/doc_type"),
                    InputFieldMappingEntry(name="product_name",   source="/document/excel_rows/*/product_name"),
                    InputFieldMappingEntry(name="source_blob_path", source="/document/metadata_storage_path"),
                    InputFieldMappingEntry(name="source_file_name", source="/document/metadata_storage_name"),
                    InputFieldMappingEntry(name="last_updated",   source="/document/metadata_storage_last_modified"),
                ],
            )
        ],
        parameters=SearchIndexerIndexProjectionsParameters(projection_mode="generatedKeyAsId"),
    )


def _document_projections(index_name: str) -> SearchIndexerIndexProjection:
    return SearchIndexerIndexProjection(
        selectors=[
            SearchIndexerIndexProjectionSelector(
                target_index_name=index_name,
                parent_key_field_name="document_id",
                source_context="/document/chunks/*",
                mappings=[
                    InputFieldMappingEntry(name="content",        source="/document/chunks/*"),
                    InputFieldMappingEntry(name="content_vector", source="/document/chunks/*/content_vector"),
                    InputFieldMappingEntry(name="cleaning_notes", source="/document/cleaning_notes"),
                    InputFieldMappingEntry(name="doc_type",       source="/document/metadata_storage_content_type"),
                    InputFieldMappingEntry(name="source_blob_path", source="/document/metadata_storage_path"),
                    InputFieldMappingEntry(name="source_file_name", source="/document/metadata_storage_name"),
                    InputFieldMappingEntry(name="last_updated",   source="/document/metadata_storage_last_modified"),
                ],
            )
        ],
        parameters=SearchIndexerIndexProjectionsParameters(projection_mode="generatedKeyAsId"),
    )


def _create_excel_indexer(client: SearchIndexerClient, index_name: str):
    indexer = SearchIndexer(
        name="excel-indexer",
        data_source_name="blob-datasource",
        skillset_name="excel-skillset",
        target_index_name=index_name,
        parameters=IndexingParameters(
            configuration=IndexingParametersConfiguration(
                data_to_extract=BlobIndexerDataToExtract.CONTENT_AND_METADATA,
                indexed_file_name_extensions=_EXCEL_EXTENSIONS,
            )
        ),
        index_projections=_excel_projections(index_name),
    )
    client.create_or_update_indexer(indexer)


def _create_document_indexer(client: SearchIndexerClient, index_name: str):
    indexer = SearchIndexer(
        name="document-indexer",
        data_source_name="blob-datasource",
        skillset_name="document-skillset",
        target_index_name=index_name,
        parameters=IndexingParameters(
            configuration=IndexingParametersConfiguration(
                data_to_extract=BlobIndexerDataToExtract.CONTENT_AND_METADATA,
                image_action="generateNormalizedImages",
                indexed_file_name_extensions=_DOCUMENT_EXTENSIONS,
            )
        ),
        index_projections=_document_projections(index_name),
    )
    client.create_or_update_indexer(indexer)
