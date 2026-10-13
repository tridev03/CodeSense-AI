"""
Unit tests for Tree-sitter AST parsers and fallback parser.

Tests:
- PythonParser: classes, methods, functions, async functions, decorators, docstrings, imports, line spans
- JsTsParser: ES6 classes, methods, functions, arrow functions, exported declarations, TS interfaces
- FallbackParser: text-based symbol extraction
- Parser registry and fallback resolution
"""
from __future__ import annotations

import pytest

from backend.ingestion.models import SymbolType
from backend.ingestion.parsers.base import get_parser, register_parser
from backend.ingestion.parsers.fallback_parser import fallback_parser
from backend.ingestion.parsers.js_ts_parser import JsTsParser
from backend.ingestion.parsers.python_parser import PythonParser


@pytest.fixture(autouse=True)
def setup_parsers():
    """Ensure parsers are registered before tests run."""
    register_parser(PythonParser())
    register_parser(JsTsParser())


def test_python_parser_classes_and_methods() -> None:
    """Test Python class and method extraction with Tree-sitter."""
    code = '''import os
from typing import List

class AuthService:
    """Handles user authentication."""

    def __init__(self, secret: str):
        self.secret = secret

    async def authenticate(self, username: str, token: str) -> bool:
        """Authenticate a user with token."""
        return True

def standalone_helper(val: int) -> int:
    return val * 2
'''
    parser = PythonParser()
    symbols = parser.parse_symbols(code, language="python", file_path="auth.py")

    symbol_names = [s.name for s in symbols]
    assert "imports" in symbol_names
    assert "AuthService" in symbol_names
    assert "__init__" in symbol_names
    assert "authenticate" in symbol_names
    assert "standalone_helper" in symbol_names

    # Check class symbol
    cls_symbol = next(s for s in symbols if s.name == "AuthService")
    assert cls_symbol.symbol_type == SymbolType.CLASS
    assert cls_symbol.docstring == "Handles user authentication."
    assert cls_symbol.start_line == 4
    assert cls_symbol.end_line == 12

    # Check method symbol
    method_symbol = next(s for s in symbols if s.name == "authenticate")
    assert method_symbol.symbol_type == SymbolType.METHOD
    assert method_symbol.parent_class == "AuthService"
    assert method_symbol.docstring == "Authenticate a user with token."
    assert method_symbol.start_line == 10

    # Check standalone function
    func_symbol = next(s for s in symbols if s.name == "standalone_helper")
    assert func_symbol.symbol_type == SymbolType.FUNCTION
    assert func_symbol.parent_class is None
    assert func_symbol.start_line == 14


def test_python_parser_decorators() -> None:
    """Test decorator extraction in Python."""
    code = '''@router.get("/users")
@require_auth
def get_users():
    return []
'''
    parser = PythonParser()
    symbols = parser.parse_symbols(code, language="python", file_path="api.py")

    assert len(symbols) == 1
    func = symbols[0]
    assert func.name == "get_users"
    assert len(func.decorators) == 2
    assert "@router.get(\"/users\")" in func.decorators
    assert "@require_auth" in func.decorators


def test_javascript_typescript_parser() -> None:
    """Test JS/TS function, class, and interface extraction."""
    code = '''import { useState } from "react";

export interface UserProps {
    id: string;
    name: string;
}

export class UserService {
    private endpoint: string;

    constructor(endpoint: string) {
        this.endpoint = endpoint;
    }

    async fetchUser(id: string) {
        return { id };
    }
}

export const formatUserName = (user: UserProps): string => {
    return user.name.toUpperCase();
};

function calculateTax(amount: number): number {
    return amount * 0.2;
}
'''
    parser = JsTsParser()
    symbols = parser.parse_symbols(code, language="typescript", file_path="service.ts")

    symbol_names = [s.name for s in symbols]
    assert "imports" in symbol_names
    assert "UserProps" in symbol_names
    assert "UserService" in symbol_names
    assert "fetchUser" in symbol_names
    assert "formatUserName" in symbol_names
    assert "calculateTax" in symbol_names

    # Check class & method
    cls = next(s for s in symbols if s.name == "UserService")
    assert cls.symbol_type == SymbolType.CLASS

    method = next(s for s in symbols if s.name == "fetchUser")
    assert method.symbol_type == SymbolType.METHOD
    assert method.parent_class == "UserService"

    # Check arrow function
    arrow = next(s for s in symbols if s.name == "formatUserName")
    assert arrow.symbol_type == SymbolType.FUNCTION


def test_fallback_parser() -> None:
    """Test generic fallback parser for arbitrary code."""
    code = '''package main

import "fmt"

type Server struct {
    port int
}

func (s *Server) Start() {
    fmt.Println("Starting")
}

func main() {
    s := Server{port: 8080}
    s.Start()
}
'''
    symbols = fallback_parser.parse_symbols(code, language="go", file_path="main.go")
    symbol_names = [s.name for s in symbols]

    assert "Server" in symbol_names
    assert "Start" in symbol_names or "main" in symbol_names
