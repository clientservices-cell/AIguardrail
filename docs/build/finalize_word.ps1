<#
.SYNOPSIS
  Finalise a generated .docx in Microsoft Word: fill in the table of contents and
  every other field, then save. Optionally export a PDF preview.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File finalize_word.ps1 -In raw.docx -Out final.docx -Pdf preview.pdf
#>
param(
  [Parameter(Mandatory = $true)][string]$In,
  [Parameter(Mandatory = $true)][string]$Out,
  [string]$Pdf
)
$ErrorActionPreference = "Stop"
$In = (Resolve-Path $In).Path
$Out = [System.IO.Path]::GetFullPath($Out)
if ($Pdf) { $Pdf = [System.IO.Path]::GetFullPath($Pdf) }

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
  $doc = $word.Documents.Open($In, $false, $false)
  foreach ($toc in $doc.TablesOfContents) { $toc.Update() }
  $doc.Fields.Update() | Out-Null
  $doc.SaveAs2($Out, 16)                               # wdFormatXMLDocument
  if ($Pdf) { $doc.ExportAsFixedFormat($Pdf, 17) }      # wdExportFormatPDF
  # Word sometimes drops the COM connection after exporting; the files are already
  # written by then, so a failure to close cleanly is not an error.
  try { $doc.Close($false) } catch {}
}
finally {
  try { $word.Quit() } catch {}
  [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
if (-not (Test-Path $Out)) { throw "Word did not write $Out" }
