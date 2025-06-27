# dotpath-x: Standard PathSegment Implementations

import re
from dataclasses import dataclass, asdict
from typing import Any, Iterable, Optional, Tuple, Dict

from .core import PathSegment

@dataclass(frozen=True)
class Key(PathSegment):
    _type_name = "key"
    name: str

    def to_dict(self) -> Dict[str, Any]:
        return {"$type": self._type_name, "name": self.name}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Key':
        return cls(name=data['name'])

    @classmethod
    def parse(cls, path_str: str) -> Optional[Tuple[PathSegment, int]]:
        # Dot notation: key
        match = re.match(r"([a-zA-Z_][a-zA-Z0-9_]*)", path_str)
        if match:
            return cls(name=match.group(1)), match.end()
        
        # Quoted bracket notation: ['key-with-special-chars']
        match = re.match(r"\[\s*'(.*?)'\s*\]|\[\s*\"(.*?)\"\s*\]", path_str)
        if match:
            key_name = match.group(1) or match.group(2)
            return cls(name=key_name), match.end()
            
        return None

    def evaluate(self, doc: Any) -> Iterable[Any]:
        if isinstance(doc, dict) and self.name in doc:
            yield doc[self.name]

@dataclass(frozen=True)
class Index(PathSegment):
    _type_name = "index"
    value: int

    def to_dict(self) -> Dict[str, Any]:
        return {"$type": self._type_name, "value": self.value}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Index':
        return cls(value=data['value'])

    @classmethod
    def parse(cls, path_str: str) -> Optional[Tuple[PathSegment, int]]:
        match = re.match(r"\[\s*(-?\d+)\s*\]", path_str)
        if match:
            return cls(value=int(match.group(1))), match.end()
        return None

    def evaluate(self, doc: Any) -> Iterable[Any]:
        if isinstance(doc, list) and -len(doc) <= self.value < len(doc):
            yield doc[self.value]

@dataclass(frozen=True)
class Slice(PathSegment):
    _type_name = "slice"
    start: Optional[int]
    stop: Optional[int]
    step: Optional[int]

    def to_dict(self) -> Dict[str, Any]:
        return {"$type": self._type_name, **asdict(self)}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Slice':
        return cls(start=data.get('start'), stop=data.get('stop'), step=data.get('step'))

    @classmethod
    def parse(cls, path_str: str) -> Optional[Tuple[PathSegment, int]]:
        match = re.match(r"\[\s*(.*?)\s*\]", path_str)
        if not match:
            return None
        
        content = match.group(1)
        if ':' not in content:
            return None

        parts = [p.strip() for p in content.split(':')]
        if len(parts) > 3: return None

        try:
            s = int(parts[0]) if parts[0] else None
            p = int(parts[1]) if len(parts) > 1 and parts[1] else None
            q = int(parts[2]) if len(parts) > 2 and parts[2] else None
            return cls(s, p, q), match.end()
        except ValueError:
            return None

    def evaluate(self, doc: Any) -> Iterable[Any]:
        if isinstance(doc, list):
            yield from doc[slice(self.start, self.stop, self.step)]

@dataclass(frozen=True)
class Wildcard(PathSegment):
    _type_name = "wildcard"

    def to_dict(self) -> Dict[str, Any]:
        return {"$type": self._type_name}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Wildcard':
        return cls()

    @classmethod
    def parse(cls, path_str: str) -> Optional[Tuple[PathSegment, int]]:
        if path_str.startswith('*'): return cls(), 1
        if path_str.startswith('[*]'): return cls(), 3
        return None

    def evaluate(self, doc: Any) -> Iterable[Any]:
        if isinstance(doc, dict):
            yield from doc.values()
        elif isinstance(doc, list):
            yield from doc

@dataclass(frozen=True)
class Descendant(PathSegment):
    _type_name = "descendant"

    def to_dict(self) -> Dict[str, Any]:
        return {"$type": self._type_name}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Descendant':
        return cls()

    @classmethod
    def parse(cls, path_str: str) -> Optional[Tuple[PathSegment, int]]:
        if path_str.startswith('**'): return cls(), 2
        return None

    def evaluate(self, doc: Any) -> Iterable[Any]:
        """Recursively yield the current doc and all its descendants."""
        q = [doc]
        while q:
            curr = q.pop(0)
            yield curr
            if isinstance(curr, dict):
                q.extend(curr.values())
            elif isinstance(curr, list):
                q.extend(curr)

@dataclass(frozen=True)
class Filter(PathSegment):
    _type_name = "filter"
    predicate_str: str

    def __post_init__(self):
        # DANGER: eval is not safe. This is for demonstration only.
        # A real implementation would require a safe, sandboxed expression evaluator.
        # The predicate string uses '@' to refer to the current item.
        try:
            # Use object.__setattr__ because the class is frozen
            object.__setattr__(self, 'predicate', lambda item: eval(self.predicate_str.replace('@', 'item')))
        except Exception as e:
            raise ValueError(f"Invalid predicate string: {self.predicate_str}") from e

    def to_dict(self) -> Dict[str, Any]:
        return {"$type": self._type_name, "predicate": self.predicate_str}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Filter':
        return cls(predicate_str=data['predicate'])

    @classmethod
    def parse(cls, path_str: str) -> Optional[Tuple[PathSegment, int]]:
        match = re.match(r"\[\s*\?\s*\((.*)\)\s*\]", path_str)
        if not match:
            return None
        
        predicate_str = match.group(1)
        return cls(predicate_str=predicate_str), match.end()

    def evaluate(self, doc: Any) -> Iterable[Any]:
        if isinstance(doc, list):
            for item in doc:
                try:
                    if self.predicate(item):
                        yield item
                except:
                    continue

@dataclass(frozen=True)
class RegexKey(PathSegment):
    _type_name = "regex_key"
    pattern: re.Pattern

    @classmethod
    def parse(cls, path_str: str) -> Optional[Tuple[PathSegment, int]]:
        # Syntax: ~r/pattern/flags (e.g., ~r/user_\d+/i)
        match = re.match(r"~r/((?:\\/|[^/])+)/([a-zA-Z]*)", path_str)
        if not match:
            return None

        pattern_str, flags_str = match.groups()
        pattern_str = pattern_str.replace('\\/', '/')  # Unescape forward slashes
        
        re_flags = 0
        if 'i' in flags_str: re_flags |= re.IGNORECASE
        if 'm' in flags_str: re_flags |= re.MULTILINE
        
        try:
            pattern = re.compile(pattern_str, re_flags)
            return cls(pattern=pattern), match.end()
        except re.error:
            return None

    def evaluate(self, doc: Any) -> Iterable[Any]:
        if isinstance(doc, dict):
            for key, value in doc.items():
                if self.pattern.search(str(key)):
                    yield value

    def to_dict(self) -> Dict[str, Any]:
        flags = ""
        if self.pattern.flags & re.IGNORECASE: flags += 'i'
        if self.pattern.flags & re.MULTILINE: flags += 'm'
        return {
            "$type": self._type_name,
            "pattern": self.pattern.pattern,
            "flags": flags
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RegexKey':
        re_flags = 0
        flags_str = data.get("flags", "")
        if 'i' in flags_str: re_flags |= re.IGNORECASE
        if 'm' in flags_str: re_flags |= re.MULTILINE
        
        pattern = re.compile(data['pattern'], re_flags)
        return cls(pattern=pattern)