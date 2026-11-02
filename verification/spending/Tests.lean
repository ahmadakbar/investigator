import SpendingSpec

set_option autoImplicit false

open SpendingVerification

def expense : InputRecord :=
  ⟨"demo:1", "same raw fields", "ok", "expense", "EUR", -10000, some 100⟩

def duplicate : InputRecord := { expense with sourceRowId := "demo:2" }

def refund : InputRecord :=
  ⟨"demo:3", "refund raw fields", "ok", "refund", "EUR", 2000, some 101⟩

def undated : InputRecord :=
  ⟨"demo:4", "undated raw fields", "ok", "expense", "USD", -500, none⟩

def demoRows : List InputRecord := [expense, duplicate, refund, undated]
def unbounded : Query := ⟨none, none⟩
def bounded : Query := ⟨some 100, some 101⟩

example : (summarizeSpec "demo" demoRows unbounded).sourceRowIds =
    ["demo:1", "demo:3", "demo:4"] := by decide

example : (summarizeSpec "demo" demoRows bounded).sourceRowIds =
    ["demo:1", "demo:3"] := by decide

example : (summarizeSpec "demo" demoRows bounded).totals =
    [⟨"EUR", 10000, 2000, 8000, true, true⟩] := by decide

example : check "demo" demoRows bounded (summarizeSpec "demo" demoRows bounded) = true := by decide

def wrong : Summary :=
  { (summarizeSpec "demo" demoRows bounded) with
    totals := [⟨"EUR", 10000, 2000, 8001, true, true⟩] }

example : check "demo" demoRows bounded wrong = false := by decide

#print axioms SpendingVerification.check_sound
#print axioms SpendingVerification.request_check_sound
#print axioms SpendingVerification.accepted_reports_agree
#print axioms SpendingVerification.accepted_source_rows
#print axioms SpendingVerification.specified_net_is_gross_minus_refunds
