' NetWatch Silent Background Runner
Option Explicit
Dim WshShell, fso, currentDir, pyExe, cmd

Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)

pyExe = "C:\Users\Chaerul\AppData\Local\Programs\Python\Python310\python.exe"

WshShell.CurrentDirectory = currentDir
cmd = """" & pyExe & """ -m uvicorn main:app --host 0.0.0.0 --port 8080"
WshShell.Run cmd, 0, False
