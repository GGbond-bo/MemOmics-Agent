' 通用 Illustrator JSX 运行器（Windows / VBS + cscript）
' 用法（bash/MSYS）：cscript //nologo run_jsx.vbs "E:/path/to/x.jsx"
' jsx 内 return 的字符串会以 "RESULT: ..." 打印出来 —— 这就是唯一验收依据
On Error Resume Next
Dim app, res, p
If WScript.Arguments.Count = 0 Then
  WScript.Echo "USAGE: cscript //nologo run_jsx.vbs <absolute-jsx-path>"
  WScript.Quit 3
End If
p = WScript.Arguments(0)

Set app = CreateObject("Illustrator.Application")
If Err.Number <> 0 Then
  WScript.Echo "COM_FAIL: " & Err.Description
  WScript.Quit 1
End If

res = app.DoJavaScriptFile(p)
If Err.Number <> 0 Then
  WScript.Echo "JS_FAIL: " & Err.Description
  WScript.Quit 2
End If
WScript.Echo "RESULT: " & res