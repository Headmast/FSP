// Executable checks for the Swift examples and dispatch semantics in ios-swift-1.
let optional: Int? = nil
print(optional ?? 7)
struct S { var n = 1 }
let a = S()
var b = a
b.n = 2
print(a.n)
class Box { var n = 1 }
let box = Box()
let alias = box
box.n = 2
print(alias.n)
protocol P {}
extension P { func f() -> String { "extension" } }
struct Concrete: P { func f() -> String { "concrete" } }
let value: any P = Concrete()
print(value.f())
