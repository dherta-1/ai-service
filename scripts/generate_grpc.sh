#!/bin/bash
# Dynamically generate gRPC Python code from all proto files in src/proto directory

PROTO_DIR="src/proto"
OUTPUT_DIR="src/grpc_generated"

if [ ! -d "$PROTO_DIR" ]; then
    echo "Error: Proto directory not found: $PROTO_DIR"
    exit 1
fi

# Create output directory if it doesn't exist
mkdir -p "$OUTPUT_DIR"

echo "Discovering proto files in $PROTO_DIR..."
proto_files=$(find "$PROTO_DIR" -name "*.proto" -type f | sort)

if [ -z "$proto_files" ]; then
    echo "Error: No proto files found in $PROTO_DIR"
    exit 1
fi

echo "Found proto files:"
echo "$proto_files" | sed 's/^/  - /'

echo ""
echo "Generating gRPC Python code..."

# Generate code for each proto file
for proto_file in $proto_files; do
    echo "  Processing: $proto_file"
    python -m grpc_tools.protoc \
        -I"$PROTO_DIR" \
        --python_out="$OUTPUT_DIR" \
        --grpc_python_out="$OUTPUT_DIR" \
        "$proto_file"
done

# Fix imports in all generated pb2 files
echo ""
echo "Fixing imports in generated files..."

# Process all generated Python files
for py_file in "$OUTPUT_DIR"/*_pb2.py "$OUTPUT_DIR"/*_pb2_grpc.py; do
    if [ -f "$py_file" ]; then
        filename=$(basename "$py_file")
        
        # Fix all relative imports to use relative import syntax
        sed -i 's/^import \([a-z_]*_pb2\) as/from . import \1 as/g' "$py_file"
        
        if [ $? -eq 0 ]; then
            echo "  ✓ Fixed imports in $filename"
        else
            echo "  ✗ Failed to fix imports in $filename"
        fi
    fi
done

echo ""
echo "✓ gRPC code generation completed!"
echo ""
echo "Generated files:"
ls -lh "$OUTPUT_DIR"/*.py 2>/dev/null | grep -E "_(pb2|pb2_grpc)\.py" | awk '{print "  - " $9 " (" $5 ")"}'

echo ""
echo "Proto statistics:"
echo "  - Total proto files: $(echo "$proto_files" | wc -l)"
echo "  - Generated Python files: $(ls -1 "$OUTPUT_DIR"/*pb2*.py 2>/dev/null | wc -l)"

