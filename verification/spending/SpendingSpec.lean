import Lean

/-!
Executable specification for currency-only spending summaries.

The trusted Python adapter supplies validated records, canonical raw-row
fingerprints, ordinal dates, and exact integer amounts in a shared unit for
each currency. CSV parsing, validation, and conversion are outside this proof.
No assumption that the unit is a cent is made here.
-/

set_option autoImplicit false

namespace SpendingVerification

open Lean

structure InputRecord where
  sourceRowId : String
  fingerprint : String
  status : String
  kind : String
  currency : String
  amount : Int
  day : Option Nat
deriving Repr, DecidableEq, FromJson, ToJson

structure Query where
  startDay : Option Nat
  endDay : Option Nat
deriving Repr, DecidableEq, FromJson, ToJson

structure CurrencyTotal where
  currency : String
  gross : Int
  refunds : Int
  net : Int
  hasExpenses : Bool
  hasRefunds : Bool
deriving Repr, DecidableEq, FromJson, ToJson

structure Summary where
  datasetId : String
  startDay : Option Nat
  endDay : Option Nat
  totals : List CurrencyTotal
  sourceRowIds : List String
  expenseCount : Nat
  refundCount : Nat
deriving Repr, DecidableEq, FromJson, ToJson

structure Request where
  protocolVersion : Nat
  datasetId : String
  query : Query
  records : List InputRecord
  claim : Summary
deriving Repr, FromJson, ToJson

/-- Keep the first OK occurrence of every canonical raw-row fingerprint. -/
def uniqueValid (seen : List String) : List InputRecord → List InputRecord
  | [] => []
  | row :: rest =>
    if row.status != "ok" then uniqueValid seen rest
    else if row.fingerprint ∈ seen then uniqueValid seen rest
    else row :: uniqueValid (row.fingerprint :: seen) rest

/-- Inclusive bounds. An undated record is eligible only with no bounds. -/
def withinPeriod (query : Query) (row : InputRecord) : Bool :=
  match row.day with
  | none => decide (query.startDay = none ∧ query.endDay = none)
  | some day =>
    let afterStart := match query.startDay with
      | none => true
      | some startDay => decide (startDay ≤ day)
    let beforeEnd := match query.endDay with
      | none => true
      | some endDay => decide (day ≤ endDay)
    afterStart && beforeEnd

/-- Select original, valid, in-period expenses and refunds in source order. -/
def selectedRows (records : List InputRecord) (query : Query) : List InputRecord :=
  (uniqueValid [] records).filter fun row =>
    withinPeriod query row && (row.kind == "expense" || row.kind == "refund")

def sumAmounts (rows : List InputRecord) : Int :=
  (rows.map (·.amount)).foldr (· + ·) 0

def totalsFor (rows : List InputRecord) (currency : String) : CurrencyTotal :=
  let expenses := rows.filter fun row => row.currency == currency && row.kind == "expense"
  let refunds := rows.filter fun row => row.currency == currency && row.kind == "refund"
  let gross := -(sumAmounts expenses)
  let refunded := sumAmounts refunds
  ⟨currency, gross, refunded, gross - refunded, !expenses.isEmpty, !refunds.isEmpty⟩

/-- Insert into the sorted, duplicate-free currency list. -/
def insertCurrency (currency : String) : List String → List String
  | [] => [currency]
  | first :: rest =>
    if currency = first then first :: rest
    else if currency ≤ first then currency :: first :: rest
    else first :: insertCurrency currency rest

def orderedCurrencies (rows : List InputRecord) : List String :=
  rows.foldr (fun row currencies => insertCurrency row.currency currencies) []

/-- The mathematical reference result, independent of the Python calculation. -/
def summarizeSpec (datasetId : String) (records : List InputRecord) (query : Query) : Summary :=
  let selected := selectedRows records query
  let currencies := orderedCurrencies selected
  { datasetId := datasetId
    startDay := query.startDay
    endDay := query.endDay
    totals := currencies.map (totalsFor selected)
    sourceRowIds := selected.map (·.sourceRowId)
    expenseCount := (selected.filter (fun row => row.kind == "expense")).length
    refundCount := (selected.filter (fun row => row.kind == "refund")).length }

/-- Correctness includes key presence, provenance, counts, and query metadata. -/
def CorrectSummary (datasetId : String) (records : List InputRecord)
    (query : Query) (claim : Summary) : Prop :=
  claim = summarizeSpec datasetId records query

def check (datasetId : String) (records : List InputRecord)
    (query : Query) (claim : Summary) : Bool :=
  decide (claim = summarizeSpec datasetId records query)

/-- Every accepted result equals the specified result on these exact inputs. -/
theorem check_sound {datasetId : String} {records : List InputRecord}
    {query : Query} {claim : Summary}
    (accepted : check datasetId records query claim = true) :
    CorrectSummary datasetId records query claim := by
  change claim = summarizeSpec datasetId records query
  exact of_decide_eq_true accepted

theorem check_complete {datasetId : String} {records : List InputRecord}
    {query : Query} {claim : Summary}
    (correct : CorrectSummary datasetId records query claim) :
    check datasetId records query claim = true := by
  unfold check
  change claim = summarizeSpec datasetId records query at correct
  exact decide_eq_true correct

theorem accepted_reports_agree {datasetId : String} {records : List InputRecord}
    {query : Query} {first second : Summary}
    (hfirst : check datasetId records query first = true)
    (hsecond : check datasetId records query second = true) : first = second := by
  exact Eq.trans (check_sound hfirst) (Eq.symm (check_sound hsecond))

theorem accepted_source_rows {datasetId : String} {records : List InputRecord}
    {query : Query} {claim : Summary}
    (accepted : check datasetId records query claim = true) :
    claim.sourceRowIds = (selectedRows records query).map (·.sourceRowId) := by
  have correct := check_sound accepted
  exact congrArg Summary.sourceRowIds correct

theorem specified_net_is_gross_minus_refunds
    (rows : List InputRecord) (currency : String) :
    (totalsFor rows currency).net =
      (totalsFor rows currency).gross - (totalsFor rows currency).refunds := by
  rfl

/-- Reject unsupported wire versions and unknown outcome/type labels. -/
def supported (request : Request) : Bool :=
  request.protocolVersion == 1 && request.records.all fun row =>
    (row.status == "invalid" || row.status == "error") ||
      (row.status == "ok" &&
        (row.kind == "expense" || row.kind == "refund" || row.kind == "income" ||
          row.kind == "transfer_in" || row.kind == "transfer_out"))

def checkRequest (request : Request) : Bool :=
  supported request && check request.datasetId request.records request.query request.claim

theorem request_check_sound (request : Request)
    (accepted : checkRequest request = true) :
    CorrectSummary request.datasetId request.records request.query request.claim := by
  cases hs : supported request with
  | false => simp [checkRequest, hs] at accepted
  | true =>
    apply check_sound
    simpa [checkRequest, hs] using accepted

/-- Pure wire handler, also exercised by the native integration tests. -/
def handle (line : String) : UInt32 × String :=
  match Json.parse line >>= (fromJson? (α := Request)) with
  | .error message =>
    (2, (Json.mkObj [("protocolVersion", toJson (1 : Nat)),
      ("accepted", toJson false), ("error", toJson message)]).compress)
  | .ok request =>
    let accepted := checkRequest request
    let message := if !supported request then "unsupported request"
      else if accepted then "verified currency totals and source rows"
      else "summary does not match the spending specification"
    (if accepted then 0 else 1,
      (Json.mkObj [("protocolVersion", toJson (1 : Nat)),
        ("accepted", toJson accepted), ("message", toJson message)]).compress)

end SpendingVerification
