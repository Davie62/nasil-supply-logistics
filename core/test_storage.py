"""Private media storage: object layout, overwrite policy and presigned access."""
import boto3
from django.core.files.base import ContentFile
from django.test import SimpleTestCase
from moto import mock_aws
from storages.backends.s3 import S3Storage

BUCKET = "nasil-media-tests"
REGION = "us-east-1"
LOCATION = "media"


def private_storage(**overrides):
    options = {
        "bucket_name": BUCKET,
        "region_name": REGION,
        "location": LOCATION,
        "default_acl": None,
        "file_overwrite": False,
        "querystring_auth": True,
        "custom_domain": None,
        "querystring_expire": 300,
        "signature_version": "s3v4",
    }
    options.update(overrides)
    return S3Storage(**options)


@mock_aws
class PrivateMediaStorageTests(SimpleTestCase):
    def setUp(self):
        self.s3 = boto3.client("s3", region_name=REGION)
        self.s3.create_bucket(Bucket=BUCKET)

    def object_key(self, name):
        """Storage names are relative to the configured location prefix."""
        return f"{LOCATION}/{name}"

    def test_upload_is_written_under_the_media_prefix(self):
        storage = private_storage()
        name = storage.save("evidence/proof.txt", ContentFile(b"delivery proof"))

        self.assertEqual(name, "evidence/proof.txt")
        body = self.s3.get_object(Bucket=BUCKET, Key=self.object_key(name))["Body"].read()
        self.assertEqual(body, b"delivery proof")

    def test_uploaded_objects_are_private(self):
        storage = private_storage()
        name = storage.save("proof.txt", ContentFile(b"payload"))
        grants = self.s3.get_object_acl(Bucket=BUCKET, Key=self.object_key(name))["Grants"]

        grantees = {grant["Grantee"].get("URI", "") for grant in grants}
        self.assertFalse(any("AllUsers" in grantee or "AuthenticatedUsers" in grantee for grantee in grantees))

    def test_private_objects_are_served_by_presigned_urls(self):
        storage = private_storage()
        name = storage.save("proof.txt", ContentFile(b"payload"))
        url = storage.url(name)

        self.assertIn(f"{BUCKET}.s3", url)
        self.assertIn("X-Amz-Signature=", url)
        self.assertIn("X-Amz-Credential=", url)
        self.assertIn("X-Amz-Expires=300", url)

    def test_presigned_url_lifetime_follows_configuration(self):
        storage = private_storage(querystring_expire=120)
        name = storage.save("proof.txt", ContentFile(b"payload"))
        self.assertIn("X-Amz-Expires=120", storage.url(name))

    def test_existing_files_are_never_overwritten(self):
        storage = private_storage()
        first = storage.save("proof.txt", ContentFile(b"first"))
        second = storage.save("proof.txt", ContentFile(b"second"))

        self.assertNotEqual(first, second)
        self.assertEqual(self.s3.get_object(Bucket=BUCKET, Key=self.object_key(first))["Body"].read(), b"first")
        self.assertEqual(self.s3.get_object(Bucket=BUCKET, Key=self.object_key(second))["Body"].read(), b"second")
