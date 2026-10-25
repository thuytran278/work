Sub Size_Personalise()
'
' Size_Personalise Macro (fixed)
' - Khong dung End(xlDown) nua (gap o dong qua tang lam macro dung giua chung)
' - Dong FREEGIFT: ghi ten qua tang (vd XMASBAG) vao cot G, qty vao cot H
'
    Dim ws As Worksheet
    Dim lastRow As Long, r As Long
    Dim parts() As String
    Dim lastPart As String

    Set ws = ActiveSheet
    lastRow = ws.Cells(ws.Rows.Count, "E").End(xlUp).Row
    If lastRow < 2 Then Exit Sub

    ' Don vung helper P:W de khong con du lieu cu
    ws.Range("P2:W" & lastRow).ClearContents

    ' E -> P, tach theo "_" thanh P:V
    ws.Range("P2:P" & lastRow).Value = ws.Range("E2:E" & lastRow).Value
    ws.Range("P2:P" & lastRow).TextToColumns Destination:=ws.Range("P2"), _
        DataType:=xlDelimited, TextQualifier:=xlDoubleQuote, _
        ConsecutiveDelimiter:=False, Tab:=False, Semicolon:=False, _
        Comma:=False, Space:=False, Other:=True, OtherChar:="_", _
        FieldInfo:=Array(Array(1, 1), Array(2, 1), Array(3, 1), Array(4, 1), _
        Array(5, 1), Array(6, 1), Array(7, 1)), TrailingMinusNumbers:=True

    ' V -> tach theo "*" thanh V (size) va W (qty)
    ws.Range("V2:V" & lastRow).TextToColumns Destination:=ws.Range("V2"), _
        DataType:=xlDelimited, TextQualifier:=xlDoubleQuote, _
        ConsecutiveDelimiter:=False, Tab:=False, Semicolon:=False, _
        Comma:=False, Space:=False, Other:=True, OtherChar:="*", _
        FieldInfo:=Array(Array(1, 1), Array(2, 1)), TrailingMinusNumbers:=True

    ' V:W -> G:H (gia tri), T -> J (gia tri)
    ws.Range("G2:H" & lastRow).Value = ws.Range("V2:W" & lastRow).Value
    ws.Range("J2:J" & lastRow).Value = ws.Range("T2:T" & lastRow).Value

    ws.Range("J2:J" & lastRow).Replace What:="No", Replacement:="", LookAt:=xlPart, _
        SearchOrder:=xlByRows, MatchCase:=False
    ws.Range("J2:J" & lastRow).Replace What:="Retro", Replacement:="", LookAt:=xlPart, _
        SearchOrder:=xlByRows, MatchCase:=False

    ' Dong qua tang: KFK_FREEGIFT_XMASBAG_2026*1 -> G = XMASBAG, H = qty sau dau *
    For r = 2 To lastRow
        If UCase(Trim(ws.Cells(r, "Q").Value)) = "FREEGIFT" Then
            ws.Cells(r, "G").Value = ws.Cells(r, "R").Value
            ws.Cells(r, "J").ClearContents
            parts = Split(CStr(ws.Cells(r, "E").Value), "*")
            lastPart = Trim(parts(UBound(parts)))
            If UBound(parts) > 0 And IsNumeric(lastPart) Then
                ws.Cells(r, "H").Value = CLng(lastPart)
            End If
        End If
    Next r
End Sub
