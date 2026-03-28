// afterPack.js — Ad-hoc codesign the entire .app bundle after electron-builder packs it.
// This signs all Mach-O binaries (including PyInstaller backend) so the app
// is not flagged as "broken" on other Macs.
//
// Signing order matters:
//   1. Sign standalone Mach-O files (dylibs, .so) that --deep might miss
//   2. Deep-sign the entire .app (catches Electron framework, helpers, etc.)
//   3. Re-sign limactl WITH entitlements (--deep stripped them in step 2)
//   4. Re-seal the outer .app WITHOUT --deep (updates the bundle seal
//      to reflect limactl's new signature, without touching inner binaries)

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

  // 1. Pre-sign standalone Mach-O files inside backend resources.
  //    These are loose binaries (not in .framework bundles), so --deep on
  //    the outer .app may not discover all of them.
  const backendDir = path.join(appPath, "Contents", "Resources", "backend");
  if (fs.existsSync(backendDir)) {
    console.log("[afterPack] Signing backend binaries...");
    try {
      execSync(
        `find "${backendDir}" -type f \\( -name "*.dylib" -o -name "*.so" \\) -exec codesign --force --sign - {} \\;`,
        { stdio: "inherit" }
      );
      const backendBin = path.join(backendDir, "clawwork_api_server");
      if (fs.existsSync(backendBin)) {
        execSync(`codesign --force --sign - "${backendBin}"`, {
          stdio: "inherit",
        });
      }
    } catch (err) {
      console.warn("[afterPack] Warning signing backend:", err.message);
    }
  }

  // 2. Deep-sign the entire .app bundle.  This recursively signs everything
  //    including Electron Framework, helper apps, and limactl.  All inner
  //    binaries get a plain ad-hoc signature (no entitlements).
  console.log("[afterPack] Deep-signing .app bundle...");
  execSync(
    `codesign --force --deep --sign - "${appPath}"`,
    { stdio: "inherit" }
  );

  // 3. Re-sign limactl with the virtualization entitlement.
  //    Step 2 overwrote limactl's signature without entitlements — we must
  //    apply it again AFTER the deep sign.
  const limaBin = path.join(appPath, "Contents", "Resources", "lima", "bin", "limactl");
  const entitlements = path.join(__dirname, "..", "..", "..", "clawwork", "sandbox", "vm", "lima", "entitlements.plist");
  if (fs.existsSync(limaBin)) {
    if (!fs.existsSync(entitlements)) {
      console.error("[afterPack] FATAL: entitlements.plist not found at", entitlements);
      console.error("[afterPack] limactl will not have virtualization entitlement — VZ VMs will fail to start");
    } else {
      console.log("[afterPack] Re-signing limactl with virtualization entitlement...");
      try {
        execSync(`codesign --force --sign - --entitlements "${entitlements}" "${limaBin}"`, { stdio: "inherit" });
      } catch (err) {
        console.warn("[afterPack] Warning signing limactl:", err.message);
      }
    }
  }

  // 4. Re-seal the outer .app (WITHOUT --deep).
  //    Signing without --deep updates only the bundle's seal to reflect
  //    limactl's new signature — it does not recurse into or re-sign any
  //    nested binaries, so the entitlement from step 3 is preserved.
  console.log("[afterPack] Re-sealing .app bundle...");
  execSync(
    `codesign --force --sign - "${appPath}"`,
    { stdio: "inherit" }
  );

  // 5. Verify the full bundle
  try {
    execSync(`codesign --verify --deep --strict "${appPath}"`, {
      stdio: "inherit",
    });
    console.log("[afterPack] Ad-hoc signing verified successfully.");
  } catch (err) {
    console.warn("[afterPack] Verification warning:", err.message);
  }
};
