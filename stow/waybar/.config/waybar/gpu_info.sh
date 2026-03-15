#!/usr/bin/env bash
set -euo pipefail

IFS=',' read -r gpu_util power gpu_temp gpu_mem_used gpu_mem_total <<< "$(nvidia-smi \
  --query-gpu=utilization.gpu,power.draw,temperature.gpu,memory.used,memory.total \
  --format=csv,noheader,nounits | xargs)"

echo "{\"gpu_util\":\"${gpu_util}%\",\"power_draw\":${power},\"gpu_temp\":${gpu_temp},\"gpu_mem_used\":${gpu_mem_used},\"gpu_mem_total\":${gpu_mem_total}}"
