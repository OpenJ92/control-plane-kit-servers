# Issue Transfer Strategy

This repository is created by `OpenJ92/control-plane-kit#649`. The original
issue topology remains in `OpenJ92/control-plane-kit` until each target issue is
ready to move or be mirrored with clear cross-links.

Transfer rules:

- Transfer only after the target repository has the required policy, package,
  test, and catalogue foundations.
- Preserve the original issue number in every transferred issue body or opening
  comment.
- Preserve predecessor and successor handoffs as explicit comments.
- Do not transfer a product issue before its law cards and frozen evidence have
  been rehydrated.
- Do not mark a product migrated merely because source files moved.
- Keep deferred products out of the repository until their own topology opens.

Bootstrap order:

```text
#649 repository creation
  -> #650 repository policy
    -> #651 package metadata and imports
      -> #652 Docker-first test and image harness
        -> #653 descriptor catalogue
          -> #813-#817 cpk-server wrapper
          -> #654/#678/#655-#658 Hello transfer and proof
```

If issue numbers change after transfer, update this document and the source
parent issue in the same coordination PR.
