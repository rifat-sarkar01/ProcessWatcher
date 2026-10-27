# Process Watcher Directory Architecture Setup Script
$ErrorActionPreference = "Stop"

$dirs = @(
    "docs/adr",
    "docs/results",
    "docs/security",
    "docs/bench",
    "docs/demo",
    "docs/submission",
    "docs/finals/explainers",
    "contracts/schemas",
    "contracts/examples",
    "src/pw/api",
    "src/pw/clients",
    "src/pw/core",
    "src/pw/ingest",
    "src/pw/pipeline",
    "src/pw/security",
    "src/pw/perception",
    "src/pw/timeline",
    "src/pw/sop",
    "src/pw/align",
    "src/pw/illustrate",
    "src/pw/evidence",
    "src/pw/report",
    "src/pw/bench",
    "src/pw/data",
    "src/pw/demo",
    "tests/api",
    "tests/clients",
    "tests/core",
    "tests/ingest",
    "tests/pipeline",
    "tests/security",
    "tests/perception",
    "tests/timeline",
    "tests/sop",
    "tests/align",
    "tests/illustrate",
    "tests/evidence",
    "tests/report",
    "tests/bench",
    "tests/data",
    "tests/demo",
    "tests/robustness",
    "tests/fixtures",
    "web/src/app",
    "web/src/api",
    "web/src/ui",
    "web/src/features",
    "web/src/types/generated",
    "web/e2e",
    "bench/sops",
    "bench/golden",
    "bench/dev",
    "bench/heldout",
    "config",
    "demo/cases",
    "scripts"
)

foreach ($d in $dirs) {
    if (-not (Test-Path $d)) {
        New-Item -ItemType Directory -Path $d -Force | Out-Null
    }
    $keepPath = Join-Path $d ".gitkeep"
    if (-not (Test-Path $keepPath)) {
        New-Item -ItemType File -Path $keepPath -Force | Out-Null
    }
}

# Move documentation files to docs/ as specified by repository architecture
$docFiles = @(
    "01_PRD.md",
    "02_AppFlow.md",
    "03_UI_Spec.md",
    "04_TRD.md",
    "05_Schema.md",
    "06_Plan.md",
    "PROGRESS.md"
)

foreach ($f in $docFiles) {
    if (Test-Path $f) {
        Copy-Item -Path $f -Destination "docs/$f" -Force
    }
}

Write-Host "Directory scaffolding and doc sync completed successfully."
