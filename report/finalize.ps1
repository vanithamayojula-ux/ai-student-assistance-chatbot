# Refreshes the table of contents and the lists of figures and tables in the report,
# then saves it and writes a PDF copy next to it. Needs Microsoft Word.
#   powershell -ExecutionPolicy Bypass -File report\finalize.ps1
$docx = Join-Path $PSScriptRoot "AI_Student_Assistance_Chatbot_Report.docx"
$pdf = [System.IO.Path]::ChangeExtension($docx, ".pdf")
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    $doc = $word.Documents.Open($docx, $false, $false)
    $doc.Repaginate()
    foreach ($toc in $doc.TablesOfContents) { $toc.Update() }
    $doc.Fields.Update() | Out-Null
    foreach ($toc in $doc.TablesOfContents) { $toc.UpdatePageNumbers() }
    $doc.Save()
    $doc.ExportAsFixedFormat($pdf, 17)
    "pages: " + $doc.ComputeStatistics(2)
    $doc.Close($false)
}
finally {
    $word.Quit()
}
