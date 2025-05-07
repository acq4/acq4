#!/usr/bin/env python
"""
Semantic search system for ACQ4 metadata using Claude API.

This script recursively scans directories for .index files, parses their metadata,
and uses the Claude API to perform semantic searches against the data.
"""

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import anthropic
import numpy as np
import pyqtgraph.configfile
from tqdm import tqdm


class MetadataIndexer:
    """Indexes and searches .index files using Claude API."""
    
    def __init__(
        self,
        paths: List[str],
        max_entry_size: int = 500,
        cache_dir: str = None,
        verbose: bool = False,
        api_key: str = None,
    ):
        self.paths = [Path(p) for p in paths]
        self.max_entry_size = max_entry_size
        self.cache_dir = Path(cache_dir or os.path.expanduser("~/.index_search_cache"))
        self.verbose = verbose
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.client = None
        
        # Initialize cache directory
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_cache_path = self.cache_dir / "metadata_cache.json"
        self.query_cache_path = self.cache_dir / "query_cache.json"
        
        # Initialize caches
        self.metadata_cache = self._load_cache(self.metadata_cache_path)
        self.query_cache = self._load_cache(self.query_cache_path)
        
        # File paths indexed keyed by directory
        self.indexed_files = defaultdict(list)
        
    def _load_cache(self, cache_path: Path) -> Dict:
        """Load cache from disk if it exists."""
        if cache_path.exists():
            try:
                with open(cache_path, 'r') as f:
                    if self.verbose:
                        print(f"Loading cache from {cache_path}")
                    return json.load(f)
            except Exception as e:
                if self.verbose:
                    print(f"Error loading cache: {e}")
        return {}
    
    def _save_cache(self, cache: Dict, cache_path: Path) -> None:
        """Save cache to disk."""
        with open(cache_path, 'w') as f:
            if self.verbose:
                print(f"Saving cache to {cache_path}")
            json.dump(cache, f)
    
    def _init_client(self) -> None:
        """Initialize the Claude API client."""
        if self.client is None:
            if not self.api_key:
                raise ValueError(
                    "API key is required. Please provide it via --api-key or set the ANTHROPIC_API_KEY environment variable."
                )
            self.client = anthropic.Anthropic(api_key=self.api_key)
    
    def scan_directories(self, force_update: bool = False) -> None:
        """Scan directories for .index files and parse their metadata."""
        for base_path in self.paths:
            if not base_path.exists():
                print(f"Warning: Path {base_path} does not exist. Skipping.")
                continue
                
            print(f"Scanning {base_path} for .index files...")
            found_files = list(base_path.glob("**/*.index"))
            
            if self.verbose:
                print(f"Found {len(found_files)} .index files")
            
            for file_path in tqdm(found_files, desc="Indexing files", disable=not self.verbose):
                rel_path = file_path.relative_to(base_path)
                dir_path = str(file_path.parent)
                self.indexed_files[dir_path].append(str(file_path))
                
                # Skip already cached files unless forced to update
                if not force_update and str(file_path) in self.metadata_cache:
                    continue
                
                try:
                    metadata = pyqtgraph.configfile.readConfigFile(str(file_path))
                    # Process metadata to make it more searchable
                    processed_metadata = self._process_metadata(metadata, file_path)
                    self.metadata_cache[str(file_path)] = processed_metadata
                except Exception as e:
                    print(f"Error processing {file_path}: {e}")
        
        # Save the updated cache
        self._save_cache(self.metadata_cache, self.metadata_cache_path)
        print(f"Indexed {len(self.metadata_cache)} files")
    
    def _process_metadata(self, metadata: Dict, file_path: Path) -> Dict:
        """Process metadata into a searchable format."""
        # Create a processed version with additional context
        processed = {
            "file_path": str(file_path),
            "directory": str(file_path.parent),
            "filename": file_path.name,
            "metadata": {},
            "extracted_fields": {},
        }
        
        # Extract and process relevant metadata fields, filtering by size
        self._extract_metadata_fields(metadata, processed["metadata"], set())
        
        # Extract special fields of interest that might be deeply nested
        self._extract_special_fields(metadata, processed["extracted_fields"])
        
        return processed
    
    def _extract_metadata_fields(
        self, 
        data: Any, 
        result: Dict, 
        path: Set[str], 
        current_path: str = "",
    ) -> None:
        """Recursively extract metadata fields, filtering by size."""
        if isinstance(data, dict):
            for key, value in data.items():
                new_path = f"{current_path}.{key}" if current_path else key
                if new_path in path:  # Avoid circular references
                    continue
                    
                new_path_set = path.copy()
                new_path_set.add(new_path)
                
                if isinstance(value, (dict, list)):
                    result[key] = {} if isinstance(value, dict) else []
                    self._extract_metadata_fields(value, result[key], new_path_set, new_path)
                else:
                    # Check size before including
                    value_str = str(value)
                    if len(value_str) <= self.max_entry_size:
                        result[key] = value
                    else:
                        result[key] = f"[TRUNCATED: {len(value_str)} bytes]"
        
        elif isinstance(data, list):
            for i, item in enumerate(data):
                new_path = f"{current_path}[{i}]"
                if new_path in path:  # Avoid circular references
                    continue
                    
                new_path_set = path.copy()
                new_path_set.add(new_path)
                
                if isinstance(item, (dict, list)):
                    result.append({} if isinstance(item, dict) else [])
                    self._extract_metadata_fields(item, result[-1], new_path_set, new_path)
                else:
                    # Check size before including
                    item_str = str(item)
                    if len(item_str) <= self.max_entry_size:
                        result.append(item)
                    else:
                        result.append(f"[TRUNCATED: {len(item_str)} bytes]")
        else:
            # For primitive types, just convert to appropriate JSON-compatible form
            if isinstance(data, np.ndarray):
                data = data.tolist()
            result = data
    
    def _extract_special_fields(self, data: Any, result: Dict, path: str = "") -> None:
        """Extract specific fields of interest from nested structures."""
        # Fields we're interested in finding anywhere in the structure
        special_fields = {
            "notes", "illumination", "exposure", "wavelength", "camera", "date", "device", 
            "objective", "filter", "protocol", "recording", "cell", "patch", "stimulus"
        }
        
        if isinstance(data, dict):
            for key, value in data.items():
                new_path = f"{path}.{key}" if path else key
                
                # Check if this is a special field
                if key.lower() in special_fields:
                    # Only store if it's not too large
                    value_str = str(value)
                    if len(value_str) <= self.max_entry_size:
                        result[new_path] = value
                    else:
                        result[new_path] = f"[TRUNCATED: {len(value_str)} bytes]"
                
                # Recurse into nested structures
                if isinstance(value, (dict, list)):
                    self._extract_special_fields(value, result, new_path)
        
        elif isinstance(data, list):
            for i, item in enumerate(data):
                new_path = f"{path}[{i}]"
                if isinstance(item, (dict, list)):
                    self._extract_special_fields(item, result, new_path)
    
    def search(self, query: str, max_results: int = 10) -> List[Dict]:
        """Search the indexed metadata using Claude."""
        if not self.metadata_cache:
            print("No indexed files. Run scan_directories() first.")
            return []
        
        # Check query cache first
        cache_key = f"{query}:{max_results}"
        if cache_key in self.query_cache:
            if self.verbose:
                print("Using cached query results")
            return self.query_cache[cache_key]
        
        self._init_client()
        
        # Prepare the prompt for Claude
        prompt = self._build_search_prompt(query, max_results)
        
        try:
            # Call Claude API
            response = self.client.messages.create(
                model="claude-3-7-sonnet-20250219",  # Using the current Claude model as of 2025
                max_tokens=4096,
                temperature=0,
                system="""You are a specialized search system for scientific metadata from 
                neurophysiology experiments. Your job is to find relevant files based on 
                natural language queries by analyzing metadata information. 
                
                Return your results as a JSON array containing objects with:
                1. file_path: The path to the matching file
                2. relevance: A number from 0-10 indicating match quality
                3. reason: A short explanation of why this file matches
                
                Answer ONLY with valid JSON. Do not include any other text or explanations.""",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Extract the JSON response
            try:
                results = json.loads(response.content[0].text)
                
                # Cache the results
                self.query_cache[cache_key] = results
                self._save_cache(self.query_cache, self.query_cache_path)
                
                return results
            except json.JSONDecodeError:
                print("Error: Couldn't parse JSON response from Claude")
                print(response.content[0].text)
                return []
                
        except Exception as e:
            print(f"Error querying Claude API: {e}")
            return []
    
    def _build_search_prompt(self, query: str, max_results: int) -> str:
        """Build a prompt for Claude to search the metadata."""
        # Select a subset of metadata to include in the prompt
        # This is necessary to avoid exceeding context limits
        relevant_metadata = self._select_relevant_metadata(query, max_count=50)
        
        metadata_json = json.dumps(relevant_metadata, indent=2)
        
        prompt = f"""
        I need you to search through the following metadata from neurophysiology experiments 
        and find the {max_results} most relevant files for this query:
        
        QUERY: {query}
        
        Here is the metadata from various files:
        ```json
        {metadata_json}
        ```
        
        Analyze the metadata and return the {max_results} most relevant results as a JSON array of objects.
        Each object should have:
        - file_path: The full path to the file
        - relevance: A score from 0-10 indicating how relevant this file is to the query
        - reason: A brief explanation of why this file matches the query
        
        Return ONLY the JSON array. Do not include any other text.
        """
        
        return prompt
    
    def _select_relevant_metadata(self, query: str, max_count: int = 50) -> List[Dict]:
        """
        Select a subset of metadata that might be relevant to the query.
        This uses simple keyword matching to reduce the context size for Claude.
        """
        # Extract keywords from the query
        keywords = set(query.lower().split())
        
        # Filter out common words that aren't useful for matching
        stopwords = {"a", "an", "the", "with", "for", "and", "or", "in", "on", "at", "to", "of", "find", "me"}
        keywords = keywords - stopwords
        
        # Score each metadata entry based on keyword matches
        scored_entries = []
        
        for file_path, metadata in self.metadata_cache.items():
            score = 0
            metadata_str = json.dumps(metadata).lower()
            
            for keyword in keywords:
                if keyword in metadata_str:
                    score += 1
            
            # Also consider file path for relevance
            for keyword in keywords:
                if keyword in file_path.lower():
                    score += 0.5
            
            scored_entries.append((score, metadata))
        
        # Sort by score and take the top entries
        scored_entries.sort(reverse=True, key=lambda x: x[0])
        return [entry[1] for entry in scored_entries[:max_count]]
    
    def export_results(self, results: List[Dict], output_file: str) -> None:
        """Export search results to a JSON file."""
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"Results exported to {output_file}")


def main():
    """Main function to run when executed as a script."""
    parser = argparse.ArgumentParser(description='Semantic search for ACQ4 metadata.')
    parser.add_argument('--paths', required=True, help='Comma-separated paths to scan for .index files')
    parser.add_argument('--max-entry-size', type=int, default=500, help='Maximum size of metadata entries to include')
    parser.add_argument('--cache-dir', default=None, help='Directory to store cache files')
    parser.add_argument('--api-key', default=None, help='Anthropic API key (can also use ANTHROPIC_API_KEY env var)')
    parser.add_argument('--update', action='store_true', help='Force update of the cache/index')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('--max-results', type=int, default=10, help='Maximum number of results to return')
    parser.add_argument('--export', help='Export results to a JSON file')
    parser.add_argument('query', nargs='?', help='Search query')
    
    args = parser.parse_args()
    
    # Split paths
    paths = [path.strip() for path in args.paths.split(',')]
    
    indexer = MetadataIndexer(
        paths=paths,
        max_entry_size=args.max_entry_size,
        cache_dir=args.cache_dir,
        verbose=args.verbose,
        api_key=args.api_key,
    )
    
    # Scan directories
    indexer.scan_directories(force_update=args.update)
    
    # If a query was provided, perform the search
    if args.query:
        print(f"Searching for: {args.query}")
        results = indexer.search(args.query, max_results=args.max_results)
        
        # Export results if requested
        if args.export:
            indexer.export_results(results, args.export)
            
        # Display results
        if results:
            print("\nSearch Results:")
            print("=" * 80)
            for i, result in enumerate(results, 1):
                print(f"{i}. {result['file_path']} (Relevance: {result['relevance']}/10)")
                print(f"   Reason: {result['reason']}")
                print("-" * 80)
        else:
            print("No matching results found.")


if __name__ == "__main__":
    main()