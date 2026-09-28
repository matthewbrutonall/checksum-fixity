# Checksum / Fixity skill

A local agent skill for creating and checking file checksums.

It can:

- calculate checksums for selected files;
- create checksum manifests;
- verify files against a manifest; and
- review expected and actual checksum reports.

It uses Python’s standard library and does not upload files or call an API. Operations are read-only, directories require explicit recursive processing, and symbolic links are not followed.

SHA-256 is the default. MD5 and SHA-1 are available for legacy verification. A checksum match confirms bit-level agreement with the expected value; it does not prove provenance or authenticity.
