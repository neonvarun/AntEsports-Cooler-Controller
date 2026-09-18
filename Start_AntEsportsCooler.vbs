Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
AppDir = FSO.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = AppDir
PythonW = AppDir & "\.venv\Scripts\pythonw.exe"
If Not FSO.FileExists(PythonW) Then PythonW = "pythonw.exe"
WshShell.Run Chr(34) & PythonW & Chr(34) & " " & Chr(34) & AppDir & "\main.py" & Chr(34), 0, False
