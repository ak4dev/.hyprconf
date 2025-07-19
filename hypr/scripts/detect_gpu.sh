#!/bin/bash

# Check for GeForce RTX 4090 and source the appropriate monitor config
GPU_INFO=$(lspci | grep -i "4090")

if [[ -n "$GPU_INFO" ]]; then
  source ~/.hyprconf/pcMonitors.conf
else
  source ~/.hyprconf/bladeMonitors.conf
fi

