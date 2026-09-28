#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

VERSION = "0.1.0"
CHUNK_SIZE = 1024 * 1024
DEFAULT_MAX_FILES = 10_000
ALGORITHMS = {
    "md5": 32,
    "sha1": 40,
    "sha256": 64,
    "sha512": 128,
}
LEGACY_ALGORITHMS = {"md5", "sha1"}


class FixityError(Exception):
    pass


class OutputExistsError(FixityError):
    pass


def has_symlink_component(path: Path) -> bool:
    absolute = Path(os.path.abspath(path))
    return any(candidate.is_symlink() for candidate in (absolute, *absolute.parents))


def algorithm_warning(algorithm: str) -> str | None:
    if algorithm in LEGACY_ALGORITHMS:
        return f"{algorithm.upper()} is supported for legacy compatibility; prefer SHA-256 for new manifests."
    return None


def hash_file(path: Path, algorithm: str) -> str:
    if has_symlink_component(path):
        raise FixityError(f"Symbolic links are not followed: {path}")
    if not path.is_file():
        raise FixityError(f"Not a regular file: {path}")
    digest = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative_path(path: Path, base_dir: Path) -> str:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(base_dir.resolve())
    except ValueError as error:
        raise FixityError(f"Path is outside the declared base directory: {path}") from error
    value = relative.as_posix()
    if "\n" in value or "\r" in value:
        raise FixityError(f"Manifest paths cannot contain line breaks: {path}")
    return value


def collect_files(paths: list[str], recursive: bool, max_files: int) -> tuple[list[Path], list[dict[str, str]]]:
    files: list[Path] = []
    skipped: list[dict[str, str]] = []
    for supplied in paths:
        path = Path(supplied)
        if has_symlink_component(path):
            skipped.append({"path": str(path), "reason": "symbolic_link_not_followed"})
            continue
        if path.is_file():
            files.append(path)
            continue
        if path.is_dir():
            if not recursive:
                raise FixityError(f"Directory input requires --recursive: {path}")
            for root, directories, filenames in os.walk(path, followlinks=False):
                root_path = Path(root)
                retained_directories = []
                for directory in directories:
                    candidate = root_path / directory
                    if candidate.is_symlink():
                        skipped.append({"path": str(candidate), "reason": "symbolic_link_not_followed"})
                    else:
                        retained_directories.append(directory)
                directories[:] = retained_directories
                for filename in filenames:
                    candidate = root_path / filename
                    if candidate.is_symlink():
                        skipped.append({"path": str(candidate), "reason": "symbolic_link_not_followed"})
                    elif candidate.is_file():
                        files.append(candidate)
                        if len(files) > max_files:
                            raise FixityError(
                                f"File count exceeds --max-files ({max_files}). Increase it explicitly after reviewing the scope."
                            )
            continue
        skipped.append({"path": str(path), "reason": "missing_or_not_regular"})
    unique = {str(path.resolve()): path for path in files}
    ordered = [unique[key] for key in sorted(unique)]
    if len(ordered) > max_files:
        raise FixityError(f"File count exceeds --max-files ({max_files}).")
    return ordered, skipped


def refuse_existing_output(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise OutputExistsError(f"Refusing to overwrite existing output: {path}")
    if has_symlink_component(path.parent):
        raise FixityError(f"Refusing to write through a symbolic-link path: {path}")


def write_new_text(path: Path, content: str) -> None:
    refuse_existing_output(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as stream:
        stream.write(content)


def hash_operation(args: argparse.Namespace) -> dict:
    files, skipped = collect_files(args.paths, recursive=False, max_files=len(args.paths))
    results = []
    for path in files:
        results.append({"path": str(path), "algorithm": args.algorithm, "checksum": hash_file(path, args.algorithm)})
    return operation_result("hash", args.algorithm, results, skipped)


def manifest_operation(args: argparse.Namespace) -> dict:
    supplied_base = Path(args.base_dir)
    if has_symlink_component(supplied_base):
        raise FixityError(f"Symbolic links are not followed: {supplied_base}")
    base_dir = supplied_base.resolve()
    if not base_dir.is_dir():
        raise FixityError(f"Base directory does not exist: {base_dir}")
    files, skipped = collect_files(args.paths, args.recursive, args.max_files)
    rows = []
    lines = []
    for path in files:
        relative_path = safe_relative_path(path, base_dir)
        checksum = hash_file(path, args.algorithm)
        rows.append({"path": relative_path, "algorithm": args.algorithm, "checksum": checksum})
        lines.append(f"{checksum}  {relative_path}")
    output = Path(args.output)
    write_new_text(output, "\n".join(lines) + ("\n" if lines else ""))
    result = operation_result("manifest", args.algorithm, rows, skipped)
    result["output"] = str(output)
    result["baseDirectory"] = str(base_dir)
    return result


def parse_manifest(path: Path, algorithm: str) -> tuple[list[dict[str, str]], list[dict[str, object]]]:
    entries = []
    invalid = []
    expected_length = ALGORITHMS[algorithm]
    with path.open("r", encoding="utf-8-sig") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            line = raw_line.rstrip("\r\n")
            if not line.strip():
                continue
            match = re.match(r"^([0-9A-Fa-f]+)\s+[ *]?(.*)$", line)
            if not match or not match.group(2):
                invalid.append({"line": line_number, "status": "invalid_manifest_line"})
                continue
            checksum, relative_path = match.groups()
            if len(checksum) != expected_length:
                invalid.append({"line": line_number, "path": relative_path, "status": "invalid_checksum_length"})
                continue
            entries.append({"line": line_number, "path": relative_path, "expected": checksum.lower()})
    return entries, invalid


def verify_operation(args: argparse.Namespace) -> dict:
    manifest = Path(args.manifest)
    if has_symlink_component(manifest) or not manifest.is_file():
        raise FixityError(f"Manifest is not a regular file: {manifest}")
    supplied_base = Path(args.base_dir) if args.base_dir else manifest.parent
    if has_symlink_component(supplied_base):
        raise FixityError(f"Symbolic links are not followed: {supplied_base}")
    base_dir = supplied_base.resolve()
    if not base_dir.is_dir():
        raise FixityError(f"Base directory does not exist: {base_dir}")
    entries, invalid = parse_manifest(manifest, args.algorithm)
    results: list[dict[str, object]] = []
    for entry in entries:
        requested = base_dir / str(entry["path"])
        resolved = requested.resolve()
        try:
            resolved.relative_to(base_dir)
        except ValueError:
            results.append({**entry, "status": "unsafe_path"})
            continue
        if has_symlink_component(requested):
            results.append({**entry, "status": "symbolic_link_refused"})
            continue
        if not resolved.is_file():
            results.append({**entry, "status": "missing"})
            continue
        actual = hash_file(resolved, args.algorithm)
        status = "match" if actual.lower() == entry["expected"] else "mismatch"
        results.append({**entry, "actual": actual, "status": status})
    results.extend(invalid)
    counts: dict[str, int] = {}
    for row in results:
        status = str(row["status"])
        counts[status] = counts.get(status, 0) + 1
    return {
        "skill": "checksum-fixity",
        "skillVersion": VERSION,
        "operation": "verify",
        "algorithm": args.algorithm,
        "warning": algorithm_warning(args.algorithm),
        "manifest": str(manifest),
        "baseDirectory": str(base_dir),
        "counts": counts,
        "results": results,
        "caveat": "Checksum agreement confirms bit-level agreement with the supplied expected value; it does not prove provenance or authenticity.",
    }


PATH_HEADERS = {"path", "filepath", "file path", "filename", "file name", "name"}
EXPECTED_HEADERS = {"expected checksum", "expected", "expected_sha256", "expected md5", "stored checksum", "manifest checksum"}
ACTUAL_HEADERS = {"actual checksum", "actual", "actual_sha256", "computed checksum", "verified checksum", "verification checksum", "fixity checksum"}
ALGORITHM_HEADERS = {"algorithm", "checksum algorithm", "hash algorithm"}
DATE_HEADERS = {"verification date", "date checked", "checked date", "date", "verified at"}


def normalized_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def find_header(fieldnames: list[str], candidates: set[str]) -> str | None:
    normalized = {field: normalized_header(field) for field in fieldnames}
    exact = next((field for field, value in normalized.items() if value in candidates), None)
    if exact:
        return exact
    return next((field for field, value in normalized.items() if any(candidate in value for candidate in candidates)), None)


def review_status(expected: str, actual: str) -> str:
    if not expected and not actual:
        return "missing_checksums"
    if not expected:
        return "missing_expected"
    if not actual:
        return "missing_actual"
    return "match" if expected.lower() == actual.lower() else "mismatch"


def review_operation(args: argparse.Namespace) -> dict:
    source = Path(args.input)
    if has_symlink_component(source) or not source.is_file():
        raise FixityError(f"Input is not a regular CSV file: {source}")
    with source.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fieldnames = reader.fieldnames or []
        path_header = find_header(fieldnames, PATH_HEADERS)
        if not path_header:
            raise FixityError("CSV requires a recognised path or filename column.")
        expected_header = find_header(fieldnames, EXPECTED_HEADERS)
        actual_header = find_header(fieldnames, ACTUAL_HEADERS)
        algorithm_header = find_header(fieldnames, ALGORITHM_HEADERS)
        date_header = find_header(fieldnames, DATE_HEADERS)
        if not expected_header and not actual_header:
            raise FixityError("CSV requires an expected checksum or actual checksum column.")
        rows = []
        for source_row, row in enumerate(reader, start=2):
            path_value = (row.get(path_header) or "").strip()
            if not path_value:
                continue
            expected = (row.get(expected_header) or "").strip() if expected_header else ""
            actual = (row.get(actual_header) or "").strip() if actual_header else ""
            status = review_status(expected, actual)
            rows.append({
                "source_row": source_row,
                "path": path_value,
                "algorithm": ((row.get(algorithm_header) or "").strip() if algorithm_header else "") or args.algorithm or "",
                "expected_checksum": expected,
                "actual_checksum": actual,
                "verification_date": ((row.get(date_header) or "").strip() if date_header else "") or args.verification_date or "",
                "status": status,
                "next_action": next_action(status),
            })
    counts = {status: sum(1 for row in rows if row["status"] == status) for status in ["match", "mismatch", "missing_expected", "missing_actual", "missing_checksums"]}
    result = {
        "skill": "checksum-fixity",
        "skillVersion": VERSION,
        "operation": "review",
        "input": str(source),
        "counts": counts,
        "rows": rows,
        "caveat": "This review compares supplied strings only; it does not show that the referenced files were opened or hashed.",
    }
    if args.output_dir:
        output_dir = Path(args.output_dir)
        outputs = [output_dir / "fixity-register.csv", output_dir / "fixity-exceptions.csv", output_dir / "fixity-record.md"]
        for output in outputs:
            refuse_existing_output(output)
        output_dir.mkdir(parents=True, exist_ok=True)
        headers = ["source_row", "path", "algorithm", "expected_checksum", "actual_checksum", "verification_date", "status", "next_action"]
        write_review_csv(outputs[0], rows, headers)
        write_review_csv(outputs[1], [row for row in rows if row["status"] != "match"], headers)
        markdown = build_review_markdown(rows, counts)
        write_new_text(outputs[2], markdown)
        result["outputs"] = [str(output) for output in outputs]
    return result


def write_review_csv(path: Path, rows: list[dict], headers: list[str]) -> None:
    refuse_existing_output(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def build_review_markdown(rows: list[dict], counts: dict[str, int]) -> str:
    exceptions = [row for row in rows if row["status"] != "match"]
    lines = [
        "# Draft Checksum / Fixity Register",
        "",
        f"Generated locally on {date.today().isoformat()} from a supplied report.",
        "",
        "## Summary",
        "",
        f"- listed files: {len(rows)}",
        f"- matches: {counts['match']}",
        f"- mismatches: {counts['mismatch']}",
        f"- missing expected checksums: {counts['missing_expected']}",
        f"- missing actual checksums: {counts['missing_actual']}",
        f"- missing both checksums: {counts['missing_checksums']}",
        "",
        "## Exceptions",
        "",
    ]
    lines.extend(f"- {row['path']} | {row['status']} | {row['next_action']}" for row in exceptions)
    if not exceptions:
        lines.append("- None recorded by this draft.")
    lines.extend([
        "",
        "## Caveat",
        "",
        "This review compares supplied strings only. It does not show that the referenced files were opened or hashed, and it does not prove provenance or authenticity.",
        "",
    ])
    return "\n".join(lines)


def next_action(status: str) -> str:
    actions = {
        "match": "Record the verification outcome.",
        "mismatch": "Re-run local verification and begin preservation incident review; do not overwrite automatically.",
        "missing_expected": "Locate the original manifest or trusted repository metadata.",
        "missing_actual": "Run local fixity verification and record the resulting checksum.",
        "missing_checksums": "Supply checksum evidence before making a fixity finding.",
    }
    return actions[status]


def operation_result(operation: str, algorithm: str, results: list[dict], skipped: list[dict]) -> dict:
    return {
        "skill": "checksum-fixity",
        "skillVersion": VERSION,
        "operation": operation,
        "algorithm": algorithm,
        "warning": algorithm_warning(algorithm),
        "processed": len(results),
        "skipped": skipped,
        "results": results,
        "caveat": "Checksums describe file bytes under the stated algorithm; they do not prove provenance or authenticity.",
    }


def add_algorithm(parser: argparse.ArgumentParser, default: str = "sha256") -> None:
    parser.add_argument("--algorithm", choices=sorted(ALGORITHMS), default=default)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local, read-only checksum and fixity operations.")
    parser.add_argument("--version", action="version", version=VERSION)
    subparsers = parser.add_subparsers(dest="operation", required=True)

    hash_parser = subparsers.add_parser("hash", help="Hash explicitly named files.")
    hash_parser.add_argument("paths", nargs="+")
    add_algorithm(hash_parser)
    hash_parser.set_defaults(handler=hash_operation)

    manifest_parser = subparsers.add_parser("manifest", help="Create a checksum manifest.")
    manifest_parser.add_argument("paths", nargs="+")
    manifest_parser.add_argument("--base-dir", default=".")
    manifest_parser.add_argument("--output", required=True)
    manifest_parser.add_argument("--recursive", action="store_true")
    manifest_parser.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES)
    add_algorithm(manifest_parser)
    manifest_parser.set_defaults(handler=manifest_operation)

    verify_parser = subparsers.add_parser("verify", help="Verify local files against a manifest.")
    verify_parser.add_argument("--manifest", required=True)
    verify_parser.add_argument("--base-dir")
    add_algorithm(verify_parser)
    verify_parser.set_defaults(handler=verify_operation)

    review_parser = subparsers.add_parser("review", help="Review expected and actual checksum columns in CSV.")
    review_parser.add_argument("--input", required=True)
    review_parser.add_argument("--output-dir")
    review_parser.add_argument("--algorithm")
    review_parser.add_argument("--verification-date")
    review_parser.set_defaults(handler=review_operation)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = args.handler(args)
    except OutputExistsError as error:
        print(str(error), file=sys.stderr)
        return 3
    except (FixityError, OSError, UnicodeError, csv.Error) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
