from pathlib import Path
import base64
import binascii
import shutil
import struct
import zipfile
import zlib

root = Path(__file__).resolve().parents[1]
archive_dir = root / "archive"

parts = sorted(archive_dir.glob("U_DINK_STORE_ALL_SOURCE.zip.b64.part*"))
if not parts:
    raise SystemExit("Archive parts not found.")

payload = "".join(p.read_text(encoding="utf-8").strip() for p in parts)
raw_zip = base64.b64decode(payload)
zip_path = root / "U_DINK_STORE_ALL_SOURCE.zip"
zip_path.write_bytes(raw_zip)

extract_dir = root / "restored-source"
if extract_dir.exists():
    shutil.rmtree(extract_dir)
extract_dir.mkdir(exist_ok=True)


def safe_target(name: str):
    relative = Path(name)
    target = (extract_dir / relative).resolve()
    base = extract_dir.resolve()
    if target == base or base not in target.parents:
        return None
    return target


def recover_with_central_directory():
    extracted = []
    skipped = []
    try:
        archive = zipfile.ZipFile(zip_path, "r")
    except zipfile.BadZipFile as exc:
        return extracted, [("<archive>", str(exc))]

    with archive:
        for info in archive.infolist():
            if info.is_dir():
                target = safe_target(info.filename)
                if target:
                    target.mkdir(parents=True, exist_ok=True)
                continue

            target = safe_target(info.filename)
            if target is None:
                skipped.append((info.filename, "unsafe path"))
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                with archive.open(info, "r") as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                extracted.append(info.filename)
            except (zipfile.BadZipFile, RuntimeError, OSError, EOFError) as exc:
                target.unlink(missing_ok=True)
                skipped.append((info.filename, str(exc)))

    return extracted, skipped


def recover_by_local_headers(data: bytes):
    """Recover ZIP entries by scanning actual local headers.

    The historical Base64 transfer has a readable central directory but incorrect
    central-directory local-header offsets. The local records themselves still
    begin with PK\x03\x04 and contain their own compressed sizes because bit 3 is
    not set. Reading them sequentially avoids relying on the damaged offsets.
    """
    signature = b"PK\x03\x04"
    extracted = []
    skipped = []
    cursor = 0
    total = len(data)

    while True:
        pos = data.find(signature, cursor)
        if pos < 0:
            break
        if pos + 30 > total:
            break

        try:
            (
                sig,
                version,
                flags,
                method,
                mod_time,
                mod_date,
                crc32_expected,
                compressed_size,
                uncompressed_size,
                name_len,
                extra_len,
            ) = struct.unpack_from("<4s5H3I2H", data, pos)
        except struct.error:
            break

        header_end = pos + 30 + name_len + extra_len
        if sig != signature or header_end > total:
            cursor = pos + 4
            continue

        name_bytes = data[pos + 30 : pos + 30 + name_len]
        try:
            name = name_bytes.decode("utf-8")
        except UnicodeDecodeError:
            name = name_bytes.decode("cp437", errors="replace")

        # This archive was produced without data descriptors. If a scanned false
        # positive says otherwise, ignore it and continue searching.
        if flags & 0x08:
            skipped.append((name or f"offset-{pos}", "unsupported data descriptor"))
            cursor = pos + 4
            continue

        data_end = header_end + compressed_size
        if compressed_size < 0 or data_end > total:
            skipped.append((name or f"offset-{pos}", "compressed data extends past archive"))
            cursor = pos + 4
            continue

        compressed = data[header_end:data_end]
        try:
            if method == 0:
                plain = compressed
            elif method == 8:
                plain = zlib.decompress(compressed, -15)
            else:
                raise ValueError(f"unsupported compression method {method}")

            if uncompressed_size and len(plain) != uncompressed_size:
                raise ValueError(
                    f"size mismatch: expected {uncompressed_size}, got {len(plain)}"
                )

            crc_actual = binascii.crc32(plain) & 0xFFFFFFFF
            if crc32_expected and crc_actual != crc32_expected:
                raise ValueError(
                    f"CRC mismatch: expected {crc32_expected:08x}, got {crc_actual:08x}"
                )

            target = safe_target(name)
            if target is None:
                raise ValueError("unsafe path")

            if name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(plain)
                extracted.append(name)

            # Continue exactly after the recovered compressed payload. This
            # avoids false PK signatures inside deflated data.
            cursor = data_end
        except Exception as exc:
            skipped.append((name or f"offset-{pos}", str(exc)))
            cursor = pos + 4

    return extracted, skipped


extracted, skipped = recover_with_central_directory()
index_files = list(extract_dir.rglob("index.html"))

if not index_files:
    # Clear partial output and recover from the physical local records instead.
    shutil.rmtree(extract_dir)
    extract_dir.mkdir(exist_ok=True)
    local_extracted, local_skipped = recover_by_local_headers(raw_zip)
    extracted = local_extracted
    skipped.extend(local_skipped)
    index_files = list(extract_dir.rglob("index.html"))

if not index_files:
    details = "\n".join(f"- {name}: {reason}" for name, reason in skipped[:30])
    raise SystemExit(f"Archive recovery produced no index.html. Diagnostics:\n{details}")

print(f"Restored archive: {zip_path}")
print(f"Extracted readable files: {len(extracted)}")
print(f"Recovered index files: {len(index_files)}")
for path in index_files:
    print(f"- {path.relative_to(extract_dir)}")
if skipped:
    print(f"Recovery diagnostics/skipped entries: {len(skipped)}")
    for name, reason in skipped[:30]:
        print(f"- {name}: {reason}")
print(f"Extracted source: {extract_dir}")
