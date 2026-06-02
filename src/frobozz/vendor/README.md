# Vendored Dependencies

This directory contains third-party code that has been copied ("vendored") into the Frobozz repository for stability and reproducibility.

## xyppy

**Source:** https://github.com/theinternetftw/xyppy
**Commit:** bdfe173771f414538e4e2f14d03eb092dbaf20bc
**Date vendored:** October 1, 2025 (re-vendored into Frobozz from Frotzmark, June 2, 2026)
**License:** MIT (see `xyppy/LICENSE`)

xyppy is a Z-machine interpreter written in Python. We vendor it to ensure:
- Long-term reproducibility of research results
- Independence from upstream changes or repository availability
- Explicit control over the exact version used in experiments

### Why vendored instead of dependency?

For academic/research software, vendoring critical dependencies ensures that experiments remain reproducible years into the future, regardless of changes to upstream repositories or package availability.

### Modifications

Currently using xyppy unmodified. We provide our own `Screen` implementation for programmatic control of game I/O, but the core Z-machine implementation remains unchanged.
