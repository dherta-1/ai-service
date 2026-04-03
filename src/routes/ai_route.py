import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from src.container import get_di_container
from src.services.document_processing_service import DocumentProcessingService
from src.shared.response.response_models import create_response

router = APIRouter()


@router.post("/extract-document")
async def extract_document(
    file: UploadFile = File(...),
    s3_prefix: str = Form(default="document-extraction"),
):
    """Upload document and run extraction flow."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    upload_dir = Path("output") / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename).suffix
    saved_name = f"{uuid.uuid4()}{ext}"
    local_path = upload_dir / saved_name

    content = await file.read()
    local_path.write_bytes(content)

    try:
        container = get_di_container()
        service = container.resolve(DocumentProcessingService)
        result = await service.process_document(
            local_file_path=str(local_path),
            original_filename=file.filename,
            s3_prefix=s3_prefix,
        )
        return create_response(data=result, message="Document extraction completed")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {e}") from e
    finally:
        # Keep uploaded source only when needed for debugging
        if local_path.exists():
            try:
                os.remove(local_path)
            except OSError:
                pass
