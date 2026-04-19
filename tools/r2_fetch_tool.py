from langchain_core.tools import tool
from dotenv import load_dotenv
import os
import base64
import boto3
from botocore.exceptions import BotoCoreError, ClientError

load_dotenv()


@tool
def r2_fetch_tool(r2_url: str, fetch_content: bool = False) -> dict:
    """Fetch file metadata or content from Cloudflare R2 storage.

    Args:
        r2_url: Full R2 URL of the file to fetch.
        fetch_content: If True, return the file body as base64-encoded string.
                       If False (default), return metadata only.

    Returns:
        Dict with file_name, file_size_bytes, doc_type, content_base64, and error fields.
    """
    try:
        r2_access_key = os.getenv("CLOUDFLARE_R2_ACCESS_KEY_ID")
        r2_secret_key = os.getenv("CLOUDFLARE_R2_SECRET_ACCESS_KEY")
        r2_endpoint = os.getenv("CLOUDFLARE_R2_ENDPOINT_URL")
        r2_bucket = os.getenv("CLOUDFLARE_R2_BUCKET_NAME")

        if not all([r2_access_key, r2_secret_key, r2_endpoint, r2_bucket]):
            return {
                "file_name": None,
                "file_size_bytes": None,
                "doc_type": None,
                "content_base64": None,
                "error": "Missing one or more Cloudflare R2 environment variables.",
            }

        # Parse file_name from URL — last path component
        file_name = r2_url.rstrip("/").split("/")[-1]
        if not file_name:
            return {
                "file_name": None,
                "file_size_bytes": None,
                "doc_type": None,
                "content_base64": None,
                "error": f"Could not parse file name from URL: {r2_url}",
            }

        # Extract doc_type from filename prefix (e.g. "CA_20240101_abc.pdf" → "CA")
        doc_type = file_name.split("_")[0] if "_" in file_name else file_name

        s3_client = boto3.client(
            "s3",
            endpoint_url=r2_endpoint,
            aws_access_key_id=r2_access_key,
            aws_secret_access_key=r2_secret_key,
        )

        # Always get metadata via head_object
        head_response = s3_client.head_object(Bucket=r2_bucket, Key=file_name)
        file_size_bytes = head_response.get("ContentLength", 0)

        content_base64 = None
        if fetch_content:
            get_response = s3_client.get_object(Bucket=r2_bucket, Key=file_name)
            body_bytes = get_response["Body"].read()
            content_base64 = base64.b64encode(body_bytes).decode("utf-8")

        return {
            "file_name": file_name,
            "file_size_bytes": file_size_bytes,
            "doc_type": doc_type,
            "content_base64": content_base64,
            "error": None,
        }

    except (BotoCoreError, ClientError) as e:
        return {
            "file_name": None,
            "file_size_bytes": None,
            "doc_type": None,
            "content_base64": None,
            "error": f"R2 fetch failed: {str(e)}",
        }
    except Exception as e:
        return {
            "file_name": None,
            "file_size_bytes": None,
            "doc_type": None,
            "content_base64": None,
            "error": str(e),
        }
