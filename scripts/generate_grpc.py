#!/usr/bin/env python3
"""
Dynamic gRPC code generation from all proto files.
Auto-discovers all .proto files and generates gRPC Python code with fixed imports.
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List


class ProtoBufGenerator:
    """Handles protobuf code generation and import fixing"""

    def __init__(
        self, proto_dir: str = "src/proto", output_dir: str = "src/grpc_generated"
    ):
        self.proto_dir = Path(proto_dir)
        self.output_dir = Path(output_dir)

    def discover_proto_files(self) -> List[Path]:
        """Discover all .proto files in the proto directory"""
        if not self.proto_dir.exists():
            print(f"Error: Proto directory not found: {self.proto_dir}")
            sys.exit(1)

        proto_files = sorted(self.proto_dir.glob("*.proto"))
        return proto_files

    def generate_code(self, proto_files: List[Path]) -> bool:
        """Generate gRPC Python code for all proto files"""
        if not proto_files:
            print(f"Error: No proto files found in {self.proto_dir}")
            return False

        print(f"Generating gRPC Python code for {len(proto_files)} proto file(s)...")

        for proto_file in proto_files:
            print(f"  Processing: {proto_file}")

            cmd = [
                sys.executable,
                "-m",
                "grpc_tools.protoc",
                f"-I{self.proto_dir}",
                f"--python_out={self.output_dir}",
                f"--grpc_python_out={self.output_dir}",
                str(proto_file),
            ]

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                print(f"    ✓ Generated successfully")
            except subprocess.CalledProcessError as e:
                print(f"    ✗ Failed: {e.stderr}")
                return False
            except FileNotFoundError:
                print(
                    f"    ✗ grpcio-tools not installed. Install with: pip install grpcio-tools"
                )
                return False

        return True

    def fix_imports_in_file(self, filepath: Path) -> bool:
        """Fix imports in a generated file to use relative imports"""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            original_content = content

            # Fix all relative imports to use relative import syntax
            # Pattern: import <module_pb2> as ... -> from . import <module_pb2> as ...
            content = re.sub(
                r"^import ([a-z_]*_pb2) as",
                r"from . import \1 as",
                content,
                flags=re.MULTILINE,
            )

            if content != original_content:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                return True

            return False

        except Exception as e:
            print(f"    Error: {e}")
            return False

    def fix_all_imports(self) -> int:
        """Fix imports in all generated Python files"""
        print("")
        print("Fixing imports in generated files...")

        fixed_count = 0

        # Process both pb2 and pb2_grpc files
        for pattern in ["*_pb2.py", "*_pb2_grpc.py"]:
            for py_file in self.output_dir.glob(pattern):
                filename = py_file.name
                if self.fix_imports_in_file(py_file):
                    print(f"  ✓ Fixed imports in {filename}")
                    fixed_count += 1
                else:
                    # File might not have needed fixing
                    pass

        return fixed_count

    def print_statistics(self, proto_files: List[Path]) -> None:
        """Print generation statistics"""
        print("")
        print("=" * 60)
        print("✓ gRPC code generation completed!")
        print("=" * 60)
        print("")
        print("Proto files processed:")
        for proto_file in proto_files:
            print(f"  - {proto_file.name}")

        print("")
        print("Generated Python files:")
        for py_file in sorted(self.output_dir.glob("*pb2*.py")):
            size = py_file.stat().st_size
            size_kb = f"{size / 1024:.1f} KB" if size > 1024 else f"{size} B"
            print(f"  - {py_file.name:35} ({size_kb:>8})")

        total_proto = len(proto_files)
        total_generated = len(list(self.output_dir.glob("*pb2*.py")))

        print("")
        print("Statistics:")
        print(f"  - Total proto files:        {total_proto}")
        print(f"  - Generated Python files:   {total_generated}")
        print(f"  - Output directory:         {self.output_dir}")

    def run(self) -> bool:
        """Run the complete generation process"""
        print("Discovering proto files...")
        proto_files = self.discover_proto_files()

        if not proto_files:
            return False

        print(f"Found {len(proto_files)} proto file(s):")
        for proto_file in proto_files:
            print(f"  - {proto_file.name}")

        print("")

        # Generate code
        if not self.generate_code(proto_files):
            return False

        # Fix imports
        self.fix_all_imports()

        # Print statistics
        self.print_statistics(proto_files)

        return True


def main():
    """Main entry point"""
    generator = ProtoBufGenerator()
    success = generator.run()
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
