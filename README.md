# Code Compression Experiments

This repository contains experiments in program compression and abstraction discovery for Python programs, specifically focused on the Battleship problem domain.

## Overview

The goal of these experiments is to discover useful abstractions and compress code by identifying common patterns across multiple program implementations. We explore two main approaches:

## Approaches

### 1. AST-Based Approach
Located in `ast_based_approach/`

Uses Python's Abstract Syntax Tree (AST) to identify recurring code patterns across programs and extract them into helper functions.

**Key files:**
- `ast_based_refactor.py` - Main refactoring implementation
- `ast_refactorer.py` - AST pattern extraction utilities
- `ast_helpers.py` - Helper utilities for AST manipulation
- `results/` - Analysis results and reports

**Method:**
- Parses Python programs into ASTs
- Identifies common subtree patterns across multiple programs
- Extracts recurring patterns into reusable helper functions
- Refactors original programs to use the helpers

### 2. Stitch-Based Approach
Located in `stitch_based_approach/`

Uses the Stitch compression algorithm (a Rust implementation) to discover abstractions in lambda calculus representations of Python programs.

**Key files:**
- `battleship_to_stitch.py` - Converts Battleship programs to Stitch lambda calculus format
- `run_stitch_python.py` - Runs the Stitch compression algorithm
- `translate_to_python.py` - Translates compressed programs back to Python
- `canonicalize_free_vars.py` - Normalizes free variable names
- `inline_and_convert.py` - Inlines discovered abstractions
- `stitch/` - Rust implementation of the Stitch algorithm

**Method:**
- Converts Python programs to lambda calculus expressions using De Bruijn indices
- Maps Python primitives to simple lambda calculus primitives
- Runs Stitch to discover recurring patterns and extract abstractions
- Translates compressed programs back to Python with discovered helpers

## Data

- `battleship_programs.jsonl` - Collection of Battleship program implementations used as input data

## Usage

Each approach directory contains scripts that can be run independently. See the individual Python files for documentation on their specific usage.

The general workflow is:
1. Start with input programs (from `battleship_programs.jsonl`)
2. Run compression/pattern discovery
3. Extract discovered abstractions as helper functions
4. Refactor original programs to use the helpers
5. Analyze compression results

## Requirements

- Python 3.x
- Rust/Cargo (for Stitch-based approach)
- NumPy (for program execution)
