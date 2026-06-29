#!/bin/bash

##############################################################################
# @file   deploy_starter_package.sh
# @author SRA-SAIL, Noida
# @brief  Script for deploying the X-LINUX-RBT1 web application to STM32MP board
##############################################################################
# @attention
#
# Copyright (c) 2025 STMicroelectronics.
# All rights reserved.
#
# This software is licensed under terms that can be found in the LICENSE file
# in the root directory of this software component.
# If no LICENSE file comes with this software, it is provided AS-IS.
#
##############################################################################

set -e

REMOTE_USER="root"

# Ensure the script is run from the package root directory, or navigate to it
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
PROJECT_ROOT=$(cd -- "${SCRIPT_DIR}/.." &> /dev/null && pwd)

if [ ! -d "${PROJECT_ROOT}/applications" ] || [ ! -d "${PROJECT_ROOT}/kernel" ] || [ ! -d "${PROJECT_ROOT}/scripts" ]; then
    echo "Error: Could not find package root from script location."
    exit 1
fi
cd "${PROJECT_ROOT}"

usage() {
    echo "Usage: $0 -i <ip_address> -b <board_name>"
    echo "  -i <ip_address>: IP address of the target board"
    echo "  -b <board_name>: Name of the board (e.g., stm32mp257f-dk, stm32mp157f-dk2)"
    exit 1
}

while getopts "i:b:" opt; do
    case ${opt} in
        i)
            IP_ADDRESS=${OPTARG}
            ;;
        b)
            BOARD_NAME=${OPTARG}
            ;;
        *)
            usage
            ;;
    esac
done

if [ -z "${IP_ADDRESS}" ] || [ -z "${BOARD_NAME}" ]; then
    usage
fi

echo "Deploying X-LINUX-RBT1 to ${BOARD_NAME} at ${IP_ADDRESS}..."

# 1. Copy correct dtb
DTB_FILE="kernel/6.6.116/${BOARD_NAME}.dtb"
if [ -f "${DTB_FILE}" ]; then
    echo "Copying ${DTB_FILE} to /boot/ on target..."
    scp "${DTB_FILE}" "${REMOTE_USER}@${IP_ADDRESS}:/boot/"
else
    echo "Error: DTB file ${DTB_FILE} not found."
    exit 1
fi

# 2. Deploy web-app
echo "Deploying X-LINUX-RBT1 web application..."
ssh "${REMOTE_USER}@${IP_ADDRESS}" "cd /usr/local/; rm -rf x-linux-rbt1; mkdir -p x-linux-rbt1"
scp -r "applications/web-app/"* "${REMOTE_USER}@${IP_ADDRESS}:/usr/local/x-linux-rbt1/"

# 3. Copy tests directory
echo "Copying tests directory..."
ssh "${REMOTE_USER}@${IP_ADDRESS}" "mkdir -p /usr/local/x-linux-rbt1/tests"
scp -r "tests/"* "${REMOTE_USER}@${IP_ADDRESS}:/usr/local/x-linux-rbt1/tests/"

echo "Syncing file system on target..."
ssh "${REMOTE_USER}@${IP_ADDRESS}" "sync"

echo "Deployment finished successfully."