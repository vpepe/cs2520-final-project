#!/usr/bin/env python3
"""
Create very simple lambda calculus examples that Stitch can definitely handle.
This will test if Stitch Python bindings work at all.
"""
import json

# Create simple programs that should work
simple_programs = [
    # Identity function: λx. x
    "(lam 0)",

    # Constant function: λx. λy. x
    "(lam (lam 1))",

    # Apply twice: λf. λx. f (f x)
    "(lam (lam (app 1 (app 1 0))))",

    # Composition: λf. λg. λx. f (g x)
    "(lam (lam (lam (app 2 (app 1 0)))))",

    # Simple arithmetic: λx. x + 1
    "(lam (app (app add 0) 1))",

    # λx. x + 2
    "(lam (app (app add 0) 2))",

    # λx. x + 3
    "(lam (app (app add 0) 3))",

    # λx. x * 2
    "(lam (app (app mul 0) 2))",

    # λx. x * 2
    "(lam (app (app mul 0) 2))",

    # λx. x * 3
    "(lam (app (app mul 0) 3))",

    # λx. λy. x + y
    "(lam (lam (app (app add 1) 0)))",

    # λx. λy. x + y + 1
    "(lam (lam (app (app add (app (app add 1) 0)) 1)))",

    # λx. λy. x + y + 2
    "(lam (lam (app (app add (app (app add 1) 0)) 2)))",

    # λx. x > 0
    "(lam (app (app gt 0) 0))",

    # λx. x > 1
    "(lam (app (app gt 0) 1))",

    # λx. x > 2
    "(lam (app (app gt 0) 2))",

    # λx. x == 0
    "(lam (app (app eq 0) 0))",

    # λx. x == 1
    "(lam (app (app eq 0) 1))",

    # λx. x == 2
    "(lam (app (app eq 0) 2))",

    # λx. λy. (x > 0) && (y == 0)
    "(lam (lam (app (app and (app (app gt 1) 0)) (app (app eq 0) 0))))",
]

# Save to file
output_file = 'simple_test.json'
with open(output_file, 'w') as f:
    json.dump(simple_programs, f, indent=2)

print(f"✓ Created {len(simple_programs)} simple test programs")
print(f"✓ Saved to {output_file}")
print()
print("Example programs:")
for i, prog in enumerate(simple_programs[:5], 1):
    print(f"{i}. {prog}")
