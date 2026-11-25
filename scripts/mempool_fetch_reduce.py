"""Download Flashbots Mempool Dumpster daily CSV files and reduce each day to a small Parquet file.

Usage : python mempool_fetch_reduce.py 2026-05-01 2026-10-31 [--work work]
Output: work/reduced/YYYY-MM-DD.parquet with columns
          h      UBIGINT   first 64 bits of the transaction hash (collision rate is negligible)
          sender VARCHAR   lower-case sender address
          nonce  UBIGINT
          landed BOOLEAN   included on chain according to the archive
          ts_ms  BIGINT    first time the archive saw the transaction (ms since epoch)
The raw CSV (about 100 MB zipped, several hundred MB unzipped per day) is deleted after each day,
so the run needs only a few GB of free disk. Days already reduced are skipped, so the script can
be stopped and restarted at any time. Works on Windows, macOS and Linux (no curl or unzip needed).
"""
import argparse
import datetime as dt
import pathlib
import shutil
import sys
import time
import urllib.error
import urllib.request
import zipfile

import duckdb

BASE = "https://mempool-dumpster.flashbots.net/ethereum/mainnet"


# The server rejects Python's default User-Agent (HTTP 403), so send a curl-like one.
HEADERS = {"User-Agent": "curl/8.5.0", "Accept": "*/*"}


class MissingDay(Exception):
    pass


def fetch(url: str, dst: pathlib.Path, tries: int = 4) -> None:
    for k in range(1, tries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=120) as r, open(dst, "wb") as f:
                shutil.copyfileobj(r, f, length=1 << 20)
            return
        except urllib.error.HTTPError as e:
            if e.code in (403, 404) and k >= 2:
                raise MissingDay(f"HTTP {e.code}: file not available")
            print(f"  download failed ({e}); retry {k}/{tries}", flush=True)
            time.sleep(5 * k)
        except Exception as e:  # network hiccup: wait and retry
            print(f"  download failed ({e}); retry {k}/{tries}", flush=True)
            time.sleep(10 * k)
    raise RuntimeError(f"giving up on {url}")


def reduce_day(day: str, work: pathlib.Path, con: duckdb.DuckDBPyConnection) -> None:
    out = work / "reduced" / f"{day}.parquet"
    if out.exists():
        print(f"{day}: already reduced, skip", flush=True)
        return
    tmp = work / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    zpath = tmp / f"{day}.csv.zip"
    url = f"{BASE}/{day[:7]}/{day}.csv.zip"
    t0 = time.time()
    print(f"{day}: downloading", flush=True)
    fetch(url, zpath)
    with zipfile.ZipFile(zpath) as z:
        member = [n for n in z.namelist() if n.endswith(".csv")][0]
        z.extract(member, tmp)
        csv_path = tmp / member
    zpath.unlink()

    part = out.with_suffix(".part")
    con.execute(f"""
        COPY (
          SELECT CAST('0x' || substr(hash, 3, 16) AS UBIGINT)       AS h,
                 lower(any_value("from"))                          AS sender,
                 CAST(any_value(nonce) AS UBIGINT)                 AS nonce,
                 bool_or(coalesce(included_at_block_height, '') NOT IN ('', '0')) AS landed,
                 min(CAST(timestamp_ms AS BIGINT))                 AS ts_ms
          FROM read_csv('{csv_path.as_posix()}', header=true, all_varchar=true)
          WHERE (chain_id = '1' OR chain_id IS NULL) AND hash IS NOT NULL
          GROUP BY h
        ) TO '{part.as_posix()}' (FORMAT parquet, COMPRESSION zstd)
    """)
    part.rename(out)
    csv_path.unlink()
    n = con.execute(f"SELECT count(*) FROM '{out.as_posix()}'").fetchone()[0]
    print(f"{day}: {n:,} tx reduced in {time.time() - t0:.0f} s", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("start")
    ap.add_argument("end")
    ap.add_argument("--work", default="work")
    a = ap.parse_args()
    work = pathlib.Path(a.work)
    (work / "reduced").mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    d = dt.date.fromisoformat(a.start)
    end = dt.date.fromisoformat(a.end)
    failed = []
    while d <= end:
        try:
            reduce_day(d.isoformat(), work, con)
        except Exception as e:
            print(f"{d}: FAILED ({e})", flush=True)
            failed.append(d.isoformat())
        d += dt.timedelta(days=1)
    if failed:
        print("failed days (rerun the same command to retry):", ", ".join(failed))
        sys.exit(1)
    print("all days reduced")


if __name__ == "__main__":
    main()
