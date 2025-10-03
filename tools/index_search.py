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

    # Constants for Claude API and chunking
    DEFAULT_MODEL_NAME = "claude-3-7-sonnet-20250219"
    MAX_INPUT_TOKENS_STAGE1 = 170000  # Max input tokens for Stage 1 (candidate selection)
    MAX_INPUT_TOKENS_STAGE2 = 170000  # Max input tokens for Stage 2 (deep analysis)
    MAX_OUTPUT_TOKENS = 4096
    AVG_CHARS_PER_TOKEN = 3  # Conservative estimate for characters per token
    DEFAULT_MAX_CANDIDATES_FROM_STAGE1 = 100 # Max candidates from Stage 1
    DEFAULT_MAX_CANDIDATES_PER_DEEP_ANALYSIS_CHUNK = 20 # Max candidates per Stage 2 chunk
    
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

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for a given text."""
        if not text:
            return 0
        return (len(text) + self.AVG_CHARS_PER_TOKEN - 1) // self.AVG_CHARS_PER_TOKEN

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

    def _build_candidate_selection_prompt(self, query: str, file_infos: List[Dict], max_candidates: int) -> str:
        """Builds the prompt for Stage 1 candidate selection."""
        file_infos_json = json.dumps(file_infos, indent=2)
        
        prompt = f"""
        Based on the user's query, please identify up to {max_candidates} file paths from the following list that are most likely to contain relevant information.
        The file information provided includes 'file_path', 'filename', and 'parent_dir'.

        QUERY: {query}

        FILE INFORMATION:
        ```json
        {file_infos_json}
        ```

        Return your answer as a JSON list of file_path strings. For example:
        ["/path/to/relevant_file1.index", "/path/to/relevant_file2.index"]
        
        Return ONLY the JSON list. Do not include any other text or explanations.
        """
        return prompt

    def _select_candidate_files(self, query: str, max_candidates_from_stage1: int) -> List[str]:
        """Stage 1: Select candidate files using Claude based on minimal context."""
        if not self.metadata_cache:
            return []

        self._init_client()

        file_infos_for_stage1 = []
        for path_str, metadata_item in self.metadata_cache.items():
            file_infos_for_stage1.append({
                "file_path": path_str,
                "filename": metadata_item.get("filename", Path(path_str).name),
                "parent_dir": metadata_item.get("directory", str(Path(path_str).parent))
            })
        
        if not file_infos_for_stage1:
            return []

        # Estimate token usage for the file_infos list
        # Truncate if necessary to fit within Stage 1 token limits
        # This is a simplified truncation; more sophisticated handling might be needed for huge datasets
        temp_prompt_for_estimation = self._build_candidate_selection_prompt(query, [], max_candidates_from_stage1)
        prompt_structure_tokens = self._estimate_tokens(temp_prompt_for_estimation)
        available_tokens_for_file_infos = self.MAX_INPUT_TOKENS_STAGE1 - prompt_structure_tokens - 500 # 500 for safety margin

        truncated_file_infos = []
        current_tokens = 0
        for info in file_infos_for_stage1:
            info_str = json.dumps(info)
            info_tokens = self._estimate_tokens(info_str)
            if current_tokens + info_tokens > available_tokens_for_file_infos:
                if self.verbose:
                    print(f"Warning: Truncating file list for Stage 1 due to token limits. Processed {len(truncated_file_infos)} files.")
                break
            truncated_file_infos.append(info)
            current_tokens += info_tokens
        
        if not truncated_file_infos:
            if self.verbose:
                print("Warning: No file information could be included in Stage 1 prompt within token limits.")
            return []

        prompt = self._build_candidate_selection_prompt(query, truncated_file_infos, max_candidates_from_stage1)

        try:
            response = self.client.messages.create(
                model=self.DEFAULT_MODEL_NAME,
                max_tokens=self.MAX_OUTPUT_TOKENS, # Expecting a list of strings, usually not too large
                temperature=0,
                system="""You are an AI assistant specialized in identifying potentially relevant files from a list based on a user's query.
You will be given a query and a list of file information objects, each containing 'file_path', 'filename', and 'parent_dir'.
Your task is to return a JSON list of 'file_path' strings for files that seem most promising for a more detailed analysis.
Do not analyze the content deeply; this is a pre-selection step.
Return ONLY the JSON list of file paths. For example: ["/path/to/file1.index", "/path/to/file2.index"]""",
                messages=[{"role": "user", "content": prompt}]
            )
            candidate_paths = json.loads(response.content[0].text)
            if not isinstance(candidate_paths, list) or not all(isinstance(p, str) for p in candidate_paths):
                if self.verbose:
                    print(f"Warning: Stage 1 returned an unexpected format: {candidate_paths}")
                return []
            return candidate_paths
        except Exception as e:
            print(f"Error querying Claude API in Stage 1 (candidate selection): {e}")
            if hasattr(response, 'content'):
                 print(f"Claude response: {response.content[0].text}")
            return []

    def _get_deep_analysis_system_prompt(self) -> str:
        return """You are a specialized search system for scientific metadata from 
                neurophysiology experiments. Your job is to find relevant files based on 
                natural language queries by analyzing metadata information.
                
                For single file queries, return results as:
                {
                  "file_path": "/path/to/file.index",
                  "relevance": 8,
                  "reason": "This file contains data about..."
                }
                
                For relationship queries (when the user wants to find related files), you can return:
                {
                  "file_paths": ["/path/to/file1.index", "/path/to/file2.index"],
                  "relevance": 9,
                  "reason": "These files are related because...",
                  "relationship_type": "z-stack-pair"
                }
                
                Return your results as a JSON array of these objects. Answer ONLY with valid JSON.
                Do not include any other text or explanations."""

    def _build_deep_analysis_prompt(self, query: str, metadata_list: List[Dict], max_results: int) -> str:
        """Builds the prompt for Stage 2 deep analysis."""
        metadata_json = json.dumps(metadata_list, indent=2)
        
        # Note: max_results is a guideline. The prompt asks to analyze the provided metadata.
        # Final trimming to max_results happens after aggregation if chunking.
        prompt = f"""
        I need you to search through the following metadata from neurophysiology experiments 
        and identify the most relevant results for this query.
        
        QUERY: {query}
        
        Here is the metadata from a selection of candidate files:
        ```json
        {metadata_json}
        ```
        
        Analyze this metadata and return all relevant results as a JSON array of objects.
        Strive to find up to {max_results} best matches if possible from this set of metadata.
        
        For SINGLE FILE results, each object should have:
        - file_path: The full path to the file from the metadata
        - relevance: A score from 0-10 indicating relevance
        - reason: A brief explanation of why this file matches
        
        For RELATIONSHIP QUERIES (when user asks for related files, pairs, etc.), return:
        - file_paths: An array of related file paths from the metadata
        - relationship_type: A label describing the relationship (e.g., "z-stack-pair")
        - relevance: A score from 0-10 indicating relevance
        - reason: A brief explanation of why these files are related and match the query
        
        Return ONLY the JSON array. Do not include any other text.
        """
        return prompt

    def _chunked_search(self, query: str, candidate_metadata: List[Dict], max_results: int) -> List[Dict]:
        """Performs Stage 2 deep analysis in chunks if metadata is too large."""
        all_results = []
        current_chunk = []
        current_chunk_tokens = 0

        # Estimate tokens for the prompt structure (query, instructions)
        # This needs to be based on the actual prompt template for Stage 2
        prompt_template_for_estimation = self._build_deep_analysis_prompt(query, [], max_results)
        prompt_structure_tokens = self._estimate_tokens(prompt_template_for_estimation)
        
        # Available tokens for metadata in each chunk
        available_tokens_for_metadata_chunk = self.MAX_INPUT_TOKENS_STAGE2 - prompt_structure_tokens - 500 # Safety margin

        for metadata_item in tqdm(candidate_metadata, desc="Processing chunks for deep analysis", disable=not self.verbose):
            item_json = json.dumps(metadata_item)
            item_tokens = self._estimate_tokens(item_json)

            if current_chunk_tokens + item_tokens > available_tokens_for_metadata_chunk and current_chunk:
                # Process the current_chunk
                if self.verbose:
                    print(f"Processing a chunk of {len(current_chunk)} items, estimated tokens: {current_chunk_tokens + prompt_structure_tokens}")
                prompt = self._build_deep_analysis_prompt(query, current_chunk, max_results) # Ask for up to max_results from this chunk
                response = None
                try:
                    response = self.client.messages.create(
                        model=self.DEFAULT_MODEL_NAME,
                        max_tokens=self.MAX_OUTPUT_TOKENS,
                        temperature=0,
                        system=self._get_deep_analysis_system_prompt(),
                        messages=[{"role": "user", "content": prompt}]
                    )
                    chunk_results = json.loads(response.content[0].text)
                    all_results.extend(chunk_results)
                except Exception as e:
                    print(f"Error querying Claude API in chunked search: {e}")
                    if hasattr(response, 'content'):
                        print(f"Claude response: {response.content[0].text}")
                
                # Reset for next chunk
                current_chunk = [metadata_item]
                current_chunk_tokens = item_tokens
            else:
                current_chunk.append(metadata_item)
                current_chunk_tokens += item_tokens
        
        # Process the last remaining chunk
        if current_chunk:
            if self.verbose:
                print(f"Processing the final chunk of {len(current_chunk)} items, estimated tokens: {current_chunk_tokens + prompt_structure_tokens}")
            prompt = self._build_deep_analysis_prompt(query, current_chunk, max_results)
            try:
                response = self.client.messages.create(
                    model=self.DEFAULT_MODEL_NAME,
                    max_tokens=self.MAX_OUTPUT_TOKENS,
                    temperature=0,
                    system=self._get_deep_analysis_system_prompt(),
                    messages=[{"role": "user", "content": prompt}]
                )
                chunk_results = json.loads(response.content[0].text)
                all_results.extend(chunk_results)
            except Exception as e:
                print(f"Error querying Claude API in final chunk: {e}")
                if hasattr(response, 'content'):
                    print(f"Claude response: {response.content[0].text}")

        # Sort all collected results by relevance and take top N
        all_results.sort(key=lambda x: x.get("relevance", 0), reverse=True)
        return all_results[:max_results]

    def search(self, query: str, max_results: int = 10) -> List[Dict]:
        """Search the indexed metadata using a two-stage process."""
        if not self.metadata_cache:
            print("No indexed files. Run scan_directories() first.")
            return []
        
        cache_key = f"{query}:{max_results}"
        if cache_key in self.query_cache:
            if self.verbose:
                print("Using cached query results")
            return self.query_cache[cache_key]
        
        self._init_client()

        # Stage 1: Select candidate files
        candidate_file_paths = self._select_candidate_files(query, max_candidates_from_stage1=self.DEFAULT_MAX_CANDIDATES_FROM_STAGE1)

        if not candidate_file_paths:
            if self.verbose:
                print("Stage 1 did not return any candidate files.")
            return []

        if self.verbose:
            print(f"Stage 1 identified {len(candidate_file_paths)} candidate(s). Examples: {candidate_file_paths[:5]}")

        # Prepare full metadata for candidate files
        candidate_metadata = []
        for path_str in candidate_file_paths:
            if path_str in self.metadata_cache:
                candidate_metadata.append(self.metadata_cache[path_str])
            else:
                if self.verbose:
                    print(f"Warning: Candidate file path '{path_str}' not found in metadata_cache during Stage 2 preparation.")
        
        if not candidate_metadata:
            if self.verbose:
                print("No metadata found for candidate files after Stage 1. Cannot proceed to Stage 2.")
            return []
        
        if self.verbose:
            print(f"Prepared metadata for {len(candidate_metadata)} candidates for Stage 2.")

        # Stage 2: Deep analysis of candidate metadata
        metadata_json_for_estimation = json.dumps(candidate_metadata)
        estimated_tokens_for_metadata = self._estimate_tokens(metadata_json_for_estimation)
        
        prompt_template = self._build_deep_analysis_prompt(query, [], max_results) # empty metadata for template structure
        estimated_tokens_for_prompt_structure = self._estimate_tokens(prompt_template)
        
        total_estimated_tokens_for_stage2 = estimated_tokens_for_metadata + estimated_tokens_for_prompt_structure

        results = []
        if total_estimated_tokens_for_stage2 > self.MAX_INPUT_TOKENS_STAGE2:
            if self.verbose:
                print(f"Estimated tokens for Stage 2 ({total_estimated_tokens_for_stage2}) exceed limit ({self.MAX_INPUT_TOKENS_STAGE2}). Using chunked search.")
            results = self._chunked_search(query, candidate_metadata, max_results)
        else:
            if self.verbose:
                print(f"Estimated tokens for Stage 2 ({total_estimated_tokens_for_stage2}) within limit. Using single call.")
            prompt = self._build_deep_analysis_prompt(query, candidate_metadata, max_results)
            try:
                response = self.client.messages.create(
                    model=self.DEFAULT_MODEL_NAME,
                    max_tokens=self.MAX_OUTPUT_TOKENS,
                    temperature=0,
                    system=self._get_deep_analysis_system_prompt(),
                    messages=[{"role": "user", "content": prompt}]
                )
                raw_results = json.loads(response.content[0].text)
                # Ensure results are sorted and trimmed if not chunked (chunked search does this already)
                raw_results.sort(key=lambda x: x.get("relevance", 0), reverse=True)
                results = raw_results[:max_results]

            except json.JSONDecodeError:
                print("Error: Couldn't parse JSON response from Claude in Stage 2")
                if hasattr(response, 'content'):
                    print(response.content[0].text)
                return []
            except Exception as e:
                print(f"Error querying Claude API in Stage 2: {e}")
                if hasattr(response, 'content') and response.content: # Check if content exists
                     print(f"Claude response: {response.content[0].text}")
                return []
        
        # Cache the results
        self.query_cache[cache_key] = results
        self._save_cache(self.query_cache, self.query_cache_path)
        
        return results

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
                # Handle both single and multi-file results
                if "file_paths" in result:
                    # Multi-file result
                    files = result["file_paths"]
                    rel_type = result.get("relationship_type", "Related Files")
                    print(f"{i}. {rel_type.upper()} (Relevance: {result['relevance']}/10)")
                    for j, path in enumerate(files, 1):
                        print(f"   {j}. {path}")
                else:
                    # Single file result (original format)
                    print(f"{i}. {result['file_path']} (Relevance: {result['relevance']}/10)")
                
                print(f"   Reason: {result['reason']}")
                print("-" * 80)
        else:
            print("No matching results found.")


if __name__ == "__main__":
    main()
