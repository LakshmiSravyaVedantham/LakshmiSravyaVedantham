#!/usr/bin/env python3
"""
daily_puzzle.py — Pick today's dev puzzle and update the README.

Triggered daily at 00:00 UTC via GitHub Actions.
Rotates through a bank of Python/CS puzzles deterministically by day-of-year.
"""

import re
import sys
from datetime import date

README_PATH = "README.md"

# ---------------------------------------------------------------------------
# Puzzle bank
# Each entry: code (str), question (str), answer (str), explanation (str)
# ---------------------------------------------------------------------------
PUZZLES = [
    {
        "code": """\
def append_to(item, lst=[]):
    lst.append(item)
    return lst

print(append_to(1))
print(append_to(2))""",
        "question": "What does this print?",
        "answer": "`[1]`\n`[1, 2]`",
        "explanation": (
            "Default argument values are evaluated **once** when the function is defined, "
            "not each call. The same list object is reused across calls — "
            "a classic Python gotcha. Fix: use `lst=None` and set `lst = []` inside."
        ),
    },
    {
        "code": """\
a = [1, 2, 3]
b = a
b += [4]
print(a)""",
        "question": "What does this print?",
        "answer": "`[1, 2, 3, 4]`",
        "explanation": (
            "`b = a` makes both names point to the **same list**. "
            "`+=` on a list calls `list.__iadd__`, which mutates in place — "
            "so `a` is also affected. Compare with `b = b + [4]`, which would create a new list."
        ),
    },
    {
        "code": """\
fns = [lambda: i for i in range(3)]
print(fns[0](), fns[1](), fns[2]())""",
        "question": "What does this print?",
        "answer": "`2  2  2`",
        "explanation": (
            "All three lambdas capture the **same variable** `i`, not its value at creation time. "
            "By the time they're called, the loop has finished and `i == 2`. "
            "Fix: `lambda i=i: i` to capture the value at each iteration."
        ),
    },
    {
        "code": """\
print(0.1 + 0.2 == 0.3)
print(round(0.1 + 0.2, 10) == round(0.3, 10))""",
        "question": "What does this print?",
        "answer": "`False`\n`True`",
        "explanation": (
            "Floating-point numbers can't represent `0.1` or `0.2` exactly in binary. "
            "`0.1 + 0.2` evaluates to `0.30000000000000004`. "
            "Use `math.isclose()` or round when comparing floats."
        ),
    },
    {
        "code": """\
a = 256
b = 256
c = 257
d = 257
print(a is b)
print(c is d)""",
        "question": "What does this print?",
        "answer": "`True`\n`False`",
        "explanation": (
            "CPython caches (interns) small integers from **-5 to 256** as singletons. "
            "`256 is 256` → True because it's the same object. "
            "`257 is 257` → typically False (two separate objects). Always use `==` to compare values."
        ),
    },
    {
        "code": """\
class Counter:
    count = 0
    def increment(self):
        self.count += 1

c1 = Counter()
c1.increment()
print(Counter.count)
print(c1.count)""",
        "question": "What does this print?",
        "answer": "`0`\n`1`",
        "explanation": (
            "`self.count += 1` reads the class variable (`0`), adds 1, "
            "then **assigns to the instance** — creating a new instance variable. "
            "The class variable `Counter.count` remains unchanged at `0`."
        ),
    },
    {
        "code": """\
print([] == [])
print([] is [])""",
        "question": "What does this print?",
        "answer": "`True`\n`False`",
        "explanation": (
            "`==` checks **value equality** — two empty lists have the same contents. "
            "`is` checks **identity** — each `[]` creates a new list object in memory. "
            "Rule of thumb: use `is` only for `None`, `True`, `False`."
        ),
    },
    {
        "code": """\
a, *b, c = [1, 2, 3, 4, 5]
print(a, b, c)""",
        "question": "What does this print?",
        "answer": "`1  [2, 3, 4]  5`",
        "explanation": (
            "The `*b` syntax in extended unpacking collects **all middle elements** into a list. "
            "`a` gets the first element, `c` gets the last, and `b` gets everything in between."
        ),
    },
    {
        "code": """\
g = (x * x for x in range(5))
print(sum(g))
print(sum(g))""",
        "question": "What does this print?",
        "answer": "`30`\n`0`",
        "explanation": (
            "A generator expression is a **lazy iterator** — it can only be traversed once. "
            "After `sum(g)` exhausts it, the second call finds no elements and returns `0`. "
            "Use `list(g)` if you need to iterate multiple times."
        ),
    },
    {
        "code": """\
d = {'z': 1, 'a': 2, 'm': 3}
print(list(d.keys()))""",
        "question": "What does this print?",
        "answer": "`['z', 'a', 'm']`",
        "explanation": (
            "Since Python 3.7, dictionaries **preserve insertion order** as part of the language spec. "
            "Keys are returned in the order they were added, not alphabetically."
        ),
    },
    {
        "code": """\
matrix = [[0] * 3] * 3
matrix[0][0] = 9
print(matrix)""",
        "question": "What does this print?",
        "answer": "`[[9, 0, 0], [9, 0, 0], [9, 0, 0]]`",
        "explanation": (
            "`[[0]*3] * 3` creates **three references to the same inner list**. "
            "Mutating `matrix[0][0]` changes the one list that all rows point to. "
            "Fix: `[[0]*3 for _ in range(3)]` to create independent rows."
        ),
    },
    {
        "code": """\
print(True + True + True)
print(True * 10)
print(isinstance(True, int))""",
        "question": "What does this print?",
        "answer": "`3`\n`10`\n`True`",
        "explanation": (
            "`bool` is a subclass of `int`. `True == 1` and `False == 0`. "
            "This means booleans support all integer arithmetic, "
            "which is occasionally useful (e.g. counting `True` values in a list)."
        ),
    },
    {
        "code": """\
s = 'hello world'
print(s[::-1])
print(s[::2])""",
        "question": "What does this print?",
        "answer": "`dlrow olleh`\n`hlowrd`",
        "explanation": (
            "The slice `[start:stop:step]` with `step=-1` reverses the sequence. "
            "`[::2]` selects every other character (indices 0, 2, 4, …). "
            "Slicing is one of Python's most powerful sequence operations."
        ),
    },
    {
        "code": """\
a = {1, 2, 3, 4}
b = {3, 4, 5, 6}
print(len(a ^ b))
print(a & b)""",
        "question": "What does this print?",
        "answer": "`4`\n`{3, 4}`",
        "explanation": (
            "`^` is the **symmetric difference** — elements in either set but not both: `{1,2,5,6}`. "
            "`&` is the **intersection** — elements in both sets. "
            "Sets also support `|` (union) and `-` (difference)."
        ),
    },
    {
        "code": """\
nums = [1, 2, 3]
doubled = map(lambda x: x * 2, nums)
nums.append(4)
print(list(doubled))""",
        "question": "What does this print?",
        "answer": "`[2, 4, 6, 8]`",
        "explanation": (
            "`map()` is **lazy** — it holds a reference to `nums` and only iterates when consumed. "
            "Because we mutated `nums` before calling `list(doubled)`, "
            "the appended `4` is included in the result."
        ),
    },
    {
        "code": """\
x = 10
print(f'{x = }')""",
        "question": "What does this print?",
        "answer": "`x = 10`",
        "explanation": (
            "The `=` specifier in f-strings (Python 3.8+) is a **self-documenting expression**. "
            "It expands to the variable name + ` = ` + its value. "
            "Great for quick debugging: `f'{some_variable = }'`."
        ),
    },
    {
        "code": """\
try:
    result = 1 / 0
except ZeroDivisionError:
    result = 0
    print('caught')
finally:
    print('done')
print(result)""",
        "question": "What does this print?",
        "answer": "`caught`\n`done`\n`0`",
        "explanation": (
            "`finally` **always runs**, whether or not an exception was raised. "
            "It's used for cleanup (closing files, releasing locks). "
            "The `except` block handles the error, so execution continues normally after the `try`."
        ),
    },
    {
        "code": """\
from functools import lru_cache

@lru_cache(maxsize=None)
def fib(n):
    return n if n < 2 else fib(n-1) + fib(n-2)

print(fib(10))
print(fib.cache_info().hits)""",
        "question": "What does this print?",
        "answer": "`55`\n`8`",
        "explanation": (
            "`@lru_cache` memoises function results. `fib(10)` makes 11 unique calls (fib 0–10) "
            "and 8 cache hits (values reused from earlier calls). "
            "Without caching, naive `fib(10)` would make 177 calls."
        ),
    },
    {
        "code": """\
data = [3, 1, 4, 1, 5, 9, 2, 6]
print(sorted(data, key=lambda x: -x)[:3])""",
        "question": "What does this print?",
        "answer": "`[9, 6, 5]`",
        "explanation": (
            "Negating values in the key function sorts in **descending order** without `reverse=True`. "
            "Then `[:3]` slices the top 3. "
            "Alternatively: `sorted(data, reverse=True)[:3]` or `heapq.nlargest(3, data)`."
        ),
    },
    {
        "code": """\
import itertools
pairs = list(itertools.combinations('ABC', 2))
print(len(pairs))
print(pairs[0])""",
        "question": "What does this print?",
        "answer": "`3`\n`('A', 'B')`",
        "explanation": (
            "`combinations('ABC', 2)` yields all unique 2-element subsets: "
            "`('A','B')`, `('A','C')`, `('B','C')`. "
            "C(3,2) = 3. "
            "`itertools` is your best friend for combinatorics — also check `permutations` and `product`."
        ),
    },
    {
        "code": """\
words = ['banana', 'apple', 'cherry', 'avocado']
words.sort(key=lambda w: (w[0], len(w)))
print(words)""",
        "question": "What does this print?",
        "answer": "`['apple', 'avocado', 'banana', 'cherry']`",
        "explanation": (
            "Sorting by a **tuple key** applies criteria left-to-right. "
            "First sorts by first letter (`a < b < c`), then by length for ties. "
            "'apple' (5) comes before 'avocado' (7) because they share 'a' and 5 < 7."
        ),
    },
    {
        "code": """\
x = [1, 2, 3, 4, 5]
print(x[10:20])
print(x[-2:])""",
        "question": "What does this print?",
        "answer": "`[]`\n`[4, 5]`",
        "explanation": (
            "Python slices **never raise IndexError** — out-of-range slices simply return empty or clamped results. "
            "`x[10:20]` finds nothing and returns `[]`. "
            "`x[-2:]` starts from the 2nd-to-last element: `[4, 5]`."
        ),
    },
    {
        "code": """\
def make_adder(n):
    return lambda x: x + n

add5  = make_adder(5)
add10 = make_adder(10)
print(add5(3), add10(3))""",
        "question": "What does this print?",
        "answer": "`8  13`",
        "explanation": (
            "Each call to `make_adder` creates a **closure** — a function that remembers `n` "
            "from its enclosing scope. `add5` closes over `n=5`, `add10` over `n=10`. "
            "Closures are the foundation of decorators, partial functions, and callbacks."
        ),
    },
    {
        "code": """\
print(type(lambda: None).__name__)
print(callable(lambda: None))
print((lambda x, y: x + y)(3, 4))""",
        "question": "What does this print?",
        "answer": "`function`\n`True`\n`7`",
        "explanation": (
            "A `lambda` is just a regular function object — its type is `function`. "
            "`callable()` returns `True` for anything with a `__call__` method. "
            "Lambdas can be called immediately (IIFE pattern) just like regular functions."
        ),
    },
    {
        "code": """\
d = {'a': 1, 'b': 2, 'c': 3}
print({v: k for k, v in d.items()})""",
        "question": "What does this print?",
        "answer": "`{1: 'a', 2: 'b', 3: 'c'}`",
        "explanation": (
            "A **dict comprehension** with swapped `k` and `v` inverts the mapping. "
            "This only works correctly when values are unique and hashable. "
            "If two keys share a value, the last one wins in the inverted dict."
        ),
    },
]


# ---------------------------------------------------------------------------
# README section builder
# ---------------------------------------------------------------------------

def build_puzzle_section(puzzle: dict, day: date, index: int, total: int) -> str:
    code    = puzzle["code"]
    q       = puzzle["question"]
    answer  = puzzle["answer"]
    explain = puzzle["explanation"]
    day_str = day.strftime("%B %-d, %Y")

    return f"""## 🧩 Daily Dev Puzzle

**{q}**

```python
{code}
```

<details>
<summary>💡 Reveal answer</summary>

**Answer:** {answer}

{explain}

</details>

<sub>Puzzle {index + 1} of {total} · Rotates daily · {day_str}</sub>"""


def update_readme(section: str) -> None:
    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    new_content = re.sub(
        r"<!-- PUZZLE_START -->.*?<!-- PUZZLE_END -->",
        f"<!-- PUZZLE_START -->\n{section}\n<!-- PUZZLE_END -->",
        content,
        flags=re.DOTALL,
    )

    if "<!-- PUZZLE_START -->" not in content:
        print("ERROR: PUZZLE_START marker not found in README.", file=sys.stderr)
        sys.exit(1)

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)


def main() -> None:
    today  = date.today()
    index  = today.timetuple().tm_yday % len(PUZZLES)
    puzzle = PUZZLES[index]

    print(f"Today: {today}  →  puzzle #{index + 1} of {len(PUZZLES)}")
    print(f"Question: {puzzle['question']}")

    section = build_puzzle_section(puzzle, today, index, len(PUZZLES))
    update_readme(section)
    print("README updated.")


if __name__ == "__main__":
    main()
