#!/bin/sh

##
##############################################################################
# @file   deploy.sh
# @author SRA-SAIL, Noida
# @brief  Script for deploying the X-LINUX-RBT1 application to STM32MP board
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
##

# usage ./deploy <ip address of the board>

if [ $# -eq 0 ]; then
    echo "Error: please provide the IP address of the board"
    exit 1
fi

ssh root@$1 "cd /usr/local/;rm -r x-linux-rbt1;mkdir -p x-linux-rbt1"
scp -r ../application/x-linux-rbt1/* root@$1:/usr/local/x-linux-rbt1/