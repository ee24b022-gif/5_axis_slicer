import os
from typing import Protocol
from urllib.parse import urlparse
import boto3
from config import settings

class StorageAdapter(Protocol):
    def save_artifact(self, prefix: str, content: bytes, content_hash: str) -> str:
        ...
    def get_artifact(self, uri: str) -> bytes:
        ...
    def delete_artifact(self, uri: str) -> None:
        ...
    def exists(self, uri: str) -> bool:
        ...

class LocalStorageAdapter(StorageAdapter):
    def __init__(self):
        self.base_uri = settings.artifact_storage_uri
        if not self.base_uri.startswith("file://"):
            raise ValueError("LocalStorageAdapter requires a file:// URI.")
        self.base_path = self.base_uri[7:]
        os.makedirs(self.base_path, exist_ok=True)
        
    def _uri_to_path(self, uri: str) -> str:
        if not uri.startswith("file://"):
            raise ValueError(f"Invalid URI for LocalStorageAdapter: {uri}")
        return uri[7:]
        
    def save_artifact(self, prefix: str, content: bytes, content_hash: str) -> str:
        dir_path = os.path.join(self.base_path, prefix)
        os.makedirs(dir_path, exist_ok=True)
        file_path = os.path.join(dir_path, content_hash)
        with open(file_path, "wb") as f:
            f.write(content)
        return f"file://{file_path}"
        
    def get_artifact(self, uri: str) -> bytes:
        path = self._uri_to_path(uri)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Artifact not found: {uri}")
        with open(path, "rb") as f:
            return f.read()
            
    def delete_artifact(self, uri: str) -> None:
        path = self._uri_to_path(uri)
        if os.path.exists(path):
            os.remove(path)
            
    def exists(self, uri: str) -> bool:
        path = self._uri_to_path(uri)
        return os.path.exists(path)

class S3StorageAdapter(StorageAdapter):
    def __init__(self):
        self.base_uri = settings.artifact_storage_uri
        if not self.base_uri.startswith("s3://"):
            raise ValueError("S3StorageAdapter requires an s3:// URI.")
        parsed = urlparse(self.base_uri)
        self.bucket = parsed.netloc
        self.base_prefix = parsed.path.lstrip("/")
        
        self.s3_client = boto3.client("s3", endpoint_url=settings.s3_endpoint_url)
        
    def _uri_to_key(self, uri: str) -> str:
        if not uri.startswith(f"s3://{self.bucket}/"):
            raise ValueError(f"Invalid URI for this S3 adapter: {uri}")
        return uri[len(f"s3://{self.bucket}/"):]
        
    def save_artifact(self, prefix: str, content: bytes, content_hash: str) -> str:
        key = os.path.join(self.base_prefix, prefix, content_hash).lstrip("/")
        self.s3_client.put_object(Bucket=self.bucket, Key=key, Body=content)
        return f"s3://{self.bucket}/{key}"
        
    def get_artifact(self, uri: str) -> bytes:
        key = self._uri_to_key(uri)
        try:
            response = self.s3_client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()
        except self.s3_client.exceptions.NoSuchKey:
            raise FileNotFoundError(f"Artifact not found: {uri}")
            
    def delete_artifact(self, uri: str) -> None:
        key = self._uri_to_key(uri)
        self.s3_client.delete_object(Bucket=self.bucket, Key=key)
        
    def exists(self, uri: str) -> bool:
        key = self._uri_to_key(uri)
        try:
            self.s3_client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

def get_storage_adapter() -> StorageAdapter:
    if settings.artifact_storage_uri.startswith("s3://"):
        return S3StorageAdapter()
    return LocalStorageAdapter()
