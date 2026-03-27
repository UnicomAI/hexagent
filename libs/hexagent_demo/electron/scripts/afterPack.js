// afterPack.js — Ad-hoc codesign the entire .app bundle after electron-builder packs it.
// This signs all Mach-O binaries (including PyInstaller backend) so the app
// is not flagged as "broken" on other Macs.

const { execSync } = require("child_process");
const path = require("path");
const fs = require("fs");

exports.default = async function afterPack(context) {
  if (process.platform !== "darwin") return;

  const appPath = path.join(
    context.appOutDir,
    `${context.packager.appInfo.productFilename}.app`
  );

  console.log(`[afterPack] Ad-hoc signing: ${appPath}`);

  // 1. Sign all binaries inside the backend resources (PyInstaller output).
  //    We must sign inner binaries before signing the outer .app bundle.
  const backendDir = path.join(appPath, "Contents", "Resources", "backend");
  if (fs.existsSync(backendDir)) {
    console.log("[afterPack] Signing backend binaries...");

    // Find and sign all Mach-O files (dylibs and executables) inside backend/
    try {
      // Sign .dylib and .so files first (inner before outer)
      execSync(
        `find "${backendDir}" -type f \\( -name "*.dylib" -o -name "*.so" \\) -exec codesign --force --deep --sign - {} \\;`,
        { stdio: "inherit" }
      );

      // Sign the main backend executable
      const backendBin = path.join(backendDir, "hexagent_api_server");
      if (fs.existsSync(backendBin)) {
        execSync(`codesign --force --deep --sign - "${backendBin}"`, {
          stdio: "inherit",
        });
      }
    } catch (err) {
      console.warn("[afterPack] Warning signing backend:", err.message);
    }
  }

  // 2. Sign bundled Lima binary
  const limaBin = path.join(appPath, "Contents", "Resources", "lima", "bin", "limactl");
  if (fs.existsSync(limaBin)) {
    console.log("[afterPack] Signing limactl...");
    try {
      execSync(`codesign --force --sign - "${limaBin}"`, { stdio: "inherit" });
    } catch (err) {
      console.warn("[afterPack] Warning signing limactl:", err.message);
    }
  }

  // 3. Sign the entire .app bundle with ad-hoc identity
  console.log("[afterPack] Signing .app bundle...");
  execSync(
    `codesign --force --deep --sign - "${appPath}"`,
    { stdio: "inherit" }
  );

  // 3. Verify
  try {
    execSync(`codesign --verify --deep --strict "${appPath}"`, {
      stdio: "inherit",
    });
    console.log("[afterPack] Ad-hoc signing verified successfully.");
  } catch (err) {
    console.warn("[afterPack] Verification warning:", err.message);
  }
};
