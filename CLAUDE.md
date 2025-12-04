# Claude Code Repository Rules

Follow these rules when reading, modifying, generating, or refactoring code in
this repository.

## 1. Python Style Standard
Use the following authoritative style references:

- **PEP 8**: official formatting and naming conventions.
- **PEP 20 (Zen of Python)**: simplicity, clarity, explicitness.
- **PEP 484**: full type annotations for all functions.
- **Black formatting**: line length 88, stable formatting.
- **Google Python Style Guide**: docstring format and function structuring.

All Python must:
- use type hints everywhere
- use pathlib instead of os.path
- use dataclasses for structured data
- avoid mutable default arguments
- prefer early returns over deep nesting
- avoid exec(), eval(), and mutation of locals()/globals()

## 2. Allowed Dependencies
Only the following are allowed:
- Python 3 standard library
- The `dcs` / `pydcs` mission-building library
No additional dependencies unless explicitly requested.

## 3. Code Structure Expectations
- Write small, focused functions; avoid functions > 50 lines.
- Use pure functions when practical.
- Keep modules logically separated and readable.
- Use `logging` instead of print().
- Handle errors explicitly with meaningful exceptions.

## 4. Repository Safety Rules
Claude Code MUST NOT:
- break existing mod identity (e.g., MiG-17 folder names, unitType names)
- introduce incompatible mission-generation formats
- modify binary files
- generate .miz files directly (generate code that produces them instead)

Claude Code SHOULD:
- preserve API compatibility unless instructed otherwise
- update interconnected files consistently
- document changes with comments when helpful

## 5. Refactoring Rules
When refactoring:
- improve clarity and maintainability
- keep behavior identical unless instructed to modify it
- remove dead code, unused variables, unnecessary complexity
- prefer explicit readability over compact cleverness

## 6. Mission Generation Scripts
When generating .miz-building code:
- use Python + dcs/pydcs library, no external tools
- structure mission generation in clean functions
- embed logger Lua scripts as strings
- parameterize aircraft type, altitudes, speeds

## 7. Output Format
All Claude Code output should be:
- fully self-contained
- directly runnable
- formatted with Black-style conventions
- accompanied by a short explanation of design choices when helpful
