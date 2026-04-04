"""ZIP download and extraction utilities."""

import hashlib
import logging
import zipfile
from pathlib import Path

import aiofiles
import httpx

logger = logging.getLogger(__name__)


async def download_zip(
    url: str,
    client: httpx.AsyncClient,
    cache_dir: Path,
    *,
    force_redownload: bool = False,
) -> Path:
    """Download a ZIP file to cache_dir. Returns path to the downloaded ZIP.

    Uses a content-hash filename to avoid re-downloading identical files.
    If the file already exists in cache, skip download unless force_redownload=True.
    """
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    filename = url.split("/")[-1] or f"vestnik_{url_hash}.zip"
    dest = cache_dir / filename

    if dest.exists() and not force_redownload:
        logger.debug("Using cached ZIP: %s", dest)
        return dest

    cache_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading ZIP: %s", url)

    async with client.stream("GET", url) as response:
        response.raise_for_status()
        async with aiofiles.open(dest, "wb") as f:
            async for chunk in response.aiter_bytes(chunk_size=65536):
                await f.write(chunk)

    logger.info("Downloaded %d bytes: %s", dest.stat().st_size, dest.name)
    return dest


def extract_xml_files(zip_path: Path, extract_dir: Path) -> list[Path]:
    """Extract all XML files from a ZIP archive. Returns list of extracted XML paths."""
    extract_dir.mkdir(parents=True, exist_ok=True)
    xml_files = []

    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            if name.endswith(".xml"):
                zf.extract(name, extract_dir)
                xml_files.append(extract_dir / name)

    logger.info("Extracted %d XML files from %s", len(xml_files), zip_path.name)
    return xml_files
