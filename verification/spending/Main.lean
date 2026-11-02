import SpendingSpec

def main : IO UInt32 := do
  let stdin ← IO.getStdin
  let stdout ← IO.getStdout
  let line ← stdin.getLine
  let (code, response) := SpendingVerification.handle line
  stdout.putStrLn response
  return code
