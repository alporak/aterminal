Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
ScriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)

' Run the Python tray application
cmd = "pythonw " & Chr(34) & ScriptDir & "\streamlit_tray.py" & Chr(34)
WshShell.Run cmd, 0, False

Set FSO = Nothing
Set WshShell = Nothing
