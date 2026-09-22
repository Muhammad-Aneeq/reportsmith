<#
.SYNOPSIS
  Windows parity for the Makefile. There is no `make` on this box (BLOCKERS B1).

  The Makefile stays authoritative and is what CI runs; this mirrors it target for target.
  `tests/test_docs_and_tooling.py` asserts the two expose the same set of targets, because
  a parity claim nobody checks stops being true almost immediately.

.EXAMPLE
  ./make.ps1 demo
  ./make.ps1 test
#>
param([Parameter(Position = 0)][string]$Target = 'help')

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$py = Join-Path $root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }

function Run([string]$dir, [string[]]$cmd) {
    Push-Location (Join-Path $root $dir)
    try {
        & $cmd[0] @($cmd[1..($cmd.Length - 1)])
        if ($LASTEXITCODE -ne 0) { throw "$($cmd -join ' ') exited $LASTEXITCODE" }
    }
    finally { Pop-Location }
}

switch ($Target) {
    'help' {
        Write-Host 'ReportSmith targets:'
        @(
            'install      Install backend (uv) and frontend (npm) dependencies',
            'dev          Run the API and the SPA together - the demo entrypoint',
            'dev-api      Run the FastAPI backend with reload',
            'dev-web      Run the Vite dev server',
            'up           Alias for dev',
            'down         Stop docker compose',
            'demo         Both periods end to end, then the month diff',
            'month1       Assemble, approve, waive, sign and archive the first period',
            'month2       The same template on the NEXT period',
            'diff         Show the month-diff verdict',
            'fixtures     Regenerate the SpendSort export fixtures by RUNNING SpendSort',
            'capture      Screenshot + VERIFY all six screens headless (needs make dev running)',
            'record       Record docs/demo.webm by driving the real app (needs make dev running)',
            'golden       Regenerate the committed golden assembly files',
            'test         Lint, typecheck, then the full suite (LLM mocked)',
            'test-fast    Tests only',
            'test-live    Tests that hit a real model (needs OPENAI_API_KEY)',
            'lint         ruff check',
            'fmt          ruff format (writes)',
            'typecheck    mypy + tsc',
            'evals        Run the three gates',
            'evals-gate   What CI runs, including the self-test that proves a gate can fail',
            'clean        Remove the local DB, caches and build output'
        ) | ForEach-Object { Write-Host "  $_" }
    }
    'install' {
        Run 'backend' @('uv', 'venv')
        Run 'backend' @('uv', 'pip', 'install', '-e', '.[dev]')
        Run 'frontend' @('npm', 'install')
    }
    'dev' {
        Write-Host 'API  -> http://localhost:8000/docs'
        Write-Host 'SPA  -> http://localhost:5173'
        Start-Process -FilePath $py -ArgumentList '-m', 'uvicorn', 'app.main:app', '--reload', '--port', '8000' -WorkingDirectory (Join-Path $root 'backend')
        Run 'frontend' @('npm', 'run', 'dev')
    }
    'dev-api' { Run 'backend' @($py, '-m', 'uvicorn', 'app.main:app', '--reload', '--port', '8000') }
    'dev-web' { Run 'frontend' @('npm', 'run', 'dev') }
    'up' { & $PSCommandPath 'dev' }
    'down' { Run '.' @('docker', 'compose', 'down') }
    'demo' { Run 'backend' @($py, '-m', 'app.cli', 'demo') }
    'month1' { Run 'backend' @($py, '-m', 'app.cli', 'month1') }
    'month2' { Run 'backend' @($py, '-m', 'app.cli', 'month2') }
    'diff' { Run 'backend' @($py, '-m', 'app.cli', 'demo') }
    'fixtures' { Run '.' @($py, 'fixtures/gen_fixtures.py') }
    'capture' { Run 'frontend' @('node', 'capture.mjs') }
    'record' { Run 'frontend' @('node', 'record-demo.mjs') }
    'golden' { Run '.' @($py, 'evals/make_golden.py') }
    'test' {
        & $PSCommandPath 'lint'
        & $PSCommandPath 'typecheck'
        Run 'backend' @($py, '-m', 'pytest', '-q', '-m', 'not live')
        Run 'frontend' @('npm', 'run', 'test')
    }
    'test-fast' { Run 'backend' @($py, '-m', 'pytest', '-q', '-m', 'not live') }
    'test-live' {
        $env:REPORTSMITH_LLM = 'live'
        Run 'backend' @($py, '-m', 'pytest', '-q', '-m', 'live')
    }
    'lint' {
        Run 'backend' @($py, '-m', 'ruff', 'check', 'app', 'tests')
        Run 'backend' @($py, '-m', 'ruff', 'check', 'numcheck')
    }
    'fmt' { Run 'backend' @($py, '-m', 'ruff', 'format', 'app', 'tests', 'numcheck') }
    'typecheck' {
        Run 'backend' @($py, '-m', 'mypy', 'app')
        Run 'frontend' @('npm', 'run', 'typecheck')
    }
    'evals' {
        Run '.' @($py, 'evals/run_fidelity.py')
        Run '.' @($py, 'evals/run_e2e.py')
    }
    'evals-gate' {
        Run '.' @($py, 'evals/run_fidelity.py')
        Run '.' @($py, 'evals/run_fidelity.py', '--self-test')
        Run '.' @($py, 'evals/run_e2e.py')
        Run 'backend' @($py, '-m', 'pytest', '-q', 'tests/test_state_machine.py', 'tests/test_no_silent_omission.py')
    }
    'clean' {
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $root 'backend\reportsmith.db'), (Join-Path $root 'archive'), (Join-Path $root 'frontend\dist')
        Get-ChildItem -Path $root -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }
    default {
        Write-Error "Unknown target '$Target'. Run ./make.ps1 help"
        exit 1
    }
}
