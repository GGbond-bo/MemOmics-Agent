#!/bin/bash
# Heartbeat Monitor for CellBender Pipeline
# Purpose: Write GPU + epoch + file count to monitor.log every 2 minutes
# Usage:   bash heartbeat-monitor.sh &
#          disown

MONITOR_LOG="PROJECT_DATA_DIR/monitor.log"
OUTPUT_DIR="PROJECT_DATA_DIR/cellbender_output"

echo "=== Heartbeat started at $(date) ===" >> "$MONITOR_LOG"

while true; do
    {
        echo ""
        echo "=== $(date '+%Y-%m-%d %H:%M:%S') ==="
        
        # GPU status
        echo "--- GPU ---"
        nvidia-smi --query-gpu=utilization.gpu,memory.used,temperature.gpu --format=csv,noheader
        
        # Filtered.h5 count
        echo "--- OUTPUT ---"
        echo "filtered.h5 count: $(ls "$OUTPUT_DIR"/*/cellbender_output_filtered.h5 2>/dev/null | wc -l)"
        
        # Latest epoch from running sample
        echo "--- EPOCH ---"
        find "$OUTPUT_DIR" -name "cellbender_run.log" -newer "$MONITOR_LOG" -exec tail -1 {} \; 2>/dev/null | tail -1
    } >> "$MONITOR_LOG" 2>&1
    
    sleep 120
done
