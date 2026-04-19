// Puppeteer launch options for md-to-pdf (headless PDF generation).
//
// Why these flags:
//   --no-sandbox + --disable-setuid-sandbox
//       Required in CI containers and rootless environments where the
//       kernel does not permit Chromium's sandbox user-namespace setup.
//       Safe here because the renderer only opens local trusted
//       markdown input — no untrusted URLs.
//   --disable-dev-shm-usage
//       Avoids CI runners with small /dev/shm (< 64 MB default in
//       many Docker images) which otherwise crash Chromium with
//       SIGBUS while rendering large tables/images.
//
// This file is referenced by scripts/regen_framework_pdf.sh via
// md-to-pdf's --config-file flag.  Do NOT pass these same flags via
// --launch-options on the command line — the two are redundant and
// drift apart.
//
// Iron rule 5 reminder: if md-to-pdf exits non-zero, diagnose the
// root cause (usually a Chromium version mismatch or a missing glibc
// dep). Do not add flags to silence crashes.

module.exports = {
  launch_options: {
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
    ],
  },
  pdf_options: {
    format: "A4",
    margin: {
      top: "20mm",
      right: "18mm",
      bottom: "20mm",
      left: "18mm",
    },
    printBackground: true,
  },
};
