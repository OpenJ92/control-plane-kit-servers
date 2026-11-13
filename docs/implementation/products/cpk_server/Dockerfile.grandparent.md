# Dockerfile.grandparent

The grandparent product still derives from the verified local OCI base. It admits no-version-change public dependency facts before installation, uses exact hashed wheels and explicit local project archives without resolving donor pins, and keeps normal module command/UID10001 with the explicit four-read profile. It does not package credentials or source mounts; no build has run at this preparation checkpoint.
