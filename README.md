# Checksum / Fixity skill

![Digital files paired with matching checksum patterns](assets/checksum-fixity.png)

How can you check whether a digital file has changed since an earlier copy or check? A **checksum** is a short string calculated from a file's bytes. Calculate it again later and compare the two strings. If they differ, the file's contents have changed.

This **agent skill** gives an AI assistant a careful way to make those checks on files you choose. It includes a small local Python helper. Your files stay on your computer: the helper does not upload them or call an online service.

For example, suppose an archive receives `letters/letter-001.tif` with an expected checksum in a transfer list. You can ask your agent to check that file against the list. A matching result means its bytes agree with the supplied checksum. A mismatch gives you a reason to investigate before relying on that copy. This is an illustrative example, not a claim about any particular file.

## Who might use it?

An archivist, records manager, or digital preservation worker checking a transfer, making a checksum list for selected files, or reviewing a previous fixity report. **Fixity** means checking whether digital content has stayed the same at the bit level.

## What can the skill do?

- **Calculate a checksum** for explicitly named files. For example, check one new TIFF before filing it with a transfer.
- **Make a manifest**, a plain list of filenames and their checksums, for named files. A folder is included only if you explicitly request recursive processing.
- **Verify files against a manifest** by recalculating their checksums and reporting matches, mismatches, missing files, and other problems separately.
- **Review a supplied CSV report** with expected and actual checksum columns, then make a draft register and exceptions list. This review compares the values in the report; it does not open or hash the files named there.

SHA-256 is the default checksum method. MD5 and SHA-1 are available when checking older manifests, but the method must match the one used to create the expected values.

## How to interpret a result

A match shows agreement with the **expected checksum you supplied** under the stated method. It does not prove who made the file, where it came from, or whether that expected checksum was trustworthy. Keep the transfer record or other evidence alongside the fixity result.

If a checksum differs, investigate the affected file and the expected value. The skill does not repair, replace, move, or delete files. It does not follow symbolic links. It refuses to overwrite an existing manifest or report.

## Set it up with your AI agent

Copy and paste this into an agent that can install skills on your computer:

```text
Install the Checksum / Fixity skill from https://github.com/matthewbrutonall/checksum-fixity using your agent's supported skill installation method. Keep `SKILL.md` and the bundled `scripts` directory together. Check that Python is available, confirm you can find and use the skill, and tell me how to invoke it. Do not hash or inspect my files yet.
```

Once installed, you can ask your agent, for example:

```text
Use the Checksum / Fixity skill to verify the files in /data/transfer against /data/transfer/manifest.sha256. Show me any mismatches or missing files. Do not change any source files.
```

Give your agent the actual file and manifest paths for your work. The skill operates only on paths you put in scope; a directory requires an explicit request to process it recursively.

## Run the bundled helper yourself

You can also use the helper directly without installing the skill into an agent. It uses Python's standard library:

```bash
git clone https://github.com/matthewbrutonall/checksum-fixity.git
cd checksum-fixity
python3 scripts/fixity.py --help
```

For one named file:

```bash
python3 scripts/fixity.py hash /data/transfer/letter-001.tif
```

To create a SHA-256 manifest for a named file, give a base directory so the manifest records a relative path. Choose a **new** output filename:

```bash
python3 scripts/fixity.py manifest /data/transfer/letter-001.tif \
  --base-dir /data/transfer \
  --output /data/reports/transfer.sha256
```

To check the files against that manifest later:

```bash
python3 scripts/fixity.py verify \
  --manifest /data/reports/transfer.sha256 \
  --base-dir /data/transfer
```

The helper prints structured results in JSON. It reads source files for checksums but does not alter them. Creating a manifest or register writes new output files and refuses existing output paths.

## Further options

`manifest --recursive` processes a named directory and its subdirectories, with a default limit of 10,000 files. Symbolic links are skipped. `--algorithm` accepts `sha256`, `sha512`, `sha1`, or `md5`; use the same algorithm as the expected manifest when verifying.

`review --input report.csv --output-dir review-results` compares expected and actual values already present in a CSV report. It can write a register, an exceptions CSV, and a short Markdown record. It does **not** calculate fresh checksums. Run `python3 scripts/fixity.py review --help` for the accepted options.

The standalone [Checksum / Fixity CLI](https://github.com/matthewbrutonall/checksum-fixity-cli) is a separate tool for people who prefer a dedicated command-line package. This skill works on its own; the CLI is optional.

## For developers

The guidance is in [`SKILL.md`](SKILL.md), the helper is in `scripts/fixity.py`, and its tests are in `tests/test_fixity.py`:

```bash
python3 -m unittest discover -s tests
```
