Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "c:\Projects\AntEsports"
WshShell.Run "pythonw.exe main.py", 0, False
