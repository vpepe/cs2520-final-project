#!/bin/bash

# Run Stitch compression on Battleship programs

set -e

echo "========================================================================"
echo "STITCH-BASED REFACTORING FOR BATTLESHIP PROGRAMS"
echo "========================================================================"
echo ""

# Step 1: Convert Python programs to Stitch format
echo "Step 1: Converting Python programs to Stitch lambda calculus format..."
python3 python_to_stitch.py

if [ ! -f "battleship_for_stitch.json" ]; then
    echo "Error: Conversion failed"
    exit 1
fi

echo "✓ Conversion complete"
echo ""

# Step 2: Install Stitch (if not already installed)
echo "Step 2: Building Stitch..."
cd stitch
if [ ! -f "Cargo.toml" ]; then
    echo "Error: Stitch repository not found"
    exit 1
fi

# Build Stitch
cargo build --release --bin=compress 2>&1 | tail -20
cd ..

echo "✓ Stitch built"
echo ""

# Step 3: Run Stitch compression
echo "Step 3: Running Stitch compression..."
echo ""

# Run with different iteration counts
for iterations in 1 3 5 10; do
    echo "--------------------------------------------------------------------"
    echo "Running with $iterations iterations..."
    echo "--------------------------------------------------------------------"

    OUTPUT_DIR="stitch_output_iter_${iterations}"
    mkdir -p "$OUTPUT_DIR"

    ./stitch/target/release/compress \
        battleship_for_stitch.json \
        --max-arity=3 \
        --iterations=$iterations \
        --out="$OUTPUT_DIR/out.json" \
        --show-rewritten \
        --rewritten-intermediates \
        2>&1 | tee "$OUTPUT_DIR/log.txt"

    echo ""
    echo "✓ Results saved to $OUTPUT_DIR/"
    echo ""
done

echo "========================================================================"
echo "✓ STITCH COMPRESSION COMPLETE"
echo "========================================================================"
echo ""
echo "Results available in:"
echo "  - stitch_output_iter_1/"
echo "  - stitch_output_iter_3/"
echo "  - stitch_output_iter_5/"
echo "  - stitch_output_iter_10/"
