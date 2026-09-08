' Windows silent launcher (launches mkvis3d without showing a cmd console window)
Set WshShell = CreateObject("WScript.Shell")
strDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strDir & "\.."
If CreateObject("Scripting.FileSystemObject").FileExists(strDir & "\..\dist\mkvis3d.exe") Then
    WshShell.Run """" & strDir & "\..\dist\mkvis3d.exe""", 0, False
Else
    WshShell.Run "cmd /c uv run mkvis3d gui", 0, False
End If
