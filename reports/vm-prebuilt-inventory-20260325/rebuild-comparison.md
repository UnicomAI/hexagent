# openagent-prebuilt Rebuild Comparison (2026-03-25)

## Summary

- Old prebuilt tar (before clean rebuild): `6,693,079,040` bytes (`6.23 GB`)
- New prebuilt tar (rebuilt from clean `openagent-build` + current setup scripts): `2,019,061,760` bytes (`1.88 GB`)
- Delta: `-4,674,017,280` bytes (`-4.35 GB`, about `-69.8%`)

## Hash

- Old SHA256: `61279AF095540D3C1290BDF8B2BA1F4094BD128C347E873BEF0F9D25A56986D6`
- New SHA256: `8D8F7F8718891C8242DEE44409EA92EB57B912FCBA53F427622C2DE70B92A022`

## Package Count Changes

- APT packages:
  - old: `964`
  - new: `386`
  - source files:
    - `apt-installed.txt`
    - `apt-installed-new.txt`
- Python packages:
  - old: `83` (from old dist-info snapshot extraction)
  - new: `35` (from `pip list --format=freeze` in rebuilt distro)
  - source files:
    - `pip-dist-info.txt`
    - `pip-freeze-new.txt`
- NPM global packages:
  - old: `22`
  - new: `5`
  - source files:
    - `npm-global.txt`
    - `npm-global-new.txt`

## New Prebuilt Size Hotspots

Top large files (`>50 MB`) in rebuilt tar:

- `opt/pw-browsers/chromium-1208/chrome-linux64/chrome` (`257.28 MB`)
- `opt/pw-browsers/chromium_headless_shell-1208/chrome-headless-shell-linux64/chrome-headless-shell` (`175.05 MB`)
- `usr/bin/node` (`118.90 MB`)
- `usr/lib/x86_64-linux-gnu/libLLVM-15.so.1` (`111.46 MB`)
- `usr/local/bin/uv` (`56.33 MB`)

## Notes

- During the first rebuild attempt, `05_pip.sh` did not fail even when pip installs failed.
- Root causes fixed in source:
  - `setup.sh`: `pip_install` now conditionally adds `--break-system-packages` only when supported.
  - `05_pip.sh`: now uses `set -euo pipefail` to fail fast on pip errors.
  - `03_apt.sh`: each `apt_install` call now hard-fails on error (`|| exit 1`).
- After fixes, rebuild completed and dependencies were actually installed.
