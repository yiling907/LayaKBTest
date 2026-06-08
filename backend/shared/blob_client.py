import os
from azure.storage.blob import BlobServiceClient


def get_blob_client():
    conn_str = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
    return BlobServiceClient.from_connection_string(conn_str)


def upload_document(file_name: str, data: bytes) -> str:
    container = os.environ["AZURE_STORAGE_CONTAINER_NAME"]
    client = get_blob_client()
    blob = client.get_blob_client(container=container, blob=file_name)
    blob.upload_blob(data, overwrite=True)
    return blob.url


def download_document(file_name: str) -> bytes:
    container = os.environ["AZURE_STORAGE_CONTAINER_NAME"]
    client = get_blob_client()
    blob = client.get_blob_client(container=container, blob=file_name)
    return blob.download_blob().readall()
