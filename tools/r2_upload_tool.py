from langchain_core.tools import tool
from dotenv import load_dotenv
import os
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from datetime import datetime, timezone
from uuid import uuid4

load_dotenv(override=True)


@tool
def r2_upload_tool(file_path: str, doc_type: str) -> dict:
    """Upload a PDF file to Cloudflare R2 storage.

    Args:
        file_path: Absolute path to the PDF file to upload.
        doc_type: Document type prefix, either "CA" or "Notice".

    Returns:
        Dict with r2_url, file_size_bytes, file_name, and error fields.
    """
    try:
        r2_access_key = os.getenv("CLOUDFLARE_R2_ACCESS_KEY_ID")
        r2_secret_key = os.getenv("CLOUDFLARE_R2_SECRET_ACCESS_KEY")
        r2_endpoint = os.getenv("CLOUDFLARE_R2_ENDPOINT_URL")
        r2_bucket = os.getenv("CLOUDFLARE_R2_BUCKET_NAME")

        if not all([r2_access_key, r2_secret_key, r2_endpoint, r2_bucket]):
            return {
                "r2_url": None,
                "file_size_bytes": None,
                "file_name": None,
                "error": "Missing one or more Cloudflare R2 environment variables.",
            }

        if not os.path.isfile(file_path):
            return {
                "r2_url": None,
                "file_size_bytes": None,
                "file_name": None,
                "error": f"File not found: {file_path}",
            }

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        unique_suffix = uuid4().hex[:8]
        file_name = f"{doc_type}_{timestamp}_{unique_suffix}.pdf"

        s3_client = boto3.client(
            "s3",
            endpoint_url=r2_endpoint,
            aws_access_key_id=r2_access_key,
            aws_secret_access_key=r2_secret_key,
        )

        file_size_bytes = os.path.getsize(file_path)

        with open(file_path, "rb") as f:
            s3_client.upload_fileobj(f, r2_bucket, file_name)

        r2_url = f"{r2_endpoint}/{r2_bucket}/{file_name}"

        return {
            "r2_url": r2_url,
            "file_size_bytes": file_size_bytes,
            "file_name": file_name,
            "error": None,
        }

    except (BotoCoreError, ClientError) as e:
        return {
            "r2_url": None,
            "file_size_bytes": None,
            "file_name": None,
            "error": f"R2 upload failed: {str(e)}",
        }
    except Exception as e:
        return {
            "r2_url": None,
            "file_size_bytes": None,
            "file_name": None,
            "error": str(e),
        }
