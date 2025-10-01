#!/bin/bash
# ACQ4 Installation Script for Linux/macOS
# Interactive installer with hardware and optional dependency selection

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACQ4_ROOT="$(dirname "$SCRIPT_DIR")"

echo -e "${BLUE}=== ACQ4 Interactive Installer ===${NC}"
echo "This script will install ACQ4 and its dependencies."
echo

# Check for conda (required) and mamba (optional for faster env creation)
if ! command -v conda &> /dev/null; then
    echo -e "${RED}Error: conda is not installed or not in PATH.${NC}"
    echo "Please install Anaconda or Miniconda first."
    echo "Visit: https://docs.conda.io/en/latest/miniconda.html"
    exit 1
fi

ENV_CREATE_CMD="conda"
if command -v mamba &> /dev/null; then
    ENV_CREATE_CMD="mamba"
    echo -e "${GREEN}Found mamba - using for faster environment creation${NC}"
else
    echo -e "${BLUE}Using conda for environment creation${NC}"
fi

# Function to ask yes/no questions
ask_yes_no() {
    local prompt="$1"
    local default="$2"
    local response

    if [[ "$default" == "y" ]]; then
        prompt="$prompt [Y/n]: "
    else
        prompt="$prompt [y/N]: "
    fi

    while true; do
        echo -n "$prompt" >&2
        read -r response </dev/tty
        case $response in
            [Yy]* ) return 0 ;;
            [Nn]* ) return 1 ;;
            "" )
                if [[ "$default" == "y" ]]; then
                    return 0
                else
                    return 1
                fi
                ;;
            * ) echo "Please answer yes or no." >&2 ;;
        esac
    done
}

# Function to select dependencies
select_dependencies() {
    local file="$1"
    local default_answer="$2"
    local selected=()

    if [[ ! -f "$file" ]]; then
        echo -e "${YELLOW}Warning: Dependency file $file not found${NC}"
        return
    fi

    while IFS='#' read -r package desc || [[ -n "$package" ]]; do
        # Skip comments and empty lines
        if [[ "$package" =~ ^[[:space:]]*# ]] || [[ -z "${package// }" ]]; then
            continue
        fi

        package=$(echo "$package" | xargs)  # Trim whitespace
        desc=$(echo "$desc" | xargs)

        if [[ -n "$package" ]]; then
            if ask_yes_no "Install $package? ($desc)" "$default_answer"; then
                selected+=("$package")
                echo "  → Selected: $package"
            else
                echo "  → Skipped: $package"
            fi
            echo
        fi
    done < "$file"

    echo "${selected[@]}"
}

echo -e "${YELLOW}=== Configuration ===${NC}"

# Get environment name
default_env="acq4"
read -r -p "Environment name [$default_env]: " env_name
env_name=${env_name:-$default_env}

echo
echo -e "${YELLOW}=== Non-Dev Dependencies ===${NC}"
echo "These are required, but often developers use editable versions instead"
echo
non_dev_deps_file="$SCRIPT_DIR/requirements/non-dev-deps.txt"
selected_non_dev=($(select_dependencies "$non_dev_deps_file" "y"))

echo
echo -e "${YELLOW}=== Hardware Dependencies ===${NC}"
echo "Only install packages for hardware you actually have."
echo
hardware_deps_file="$SCRIPT_DIR/requirements/hardware-deps.txt"
selected_hardware=($(select_dependencies "$hardware_deps_file" "n"))

echo
echo -e "${BLUE}=== Installation Summary ===${NC}"
echo "Environment name: $env_name"
echo "Non-dev dependencies: ${selected_non_dev[*]:-none}"
echo "Hardware dependencies: ${selected_hardware[*]:-none}"
echo

if ! ask_yes_no "Proceed with installation?" "y"; then
    echo "Installation cancelled."
    exit 0
fi

echo
echo -e "${BLUE}=== Installing ACQ4 ===${NC}"

# Check if environment already exists
if conda env list | grep -q "^$env_name "; then
    echo -e "${YELLOW}Environment '$env_name' already exists.${NC}"
    if ! ask_yes_no "Remove and recreate it?" "n"; then
        echo "Installation cancelled."
        exit 1
    fi
    echo "Removing existing environment..."
    conda env remove -n "$env_name" -y
fi

# Create conda environment (use mamba if available for speed)
echo "Creating conda environment '$env_name'..."
cd "$ACQ4_ROOT"
$ENV_CREATE_CMD env create --name="$env_name" --file=tools/requirements/acq4-torch.yml

# Activate environment for pip installs (always use conda for activation)
echo "Activating environment..."
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "$env_name"

# Install ACQ4 in development mode
echo "Installing ACQ4 in development mode..."
pip install -e .

# Install selected non_dev dependencies
if [[ ${#selected_non_dev[@]} -gt 0 ]]; then
    echo "Installing non_dev dependencies..."
    for dep in "${selected_non_dev[@]}"; do
        echo "Installing $dep..."
        pip install "$dep"
    done
fi

# Install selected hardware dependencies
if [[ ${#selected_hardware[@]} -gt 0 ]]; then
    echo "Installing hardware dependencies..."
    for dep in "${selected_hardware[@]}"; do
        echo "Installing $dep..."
        pip install "$dep"
    done
fi

echo
echo -e "${GREEN}=== Installation Complete! ===${NC}"
echo
echo "To use ACQ4:"
echo "  conda activate $env_name"
echo "  python -m acq4"
echo
echo "To deactivate the environment:"
echo "  conda deactivate"
echo