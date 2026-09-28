import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "fixity.py"


class FixitySkillTests(unittest.TestCase):
    def run_script(self, *arguments):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, arguments)],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_hashes_explicit_file_with_sha256(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "record.txt"
            source.write_bytes(b"archival record\n")
            completed = self.run_script("hash", source)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["results"][0]["checksum"], hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(payload["algorithm"], "sha256")

    def test_generates_and_verifies_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "folder" / "record one.txt"
            source.parent.mkdir()
            source.write_text("record", encoding="utf-8")
            manifest = base / "reports" / "transfer.sha256"
            generated = self.run_script("manifest", source, "--base-dir", base, "--output", manifest)
            self.assertEqual(generated.returncode, 0, generated.stderr)
            self.assertIn("folder/record one.txt", manifest.read_text(encoding="utf-8"))
            verified = self.run_script("verify", "--manifest", manifest, "--base-dir", base)
            self.assertEqual(verified.returncode, 0, verified.stderr)
            payload = json.loads(verified.stdout)
            self.assertEqual(payload["counts"], {"match": 1})

    def test_reports_mismatch_without_modifying_file(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "record.txt"
            source.write_text("changed", encoding="utf-8")
            manifest = base / "manifest.sha256"
            manifest.write_text(f"{'0' * 64}  record.txt\n", encoding="utf-8")
            before = source.read_bytes()
            completed = self.run_script("verify", "--manifest", manifest)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["counts"], {"mismatch": 1})
            self.assertEqual(source.read_bytes(), before)

    def test_refuses_manifest_path_outside_base(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            manifest = base / "manifest.sha256"
            manifest.write_text(f"{'0' * 64}  ../outside.txt\n", encoding="utf-8")
            completed = self.run_script("verify", "--manifest", manifest)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["counts"], {"unsafe_path": 1})

    def test_directory_requires_recursive_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            completed = self.run_script("manifest", base, "--base-dir", base, "--output", base / "manifest.sha256")
            self.assertEqual(completed.returncode, 2)
            self.assertIn("requires --recursive", completed.stderr)

    def test_refuses_to_overwrite_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "record.txt"
            source.write_text("record", encoding="utf-8")
            manifest = base / "manifest.sha256"
            manifest.write_text("keep", encoding="utf-8")
            completed = self.run_script("manifest", source, "--base-dir", base, "--output", manifest)
            self.assertEqual(completed.returncode, 3)
            self.assertEqual(manifest.read_text(encoding="utf-8"), "keep")

    def test_reviews_csv_and_writes_exception_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            report = base / "report.csv"
            with report.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["path", "expected_checksum", "actual_checksum"])
                writer.writerow(["match.tif", "ABC", "abc"])
                writer.writerow(["mismatch.tif", "abc", "def"])
                writer.writerow(["missing.tif", "abc", ""])
            output = base / "review"
            completed = self.run_script("review", "--input", report, "--output-dir", output)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["counts"]["match"], 1)
            self.assertEqual(payload["counts"]["mismatch"], 1)
            with (output / "fixity-exceptions.csv").open("r", encoding="utf-8", newline="") as stream:
                exception_paths = [row["path"] for row in csv.DictReader(stream)]
            self.assertEqual(exception_paths, ["mismatch.tif", "missing.tif"])

    def test_legacy_algorithm_has_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "record.txt"
            source.write_text("record", encoding="utf-8")
            completed = self.run_script("hash", source, "--algorithm", "md5")
            payload = json.loads(completed.stdout)
            self.assertIn("legacy", payload["warning"])

    def test_does_not_follow_symbolic_link_components(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            real_directory = base / "real"
            real_directory.mkdir()
            source = real_directory / "record.txt"
            source.write_text("record", encoding="utf-8")
            linked_directory = base / "linked"
            linked_directory.symlink_to(real_directory, target_is_directory=True)
            completed = self.run_script("hash", linked_directory / "record.txt")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["processed"], 0)
            self.assertEqual(payload["skipped"][0]["reason"], "symbolic_link_not_followed")


if __name__ == "__main__":
    unittest.main()
