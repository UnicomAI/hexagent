# Windows Installer Regression Checklist (No-WSL Machine)

## 0. Test Environment
- Fresh Windows 10/11 x64 machine (no OpenAgent, no WSL distro).
- Verify:
  - `wsl --status` shows not installed or unavailable.
  - `wsl -l -v` has no `openagent` distro.

## 1. Install App
- Run `OpenAgent-0.0.1-win-x64.exe`.
- Open OpenAgent -> Settings -> Sandbox.
- Expected:
  - App launches normally.
  - No crash on Sandbox page.

## 2. Assisted WSL Install (First-time)
- Click VM setup / Retry on `VM Engine`.
- Expected:
  - If WSL missing: clear guided message appears.
  - App attempts assisted install (with clear status text).
  - If system needs reboot, UI explicitly asks reboot.

## 3. Reboot Required Path
- If prompted, reboot Windows.
- Re-open OpenAgent -> Sandbox.
- Click Retry again.
- Expected:
  - `VM Instance` eventually becomes `Ready`.
  - No `exit 4294967295` generic toast without guidance.

## 4. VM Dependencies Install
- Click install for `VM System Dependencies`.
- Expected:
  - Progress steps update continuously.
  - Failure (if any) includes actionable reason.
  - Success ends with green/ready state.

## 5. Cowork Functional Smoke Test
- Set cowork folder to a writable path, e.g. `D:\code\agentTest`.
- In chat:
  - Create folder `sport`.
  - Then create `sport\basketball`.
- Expected:
  - Both operations succeed.
  - No false "current directory not writable" error.

## 6. Non-Technical User UX Check
- Trigger BIOS/virtualization-disabled scenario (or validate copy via mocked error).
- Expected:
  - Error includes clear next steps:
    - Enable virtualization in BIOS (Intel VT-x / AMD SVM).
    - Save BIOS and reboot.
    - Retry in app.
  - Language is understandable for non-technical users.

## 7. Log Collection (On Failure)
- Collect:
  - OpenAgent backend logs.
  - Sandbox setup UI log panel output.
  - `wsl --status`
  - `wsl -l -v`
- Record exact toast error text and timestamp.

## 8. Release Gate (Pass Criteria)
- Must pass:
  - App install + launch.
  - WSL guided install path.
  - Reboot path.
  - VM Instance ready.
  - VM dependencies ready.
  - Cowork nested directory creation.
- Block release if any of above fails.

