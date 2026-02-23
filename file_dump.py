#!/usr/bin/env python3
"""
Project File Dumper - Export source files to a single text file for AI chat
"""

import os
import re
import json
from pathlib import Path
from collections import defaultdict

CONFIG_FILE = '.project_dumper_config.json'

def load_config():
    """Load configuration from file"""
    default_config = {
        'mode': '1',
        'max_depth': 3,
        'output_file': 'project_dump.txt',
        'last_selections': []
    }
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                # Merge with defaults in case new keys were added
                return {**default_config, **config}
        except:
            pass
    
    return default_config

def save_config(config):
    """Save configuration to file"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
    except:
        pass

def count_lines(filepath):
    """Count non-empty lines in a file"""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return sum(1 for line in f if line.strip())
    except:
        return 0

def find_imports(filepath):
    """Find imported/included files from C/JS/TS source files"""
    imports = set()
    
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
        ext = filepath.suffix.lower()
        
        # C/C++ includes: #include "file.h" or #include <file.h>
        if ext in {'.c', '.cpp', '.cc', '.cxx', '.h', '.hpp'}:
            # Match both "" and <> includes
            matches = re.findall(r'#include\s+[<"]([^>"]+)[>"]', content)
            imports.update(matches)
        
        # JavaScript/TypeScript imports
        elif ext in {'.js', '.jsx', '.ts', '.tsx', '.mjs'}:
            # import ... from 'file' or require('file')
            matches = re.findall(r'(?:import|require)\s*\(?[\'"]([^\'"]+)[\'"]', content)
            imports.update(matches)
            # export ... from 'file'
            matches = re.findall(r'export\s+.*?from\s+[\'"]([^\'"]+)[\'"]', content)
            imports.update(matches)
    
    except:
        pass
    
    return imports

def resolve_import_path(base_file, import_str, all_files_map):
    """Try to resolve an import string to an actual file path"""
    base_dir = base_file.parent
    candidates = []
    
    # For C/C++ - try common patterns
    if base_file.suffix.lower() in {'.c', '.cpp', '.cc', '.cxx', '.h', '.hpp'}:
        # Try relative to current file's directory
        candidates.append(base_dir / import_str)
        
        # Try sibling directories (e.g., src -> inc, src -> include)
        parent = base_dir.parent
        candidates.append(parent / 'inc' / import_str)
        candidates.append(parent / 'include' / import_str)
        candidates.append(parent / 'h' / import_str)
        candidates.append(parent / 'header' / import_str)
        candidates.append(parent / 'headers' / import_str)
        
        # Try common project-level include directories
        candidates.append(Path('include') / import_str)
        candidates.append(Path('inc') / import_str)
        candidates.append(Path('src') / import_str)
        candidates.append(Path('.') / import_str)
        
        # Search all files by filename if the above fails
        # This is slower but catches files in non-standard locations
        import_filename = Path(import_str).name
        for file_path in all_files_map.values():
            if file_path.name == import_filename:
                candidates.append(file_path)
    
    # For JS/TS - handle relative imports
    elif base_file.suffix.lower() in {'.js', '.jsx', '.ts', '.tsx', '.mjs'}:
        # Handle relative paths
        if import_str.startswith('./') or import_str.startswith('../'):
            candidates.append(base_dir / import_str)
        else:
            # Try as relative anyway
            candidates.append(base_dir / import_str)
        
        # Try with common extensions if no extension provided
        if not Path(import_str).suffix:
            for ext in ['.js', '.jsx', '.ts', '.tsx', '.mjs']:
                if import_str.startswith('./') or import_str.startswith('../'):
                    candidates.append(base_dir / (import_str + ext))
                candidates.append(base_dir / (import_str + ext))
    
    # Try to find a match in our file map
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            if resolved in all_files_map:
                return resolved
        except:
            # If resolve() fails, try direct lookup
            if candidate in all_files_map.values():
                return candidate
    
    return None

def find_counterpart_file(filepath, all_files_map):
    """Find the .c file for a .h file or vice versa"""
    stem = filepath.stem
    ext = filepath.suffix.lower()
    counterparts = []
    
    # For .h/.hpp files, look for .c/.cpp files
    if ext in {'.h', '.hpp'}:
        for c_ext in ['.c', '.cpp', '.cc', '.cxx']:
            # Search in all_files_map for matching filename
            for file_path in all_files_map.values():
                if file_path.stem == stem and file_path.suffix.lower() == c_ext:
                    counterparts.append(file_path)
    
    # For .c/.cpp files, look for .h/.hpp files
    elif ext in {'.c', '.cpp', '.cc', '.cxx'}:
        for h_ext in ['.h', '.hpp']:
            for file_path in all_files_map.values():
                if file_path.stem == stem and file_path.suffix.lower() == h_ext:
                    counterparts.append(file_path)
    
    return counterparts

def collect_dependencies(start_file, all_files_map, max_depth=3):
    """Recursively collect all dependencies up to max_depth"""
    visited = set()
    to_process = [(start_file, 0)]
    result = set()
    
    while to_process:
        current_file, depth = to_process.pop(0)
        
        if current_file in visited or depth > max_depth:
            continue
        
        visited.add(current_file)
        result.add(current_file)
        
        # Always add the counterpart file (.c for .h, .h for .c)
        counterparts = find_counterpart_file(current_file, all_files_map)
        for counterpart in counterparts:
            if counterpart not in visited:
                result.add(counterpart)
                # Also process imports from the counterpart file
                if depth < max_depth:
                    to_process.append((counterpart, depth))
        
        if depth < max_depth:
            imports = find_imports(current_file)
            for import_str in imports:
                resolved = resolve_import_path(current_file, import_str, all_files_map)
                if resolved and resolved not in visited:
                    to_process.append((resolved, depth + 1))
    
    return result

def scan_directory(directory='.', recursive=True):
    """Scan directory and group files by extension"""
    file_groups = defaultdict(list)
    all_files_map = {}  # Map resolved paths to Path objects
    
    if recursive:
        for root, dirs, files in os.walk(directory):
            # Skip common directories
            dirs[:] = [d for d in dirs if d not in {'.git', '.svn', 'node_modules', '__pycache__', 'venv', '.venv', 'dist', 'build'}]
            
            for file in files:
                filepath = Path(root) / file
                ext = filepath.suffix.lower()
                if ext:
                    file_groups[ext].append(filepath)
                    try:
                        all_files_map[filepath.resolve()] = filepath
                    except:
                        pass
    else:
        # Only current directory
        for file in os.listdir(directory):
            filepath = Path(directory) / file
            if filepath.is_file():
                ext = filepath.suffix.lower()
                if ext:
                    file_groups[ext].append(filepath)
                    try:
                        all_files_map[filepath.resolve()] = filepath
                    except:
                        pass
    
    return file_groups, all_files_map

def display_file_groups(file_groups):
    """Display file groups with statistics and return sorted list"""
    stats = []
    
    for ext, files in sorted(file_groups.items()):
        total_lines = sum(count_lines(f) for f in files)
        stats.append((ext, len(files), total_lines, files))
    
    # Sort alphabetically by extension
    stats.sort(key=lambda x: x[0])
    
    print("\n" + "="*60)
    print("FILE STATISTICS (alphabetically sorted)")
    print("="*60)
    
    for idx, (ext, count, lines, _) in enumerate(stats, 1):
        print(f"{idx}) {count} *{ext} files found, total = {lines:,} lines")
    
    print("="*60)
    return stats

def export_files(selected_files, output_file='project_dump.txt'):
    """Export selected files to a single text file"""
    with open(output_file, 'w', encoding='utf-8', errors='ignore') as out:
        for filepath in sorted(selected_files):
            # Use relative path from current directory
            try:
                rel_path = filepath.relative_to('.')
            except:
                rel_path = filepath
            
            out.write(f"\n{'='*60}\n")
            out.write(f"=== {rel_path} ===\n")
            out.write(f"{'='*60}\n\n")
            
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    out.write(content)
                    if content and not content.endswith('\n'):
                        out.write('\n')
            except Exception as e:
                out.write(f"[Error reading file: {e}]\n")
    
    print(f"\n✓ Exported {len(selected_files)} files to '{output_file}'")
    print(f"✓ File size: {os.path.getsize(output_file):,} bytes")

def main():
    print("Project File Dumper")
    
    # Load saved configuration
    config = load_config()
    
    print("\nScan mode:")
    print("1) Recursive (scan all subdirectories)")
    print("2) Current directory only")
    print("3) Dependency mode (specify a file and collect its imports)")
    print(f"\nSelect mode (1/2/3, default={config['mode']}): ", end='')
    
    mode = input().strip() or config['mode']
    config['mode'] = mode
    
    if mode == '3':
        # Dependency collection mode
        print("\nEnter the path to the starting file: ", end='')
        start_file = input().strip()
        
        if not start_file or not os.path.isfile(start_file):
            print(f"Error: File '{start_file}' not found!")
            return
        
        print(f"Maximum dependency depth (1-5, default={config['max_depth']}): ", end='')
        depth_input = input().strip()
        max_depth = int(depth_input) if depth_input.isdigit() else config['max_depth']
        max_depth = max(1, min(5, max_depth))
        config['max_depth'] = max_depth
        
        print(f"\nScanning dependencies (depth={max_depth})...")
        
        # Need to build file map
        file_groups, all_files_map = scan_directory('.', recursive=True)
        
        start_path = Path(start_file).resolve()
        dependencies = collect_dependencies(start_path, all_files_map, max_depth)
        
        print(f"\nFound {len(dependencies)} files (including starting file):")
        for dep in sorted(dependencies):
            try:
                print(f"  - {dep.relative_to('.')}")
            except:
                print(f"  - {dep}")
        
        print(f"\nOutput filename (default: {config['output_file']}): ", end='')
        output_file = input().strip() or config['output_file']
        config['output_file'] = output_file
        
        save_config(config)
        export_files(dependencies, output_file)
        return
    
    # Regular scanning mode
    recursive = (mode != '2')
    print(f"\nScanning {'recursively' if recursive else 'current directory only'}...")
    
    file_groups, all_files_map = scan_directory('.', recursive=recursive)
    
    if not file_groups:
        print("\nNo files found!")
        return
    
    stats = display_file_groups(file_groups)
    
    # Get user selection
    last_sel = ','.join(map(str, config['last_selections'])) if config['last_selections'] else ''
    if last_sel:
        print(f"\nEnter the numbers of file types to export (comma-separated, e.g., 1,2,3)")
        print(f"Last used: {last_sel}")
        print("Or press Enter to cancel: ", end='')
    else:
        print("\nEnter the numbers of file types to export (comma-separated, e.g., 1,2,3)")
        print("Or press Enter to cancel: ", end='')
    
    selection = input().strip()
    
    if not selection:
        print("Cancelled.")
        return
    
    # Parse selection
    try:
        indices = [int(x.strip()) for x in selection.split(',')]
        config['last_selections'] = indices
        selected_files = []
        
        for idx in indices:
            if 1 <= idx <= len(stats):
                _, _, _, files = stats[idx - 1]
                selected_files.extend(files)
            else:
                print(f"Warning: Invalid selection '{idx}' ignored")
        
        if not selected_files:
            print("No valid files selected!")
            return
        
        # Ask for output filename
        print(f"\nOutput filename (default: {config['output_file']}): ", end='')
        output_file = input().strip() or config['output_file']
        config['output_file'] = output_file
        
        # Save configuration
        save_config(config)
        
        # Export files
        print(f"\nExporting {len(selected_files)} files...")
        export_files(selected_files, output_file)
        
    except ValueError:
        print("Invalid input! Please enter comma-separated numbers.")
        return

if __name__ == "__main__":
    main()