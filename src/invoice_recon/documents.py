"""Discover invoice images: inputs folder first, then generated; filename order within a folder."""

from pathlib import Path

from pydantic import BaseModel

from invoice_recon import config

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


class Document(BaseModel):
    file_id: str  # image filename stem, unique across all folders
    path: Path


class DuplicateFileIdError(ValueError):
    pass


def discover_documents(folders: list[Path] | None = None) -> list[Document]:
    """Return documents in processing order. Missing folders are skipped; a repeated file_id is an error."""
    folders = folders if folders is not None else [config.INPUTS_DIR / "images", config.GENERATED_DIR / "images"]
    documents: list[Document] = []
    seen: dict[str, Path] = {}
    for folder in folders:
        if not folder.is_dir():
            continue
        files = sorted(
            (p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES),
            key=lambda p: p.name,
        )
        for path in files:
            if path.stem in seen:
                raise DuplicateFileIdError(
                    f"file_id {path.stem!r} is used by both {seen[path.stem]} and {path}; file names must be unique"
                )
            seen[path.stem] = path
            documents.append(Document(file_id=path.stem, path=path))
    return documents


def relative_image_path(path: Path) -> str:
    """Repo-relative POSIX path for saved state; falls back to the absolute path outside the repo."""
    try:
        return path.resolve().relative_to(config.ROOT_DIR).as_posix()
    except ValueError:
        return path.resolve().as_posix()
