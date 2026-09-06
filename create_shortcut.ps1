$desktop = [Environment]::GetFolderPath('Desktop')
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut("$desktop\Ant Esports Cooler.lnk")
$sc.TargetPath = "c:\Projects\AntEsports\Run_As_Admin.bat"
$sc.WorkingDirectory = "c:\Projects\AntEsports"
$sc.Description = "Ant Esports ICEStorm-240 Control Center (Admin)"
$sc.IconLocation = "$env:SystemRoot\System32\shell32.dll,238"
$sc.Save()
Write-Host "Updated desktop shortcut to Run_As_Admin.bat"
