# Run this once to add a resiDNA icon to your Desktop.
# Right-click this file -> "Run with PowerShell" (or run it from a PowerShell
# window). You only need to do this once; the shortcut keeps working after.

$AppDir = $PSScriptRoot
$LauncherPath = Join-Path $AppDir "Run_resiDNA_App.bat"
$IconPath = Join-Path $AppDir "app\assets\resiDNA.ico"
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $DesktopPath "resiDNA Sample Analysis Tool.lnk"

if (-not (Test-Path $LauncherPath)) {
    Write-Host "ERROR: Run_resiDNA_App.bat not found next to this script. Keep this script in the same folder as the app." -ForegroundColor Red
    exit 1
}

$WScriptShell = New-Object -ComObject WScript.Shell
$Shortcut = $WScriptShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $LauncherPath
$Shortcut.WorkingDirectory = $AppDir
if (Test-Path $IconPath) {
    $Shortcut.IconLocation = $IconPath
}
$Shortcut.Description = "Open the resiDNA Sample Analysis Tool"
$Shortcut.Save()

Write-Host "Desktop shortcut created: $ShortcutPath" -ForegroundColor Green
Write-Host "Double-click it anytime to open the app."
