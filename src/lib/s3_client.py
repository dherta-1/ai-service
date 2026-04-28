import os
import logging
from typing import Optional, Dict, Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)


class S3Client:
    """Wrapper around boto3 S3 client for simplified DI usage."""

    def __init__(
        self,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_session_token: Optional[str] = None,
        region_name: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        config: Optional[Config] = None,
    ):
        self.session = boto3.session.Session(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token,
            region_name=region_name,
        )

        self.client = self.session.client(
            "s3",
            endpoint_url=endpoint_url,
            config=config or Config(signature_version="s3v4"),
        )

    def upload_file(
        self,
        file_path: str,
        bucket: str,
        key: str,
        ExtraArgs: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Upload file from local path to S3."""
        try:
            self.client.upload_file(file_path, bucket, key, ExtraArgs=ExtraArgs or {})
            logger.info("Uploaded file %s to s3://%s/%s", file_path, bucket, key)
        except (BotoCoreError, ClientError) as e:
            logger.error("S3 upload_file failed: %s", e)
            raise

    def upload_file_bytes(
        self,
        file_content: bytes,
        bucket: str,
        key: str,
        content_type: Optional[str] = None,
    ) -> None:
        """Upload file from bytes content to S3."""
        try:
            extra_args = {}
            if content_type:
                extra_args["ContentType"] = content_type
            self.client.put_object(
                Bucket=bucket,
                Key=key,
                Body=file_content,
                **extra_args,
            )
            logger.info("Uploaded %d bytes to s3://%s/%s", len(file_content), bucket, key)
        except (BotoCoreError, ClientError) as e:
            logger.error("S3 upload_file_bytes failed: %s", e)
            raise

    def download_file(self, bucket: str, key: str, target_path: str) -> None:
        try:
            self.client.download_file(bucket, key, target_path)
            logger.info("Downloaded file s3://%s/%s to %s", bucket, key, target_path)
        except (BotoCoreError, ClientError) as e:
            logger.error("S3 download_file failed: %s", e)
            raise

    def list_buckets(self) -> Dict[str, Any]:
        try:
            resp = self.client.list_buckets()
            return resp
        except (BotoCoreError, ClientError) as e:
            logger.error("S3 list_buckets failed: %s", e)
            raise

    def get_client(self):
        return self.client

    def generate_presigned_url(
        self,
        client_method: str,
        Params: Dict[str, Any],
        ExpiresIn: int = 3600,
    ) -> str:
        """Generate a presigned URL for S3 object access."""
        try:
            url = self.client.generate_presigned_url(
                client_method,
                Params=Params,
                ExpiresIn=ExpiresIn,
            )
            logger.info("Generated presigned URL for %s", Params.get("Key", "unknown"))
            return url
        except (BotoCoreError, ClientError) as e:
            logger.error("Failed to generate presigned URL: %s", e)
            raise

    def ensure_bucket(self, bucket: str, region_name: Optional[str] = None) -> None:
        """Ensure S3 bucket exists; create if missing."""
        try:
            self.client.head_bucket(Bucket=bucket)
        except ClientError as e:
            error_code = int(e.response["Error"]["Code"])
            if error_code == 404:
                create_kwargs = {"Bucket": bucket}
                if region_name:
                    create_kwargs["CreateBucketConfiguration"] = {
                        "LocationConstraint": region_name
                    }
                self.client.create_bucket(**create_kwargs)
                logger.info("Created S3 bucket: %s", bucket)
            else:
                logger.error("Bucket check failed for %s: %s", bucket, e)
                raise


def get_s3_client(settings=None) -> S3Client:
    """Constructs an S3Client from settings or environment variables."""

    aws_access_key_id = (
        settings.aws_access_key_id if settings else os.getenv("AWS_ACCESS_KEY_ID")
    )
    aws_secret_access_key = (
        settings.aws_secret_access_key
        if settings
        else os.getenv("AWS_SECRET_ACCESS_KEY")
    )
    # Do not use session token if invalid token issue occurs
    aws_session_token = None
    region_name = settings.aws_region if settings else os.getenv("AWS_REGION")
    endpoint_url = (
        settings.aws_s3_endpoint_url if settings else os.getenv("AWS_S3_ENDPOINT_URL")
    )

    return S3Client(
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        aws_session_token=aws_session_token,
        region_name=region_name,
        endpoint_url=endpoint_url,
    )
