from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from kb_upload_core import UPLOAD_MAX_BYTES, upload_project_archive

app = FastAPI(
    title="filesystem-knowledge-bridge uploader",
    description="ZIP archiveをincomingへ配置するアップロード専用API。登録・インデックス作成は行いません。",
    version="0.3.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/uploads/projects")
async def upload_project(
    owner: str = Form(...),
    project: str = Form(...),
    archive: UploadFile = File(...),
) -> JSONResponse:
    suffix = Path(archive.filename or "project.zip").suffix
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="kb-upload-", suffix=suffix, delete=False) as temp:
            temp_path = Path(temp.name)
            size = 0
            while chunk := await archive.read(1024 * 1024):
                size += len(chunk)
                if size > UPLOAD_MAX_BYTES:
                    raise HTTPException(status_code=413, detail="アップロードサイズが上限を超えています")
                temp.write(chunk)

        result = upload_project_archive(
            temp_path,
            owner=owner,
            project=project,
            original_filename=archive.filename or "project.zip",
        )
        return JSONResponse(result, status_code=201)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await archive.close()
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def main() -> None:
    import uvicorn

    host = os.environ.get("UPLOAD_HOST", "0.0.0.0")
    port = int(os.environ.get("UPLOAD_PORT", "8002"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
