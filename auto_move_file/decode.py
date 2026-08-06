"""
Decoder for base64-encoded file dumps.

Reads a file where each line has the format:
    relative/path/to/file(base64 encoded): <base64_data>

and recreates each file (with its directory structure) into an output folder.
"""

import base64
import os
import sys
import zlib

# Marker that separates the file path from the encoded data
MARKER = "(base64 encoded): "


def get_input_path():
    """Get the encoded dump file path (arg 1) and output dir (arg 2, optional)"""
    if len(sys.argv) > 1:
        input_path = sys.argv[1]
    else:
        input_path = input("Enter path to encoded dump file: ").strip()

    if len(sys.argv) > 2:
        output_dir = sys.argv[2]
    else:
        output_dir = input("Enter output directory (default: 'decoded_output'): ").strip()
        if not output_dir:
            output_dir = "decoded_output"

    return input_path, output_dir


def parse_line(line):
    """Parse a single line into (relative_path, encoded_data).

    Returns None if the line doesn't match the expected format.
    """
    line = line.rstrip("\n")
    if MARKER not in line:
        return None

    rel_path, encoded = line.split(MARKER, 1)
    rel_path = rel_path.strip()
    encoded = encoded.strip()

    if not rel_path or not encoded:
        return None

    return rel_path, encoded


def decode_and_write(rel_path, encoded, output_dir):
    """Decode base64 data and write it to output_dir/rel_path"""
    try:
        compressed = base64.b64decode(encoded.encode("utf-8"))
        content: str = zlib.decompress(compressed).decode("utf-8") 
    except Exception as e:
        print(f"  Failed to decode '{rel_path}': {e}")
        return False

    # Normalize path separators and build the full output path
    safe_rel = rel_path.replace("\\", os.sep).replace("/", os.sep)
    full_path = os.path.join(output_dir, safe_rel)

    # Guard against path traversal: the decoded file must stay inside output_dir.
    output_root = os.path.realpath(output_dir)
    target = os.path.realpath(full_path)
    try:
        inside = os.path.commonpath([output_root, target]) == output_root
    except ValueError:
        inside = False
    if not inside:
        print(f"  Skipped '{rel_path}': path escapes the output directory")
        return False

    # Create parent directories as needed
    parent = os.path.dirname(full_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    try:
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  Created: {full_path}")
        return True
    except Exception as e:
        print(f"  Failed to write '{full_path}': {e}")
        return False


def main() -> int:
    """Main function"""
    print("=" * 50)
    print("File Content Decoder (Base64)")
    print("=" * 50)

    input_path, output_dir = get_input_path()

    if not os.path.isfile(input_path):
        print(f"Error: '{input_path}' is not a valid file")
        return 1

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as exc:
        print(f"Error reading '{input_path}': {exc}")
        return 2

    created = 0
    skipped = 0

    print(f"\nDecoding into: {output_dir}")
    print("-" * 50)

    for line in lines:
        if not line.strip():
            continue

        parsed = parse_line(line)
        if parsed is None:
            print(f"  Skipping malformed line: {line[:50].strip()}...")
            skipped += 1
            continue

        rel_path, encoded = parsed
        if decode_and_write(rel_path, encoded, output_dir):
            created += 1
        else:
            skipped += 1

    print("-" * 50)
    print(f"Done! {created} file(s) created, {skipped} skipped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
