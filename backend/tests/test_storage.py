import os
import pytest
import boto3
from moto import mock_aws
from config import settings
from storage import LocalStorageAdapter, S3StorageAdapter, get_storage_adapter

@pytest.fixture
def local_storage(tmp_path):
    old_uri = settings.artifact_storage_uri
    settings.artifact_storage_uri = f"file://{tmp_path}/artifacts"
    adapter = LocalStorageAdapter()
    yield adapter
    settings.artifact_storage_uri = old_uri

def test_local_storage_adapter(local_storage):
    content = b"hello local world"
    content_hash = "hash123"
    
    # save
    uri = local_storage.save_artifact("test", content, content_hash)
    assert uri.startswith("file://")
    assert uri.endswith(f"test/{content_hash}")
    
    # exists
    assert local_storage.exists(uri) is True
    assert local_storage.exists(uri + "notfound") is False
    
    # get
    assert local_storage.get_artifact(uri) == content
    with pytest.raises(FileNotFoundError):
        local_storage.get_artifact(uri + "notfound")
        
    # delete
    local_storage.delete_artifact(uri)
    assert local_storage.exists(uri) is False
    # deleting a non-existent shouldn't raise error
    local_storage.delete_artifact(uri)

@pytest.fixture
def s3_storage():
    old_uri = settings.artifact_storage_uri
    settings.artifact_storage_uri = "s3://test-bucket/artifacts"
    with mock_aws():
        # Setup mock bucket
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")
        
        adapter = S3StorageAdapter()
        yield adapter
        
    settings.artifact_storage_uri = old_uri

def test_s3_storage_adapter(s3_storage):
    content = b"hello s3 world"
    content_hash = "hash456"
    
    # save
    uri = s3_storage.save_artifact("test", content, content_hash)
    assert uri == "s3://test-bucket/artifacts/test/hash456"
    
    # exists
    assert s3_storage.exists(uri) is True
    assert s3_storage.exists(uri + "notfound") is False
    
    # get
    assert s3_storage.get_artifact(uri) == content
    with pytest.raises(FileNotFoundError):
        s3_storage.get_artifact(uri + "notfound")
        
    # delete
    s3_storage.delete_artifact(uri)
    assert s3_storage.exists(uri) is False
    s3_storage.delete_artifact(uri) # idempotent
    
def test_get_storage_adapter():
    old_uri = settings.artifact_storage_uri
    
    settings.artifact_storage_uri = "file:///tmp/something"
    adapter = get_storage_adapter()
    assert isinstance(adapter, LocalStorageAdapter)
    
    settings.artifact_storage_uri = "s3://some-bucket/path"
    adapter = get_storage_adapter()
    assert isinstance(adapter, S3StorageAdapter)
    
    settings.artifact_storage_uri = old_uri
