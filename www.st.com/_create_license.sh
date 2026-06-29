#!/bin/sh

# Default value
default_file_name="SLA0047_Package_license_template.md"

# Check if an argument was provided
if [ $# -eq 0 ]; then
    input_filename=$default_file_name
else
    input_filename=$1
fi

# Extract the filename without the extension
filename_without_ext=$(basename "$input_filename" | sed 's/\.[^.]*$//')

pandoc --self-contained -s -r markdown -t html5 -c _htmresc/mini-st_2020.css ${filename_without_ext}.md > ${filename_without_ext}.html

