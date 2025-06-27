# `dotpath`: The Master Addressing Engine

`dotpath` is not just another library for accessing nested data. It is a powerful, extensible, and philosophically pure engine for defining, evaluating, and serializing complex data paths. It is the foundational "addressing layer" for the entire `dot` ecosystem.

## The Philosophy: From Brittle Logic to an Extensible Machine

Most data-accessing tools have a fatal flaw: their logic is hard-coded. They have a fixed set of features, and if you need a new capability—like fuzzy key matching or a custom filter—you are out of luck. You either fork the library or write complex, brittle logic on top of it.

`dotpath` is built on a different philosophy:

> An addressing engine should not be a static tool, but a simple, extensible machine. Its intelligence should not live in a monolithic central function, but within small, self-contained, "expert" components that can be added, removed, or replaced.

This is the core idea of `dotpath`. It provides a `PathEngine` that acts as a simple orchestrator. The real power comes from `PathSegment` classes—small, expert classes that each know how to do one thing perfectly:

1. **Parse** their own unique syntax from a path string.
2. **Evaluate** their logic against a document.
3. **Serialize** themselves to and from a universal JSON format.

This is the **"Lambda of Paths"**: the ability to extend the path language itself by simply defining a new class and registering it with the engine.

## Basic Usage

At its simplest, `dotpath` provides a default engine that understands a rich, JSONPath-inspired syntax.

```python
from dotpath import find_all, find_first
from my_data import document

# Get all authors from the bookstore
authors = find_all('store.book[*].author', document)
# => ['Nigel Rees', 'Evelyn Waugh', 'Herman Melville', 'J. R. R. Tolkien']

# Get the price of the first book
price = find_first('store.book[0].price', document)
# => 8.95
```

## The Proof: The `dot` Ecosystem is `dotpath`

The true power of this architecture is that the other addressing tools in the `dot` ecosystem (`dotget`, `dotstar`, `dotpath`) are conceptually constrained instances of the `dotpath` engine,
although by the principle of least power, and for simplicity of implementation, they hard-code their relatively straightforward logic. This also facilitates the "Steal This Code" ethos, as some of these packages have a core implementation that is around 10 lines of code.

### Implementing `dotget` with `dotpath`

`dotget` only understands basic key and index lookups. We can create a `dotget`-compliant engine by only registering the `Key` and `Index` segments.

```python
from dotpath import PathEngine
from dotpath.segments import Key, Index

# 1. Create a new, empty engine
dotget_engine = PathEngine()

# 2. Register ONLY the capabilities of dotget
dotget_engine.register(Key)
dotget_engine.register(Index)

# 3. This engine now behaves exactly like dotget.
# The engine's main loop handles the '.' separator between segments.
path = "user.name"
ast = dotget_engine.parse(path)
# The parse happens in two steps:
# a) Key.parse("user.name") matches "user".
# b) The engine strips the '.', leaving "name" for the next loop.
# c) Key.parse("name") matches "name".
# => [Key(name='user'), Key(name='name')]

# This fails because no registered segment knows how to parse "*".
# dotget_engine.parse("user.*") # => ValueError
```

### Implementing `dotstar` with `dotpath`

To upgrade our engine to `dotstar`, we simply register the `Wildcard` segment.

```python
from dotpath.segments import Wildcard

# 1. Take our dotget_engine
dotstar_engine = dotget_engine

# 2. Register the new capability
dotstar_engine.register(Wildcard)

# 3. The engine now understands wildcards
ast = dotstar_engine.parse("user.*")
# => [Key(name='user'), Wildcard()]
```

### The Default `dotpath` Engine

The full, default `dotpath` engine is simply one that has all the standard segments registered. This is what `create_default_engine()` does for you.

## The Lambda of Paths: Advanced Extensibility

Here is the ultimate demonstration. Let's invent a new path syntax: fuzzy key matching, like `~f/term/0.8`, which requires the `rapidfuzz` library.

**Step 1: Define a new `FuzzyKey` PathSegment class.**

```python
# in a new file, e.g., custom_segments.py
from dataclasses import dataclass
from rapidfuzz.process import extract
from dotpath import PathSegment

@dataclass(frozen=True)
class FuzzyKey(PathSegment):
    _type_name = "fuzzy_key"
    term: str
    cutoff: float

    @classmethod
    def parse(cls, path_str):
        match = re.match(r"~f/(.*?)/(\d\.\d+)", path_str)
        if match:
            term, cutoff = match.groups()
            return cls(term, float(cutoff)), match.end()
        return None

    def evaluate(self, doc):
        if isinstance(doc, dict):
            matches = extract(self.term, doc.keys(), score_cutoff=self.cutoff * 100)
            for key, score, index in matches:
                yield doc[key]
    
    def to_dict(self):
        return {"$type": self._type_name, "term": self.term, "cutoff": self.cutoff}

    @classmethod
    def from_dict(cls, data):
        return cls(term=data['term'], cutoff=data['cutoff'])
```

**Step 2: Create a custom engine and register your new segment.**

```python
from dotpath import create_default_engine
from custom_segments import FuzzyKey

# 1. Start with the standard engine
my_engine = create_default_engine()

# 2. Register our new, custom capability
my_engine.register(FuzzyKey)

# 3. Use it!
data = {"user_name": "John", "user_id": 123}
path = "~f/username/0.8"

# The engine now understands our custom syntax
find_all(path, data, engine=my_engine)
# => ["John"]
```

You have extended the path language without ever touching the core engine code.

## Serialization: Paths as Data

Because every `PathSegment` knows how to serialize itself, any path can be converted to a language-agnostic JSON AST. This is incredibly powerful for caching, network transfer, and building interoperable systems.

```python
from dotpath import _DEFAULT_ENGINE as engine

path_string = "store.book[?(@.price < 10)].title"

# 1. Parse the string to a Python AST
ast = engine.parse(path_string)

# 2. Serialize the AST to a JSON string
json_ast = engine.ast_to_json(ast)
print(json_ast)
# [
#   { "$type": "key", "name": "store" },
#   { "$type": "key", "name": "book" },
#   { "$type": "filter", "predicate": "@.price < 10" },
#   { "$type": "key", "name": "title" }
# ]

# 3. Deserialize it back on a server, skipping the parse step
rehydrated_ast = engine.json_to_ast(json_ast)
assert ast == rehydrated_ast
```

## Built-in Segments

The default engine comes with a rich set of built-in path segments:

| Segment        |     Syntax Examples         | Description                              |
| :--------------| :-------------------------- | :--------------------------------------- |
| **Key**        | `key`, `['key-with-chars']` | Access a dictionary value by key.        |
| **Index**      | `[2]`, `[-1]`               | Access a list element by index.          |
| **Slice**      | `[1:5]`, `[:4]`, `[::2]`    | Select a range of list elements.         |
| **Wildcard**   | `*`, `[*]`                  | Select all items in a list or dict.      |
| **Descendant** | `**`                        | Recursively select all descendant nodes. |
| **Filter**     | `[?(@.price < 10)]`         | Filter a list based on a predicate.      |
| **RegexKey**   | `~r/user_\\d+/i`            | Selects dict keys matching a regex.      |

## Command-Line Usage

You can also use `dotpath` from the command line to quickly query JSON or YAML files.

```bash
# Get all book titles from a local file
$ cat books.json | dotpath 'store.book[*].title'
[
  "The Lord of the Rings",
  "Moby Dick",
  "The Hitchhiker's Guide to the Galaxy"
]

# Find the price of the first book from a remote URL
$ curl -s https://api.example.com/books.json | dotpath 'store.book[0].price'
8.95
```

## Installation

```bash
pip install dotpath
# For fuzzy matching capability
pip install "dotpath[fuzzy]"
```
*(Note: Assumes `pyproject.toml` is configured with an optional `fuzzy` extra that includes `rapidfuzz`)*

## License

This project is licensed under the MIT License.

> "The limits of my language mean the limits of my world." - Ludwig Wittgenstein
