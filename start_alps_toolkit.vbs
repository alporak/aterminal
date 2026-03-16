' Alps Toolkit – Silent Startup Launcher
' Place this file (or a shortcut to it) in shell:startup
' to auto-launch Alps Toolkit on Windows login.
'
' Strategy: set cwd to project root → run "python tray_launcher.py"
' with a hidden window (style 0). The tray_launcher.py also hides
' its own console via ctypes as a second safety net.
'
' No pythonw detection needed — window style 0 suppresses the console.

Dim objShell, objFSO, strDir

Set objShell = CreateObject("WScript.Shell")
Set objFSO   = CreateObject("Scripting.FileSystemObject")

strDir = objFSO.GetParentFolderName(WScript.ScriptFullName)

If Not objFSO.FileExists(objFSO.BuildPath(strDir, "tray_launcher.py")) Then
    MsgBox "Alps Toolkit: tray_launcher.py not found in:" & vbCrLf & strDir, _
           vbExclamation, "Alps Toolkit"
    WScript.Quit 1
End If

' Set working directory — uvicorn resolves "run:app" relative to cwd
objShell.CurrentDirectory = strDir

' Run with hidden window (0) and don't wait (False)
objShell.Run "python """ & objFSO.BuildPath(strDir, "tray_launcher.py") & """", 0, False

Set objShell = Nothing
Set objFSO   = Nothing
