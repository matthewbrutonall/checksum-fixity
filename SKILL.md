---
name: checksum-fixity
description: Perform local, read-only checksum operations when the user asks to hash explicit files, generate or verify a checksum manifest, or turn an expected/actual checksum CSV into a fixity register. Do not trigger for general digital-preservation advice, storage planning, authenticity determinations, or repository ingest.
---

# Checksum / Fixity

Use the bundled Python helper for deterministic work. Resolve its path relative to this `SKILL.md`:

```bash
python3 <skill-directory>/scripts/fixity.py --help
```

Choose the operation that matches the request:

- `hash`: calculate checksums for explicitly named local files.
- `manifest`: create a checksum manifest from explicit files. A directory requires `--recursive`.
- `verify`: calculate local checksums and compare them with an existing manifest.
- `review`: compare supplied expected and actual checksum columns and create a register.

Use SHA-256 by default. Use MD5 or SHA-1 only when compatibility with a legacy manifest requires it, and report the helper's warning. Never silently substitute one algorithm for another.

## Safety

- Operate only on paths the user placed in scope.
- Treat files as read-only. Do not rename, move, repair, quarantine, replace, or delete them.
- Do not follow symbolic links. Report skipped or refused paths.
- Directory traversal requires `--recursive`; do not add it unless the user asked to process that directory.
- The default recursive limit is 10,000 files. Ask before raising `--max-files` substantially.
- Write manifests or reports only to new paths. The helper refuses existing outputs.
- Do not expose full paths or checksum values in an unrelated chat handoff.

## Interpretation

A match means the calculated bytes agree with the expected digest under the stated algorithm. It does not prove provenance, authorship, chain of custody, or authenticity, and it does not show that the expected manifest was trustworthy.

For mismatches, report the affected path and recommend a preservation incident review. Do not automatically replace a file from another copy. Missing files, invalid manifest lines, unsafe paths, and symlinks are separate outcomes rather than mismatches.

Example:

```bash
python3 <skill-directory>/scripts/fixity.py manifest \
  --base-dir /data/transfer \
  --recursive /data/transfer \
  --output /data/reports/transfer.sha256
```
