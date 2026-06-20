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


def download_document_by_path(blob_name: str) -> bytes:
    container = os.environ["AZURE_STORAGE_CONTAINER_NAME"]
    client = get_blob_client()
    blob = client.get_blob_client(container=container, blob=blob_name)
    return blob.download_blob().readall()


def generate_sas_url(blob_name: str, expiry_hours: int = 24) -> str:
    from azure.storage.blob import generate_blob_sas, BlobSasPermissions
    from datetime import datetime, timedelta, timezone

    conn_str = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
    parts = dict(p.split("=", 1) for p in conn_str.split(";") if "=" in p)
    account_name = parts.get("AccountName", "")
    account_key  = parts.get("AccountKey", "")
    container    = os.environ["AZURE_STORAGE_CONTAINER_NAME"]

    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=container,
        blob_name=blob_name,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(timezone.utc) + timedelta(hours=expiry_hours),
    )
    return f"https://{account_name}.blob.core.windows.net/{container}/{blob_name}?{sas_token}"
