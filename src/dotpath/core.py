# dotpath-x: The Master Addressing Engine.
# A fully extensible, registration-based engine where each path
# capability is encapsulated in a self-contained, expert class.

import re
import json
from abc import ABC, abstractmethod
from typing import Any, List, Iterable, Optional, Tuple, Type, Dict

# --- 1. The PathSegment Contract ---
# All path components inherit from this abstract base class.
# It defines the contract for parsing, evaluation, and serialization.

class PathSegment(ABC):
    _type_name: str

    @classmethod
    @abstractmethod
    def parse(cls, path_str: str) -> Optional[Tuple['PathSegment', int]]:
        """
        Try to parse a segment from the beginning of a string.
        If successful, return an instance of the class and the number of chars consumed.
        Otherwise, return None.
        """
        raise NotImplementedError

    @abstractmethod
    def evaluate(self, doc: Any) -> Iterable[Any]:
        """
        Given a document, yield all matching sub-documents.
        """
        raise NotImplementedError

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Serialize the segment to a dictionary."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PathSegment':
        """Deserialize a dictionary into a segment instance."""
        raise NotImplementedError

# --- 2. The Unified, Extensible Engine ---

class PathEngine:
    """
    A registration-based engine for parsing, evaluating, and serializing path expressions.
    Extend the path language by creating a new PathSegment class and registering it.
    """
    def __init__(self):
        self._segment_classes: List[Type[PathSegment]] = []
        self._type_registry: Dict[str, Type[PathSegment]] = {}

    def register(self, segment_class: Type[PathSegment]):
        """Register a new PathSegment class with the engine."""
        if not hasattr(segment_class, '_type_name'):
            raise TypeError("Registered class must have a '_type_name' attribute.")
        
        self._segment_classes.insert(0, segment_class)
        self._type_registry[segment_class._type_name] = segment_class

    def parse(self, path_str: str) -> List[PathSegment]:
        """Parses a path string into a list of PathSegment instances (the AST)."""
        if not isinstance(path_str, str):
            raise TypeError("Path must be a string.")
        
        ast: List[PathSegment] = []
        remaining_path = path_str.strip()

        if not remaining_path:
            return []

        while remaining_path:
            matched = False
            for parser_class in self._segment_classes:
                result = parser_class.parse(remaining_path)
                if result:
                    node, consumed = result
                    ast.append(node)
                    remaining_path = remaining_path[consumed:].lstrip('.')
                    matched = True
                    break
            if not matched:
                raise ValueError(f"Could not parse path segment: {remaining_path}")
        
        return ast

    def evaluate(self, ast: List[PathSegment], doc: Any) -> Iterable[Any]:
        """Evaluates a Path AST against a document."""
        current_docs = [doc]
        for node in ast:
            next_docs = []
            for current_doc in current_docs:
                next_docs.extend(node.evaluate(current_doc))
            current_docs = next_docs
            if not current_docs:
                return [] # Short-circuit if any segment yields no results
        
        yield from current_docs

    def ast_to_json(self, ast: List[PathSegment]) -> str:
        """Serializes a Path AST to a JSON string."""
        return json.dumps([node.to_dict() for node in ast], indent=2)

    def json_to_ast(self, json_str: str) -> List[PathSegment]:
        """Deserializes a JSON string into a Path AST."""
        data = json.loads(json_str)
        ast = []
        for node_data in data:
            type_name = node_data.get('$type')
            if not type_name:
                raise ValueError("Serialized node is missing '$type' field.")
            
            node_class = self._type_registry.get(type_name)
            if not node_class:
                raise TypeError(f"Unknown path segment type: {type_name}")
            
            ast.append(node_class.from_dict(node_data))
        return ast

# --- 3. Default Engine & Public API ---

# Import the standard segment implementations
from .segments import Key, Index, Slice, Wildcard, Descendant, Filter, RegexKey

def create_default_engine() -> PathEngine:
    """Creates and configures a PathEngine with all standard capabilities."""
    engine = PathEngine()
    # Registration order matters. More specific parsers should come first.
    engine.register(RegexKey)
    engine.register(Filter)
    engine.register(Slice)
    engine.register(Index)
    engine.register(Descendant)
    engine.register(Wildcard)
    engine.register(Key)
    return engine

_DEFAULT_ENGINE = create_default_engine()

def find_all(path: str, doc: Any, engine: PathEngine = _DEFAULT_ENGINE) -> List[Any]:
    """Find all values in a document matching the given path string."""
    ast = engine.parse(path)
    return list(engine.evaluate(ast, doc))

def find_first(path: str, doc: Any, engine: PathEngine = _DEFAULT_ENGINE) -> Optional[Any]:
    """Find the first value in a document matching the given path string."""
    ast = engine.parse(path)
    try:
        return next(engine.evaluate(ast, doc))
    except StopIteration:
        return None
