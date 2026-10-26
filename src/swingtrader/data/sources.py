"""Pinned third-party data sources.

The cloud environment this project was built in blocks the usual market-data
vendors (Yahoo, Stooq, CME, Databento, Polygon, ...). The only reachable source of
real futures history was Hugging Face. Every file below is pinned to an exact
dataset revision and SHA-256 so a backtest can be reproduced byte-for-byte, and
the provenance caveats are recorded next to it. None of these are official
exchange data; docs/INSTRUMENT_SELECTION.md and the validation report document
how far they can be trusted.
"""

from __future__ import annotations

import hashlib
import shutil
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PinnedFile:
    key: str
    repo: str
    revision: str
    filename: str
    sha256: str | None
    description: str
    caveats: str

    @property
    def url(self) -> str:
        return f"https://huggingface.co/datasets/{self.repo}/resolve/{self.revision}/{self.filename}"


_THILLSSS = ("thillsss/SPX-MES-VIX-data", "94f97451205af5320354610595da22f7dd6f5616")
_ES_DB = ("Khanhpham1992/es-futures-1m", "3e05c0408e59cec1b4ec8ca6f26e5ab058a95e09")

SOURCES: dict[str, PinnedFile] = {
    "mes_1m_eth": PinnedFile(
        "mes_1m_eth", *_THILLSSS,
        "MES_full_1min_continuous_absolute_adjusted_CT_market_close.txt",
        "796be1c8e181ad329823f2ee0c3d06bb14f41040096ef11b6b9409357cc32d93",
        "MES continuous, additive back-adjusted, 1-min, US/Central, outside-RTH bars",
        "Anonymous uploader, no licence/card. Format matches FirstRate-Data style exports. "
        "Roll schedule of the adjustment is undocumented (inferred in the data report).",
    ),
    "mes_1m_rth": PinnedFile(
        "mes_1m_rth", *_THILLSSS,
        "MES_full_1min_continuous_absolute_adjusted_CT_market_open.txt",
        "2bd44f5c58483c98930ab3c2fe870a2c60addbd11790b549666befbee5e4f4ba",
        "MES continuous, additive back-adjusted, 1-min, US/Central, RTH (08:30-15:00) bars",
        "Same provenance as mes_1m_eth.",
    ),
    "spx_1m": PinnedFile(
        "spx_1m", *_THILLSSS, "SPX_full_1min_CT.txt",
        "93ca114db81fe5786805391343ce48a6586e9fafb20c6abd44dcd15902430534",
        "S&P 500 cash index, 1-min, US/Central, RTH only, no volume",
        "Index, not tradable. Used only as (a) pre-2019 proxy test period and "
        "(b) cross-check of MES returns.",
    ),
    "vix_daily": PinnedFile(
        "vix_daily", *_THILLSSS, "VIX_daily.txt",
        "7501b8302b66986a1b9e31d0c52198a159d3d2e6fb99b893259bbeb408ec4ef3",
        "CBOE VIX daily", "Early years carry O=H=L=C (close only).",
    ),
    "mnq_1m": PinnedFile(
        "mnq_1m", *_THILLSSS, "mnq_minute_data_CT.txt",
        "55532c09568b21ff329fcc511bf6711532fb4859ca157da7b61faabc47e4132c",
        "MNQ continuous 1-min from 2022, no volume column",
        "Audited for instrument selection only (too short, no volume).",
    ),
    "es_1m_databento": PinnedFile(
        "es_1m_databento", *_ES_DB, "es_continuous_1m.parquet",
        "60341739833d7fe98bbfd4c598e5885d04509c9133aa295f165f5243274a4e3a",
        "ES front-month 1-min (Databento-style instrument_id), UNADJUSTED, 2020-11..2024-07",
        "Large gaps (e.g. 2023-05-05..2023-10-18). Used only as an independent "
        "cross-check of MES returns; its adj_* columns are inconsistent and ignored.",
    ),
}

CORE_SOURCES = ("mes_1m_eth", "mes_1m_rth", "spx_1m", "vix_daily", "es_1m_databento", "mnq_1m")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def local_path(raw_dir: Path, src: PinnedFile) -> Path:
    # Each source lives in its own directory (downloads are untrusted data).
    return raw_dir / src.key / src.filename


def download(key: str, raw_dir: Path, force: bool = False) -> Path:
    """Download one pinned file and verify its SHA-256. Raises on mismatch."""
    src = SOURCES[key]
    dest = local_path(raw_dir, src)
    if dest.exists() and not force:
        if src.sha256 is None or sha256_of(dest) == src.sha256:
            return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(src.url, timeout=300) as resp, open(tmp, "wb") as out:
        shutil.copyfileobj(resp, out)
    if src.sha256 is not None:
        got = sha256_of(tmp)
        if got != src.sha256:
            tmp.unlink(missing_ok=True)
            raise ValueError(f"{key}: sha256 mismatch (expected {src.sha256}, got {got})")
    tmp.replace(dest)
    return dest
