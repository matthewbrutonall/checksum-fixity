# Checksum / Fixity skill

![Digital files paired with matching checksum patterns](assets/checksum-fixity.png)

A local agent skill for creating and checking file checksums.

It can:

- calculate checksums for selected files;
- create checksum manifests;
- verify files against a manifest; and
- review expected and actual checksum reports.

It uses Python’s standard library and does not upload files or call an API. Operations are read-only, directories require explicit recursive processing, and symbolic links are not followed.

SHA-256 is the default. MD5 and SHA-1 are available for legacy verification. A checksum match confirms bit-level agreement with the expected value; it does not prove provenance or authenticity.

## Install with your AI agent

Copy and paste this into your agent:

```text
Install the Checksum / Fixity skill from https://github.com/matthewbrutonall/checksum-fixity using your agent's supported skill installation method. Keep `SKILL.md` and the bundled `scripts` directory together. Check that Python is available, confirm you can find and use the skill, and tell me how to invoke it. Do not hash or inspect my files yet.
```
