#!/usr/bin/env bash
set -euo pipefail

detect_script_dir() {
    local source="${BASH_SOURCE[0]:-}"
    if [[ -z "${source}" || ! -f "${source}" ]]; then
        return 1
    fi
    local dir
    if ! dir="$(cd -- "$(dirname -- "${source}")" && pwd)"; then
        return 1
    fi
    printf "%s\n" "${dir}"
}

SCRIPT_DIR=""
if ! SCRIPT_DIR="$(detect_script_dir)"; then
    SCRIPT_DIR=""
fi
INSTALLER_URL="https://raw.githubusercontent.com/acq4/acq4/main/tools/installer/installer.py"
PYTHON_VERSION="3.12"
QT_PACKAGE="pyqt6"
TOML_PARSER_PACKAGE="tomli"
INSTALLER_ENV_NAME="_acq4_installer_env"
MIN_CONDA_VERSION="4.14.0"
MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh"
MINICONDA_PREFIX="${HOME}/miniconda3"
DOWNLOADED_INSTALLER=""
BOOTSTRAP_ENV_PATH=""

log() {
    >&2 echo "[acq4-installer] $*"
}

find_conda() {
    local -a candidate_list=()
    if [[ -n "${CONDA_EXE:-}" ]]; then
        candidate_list+=("${CONDA_EXE}")
    fi

    local path_candidate
    path_candidate="$(command -v conda 2>/dev/null || true)"
    if [[ -n "${path_candidate}" ]]; then
        candidate_list+=("${path_candidate}")
    fi

    candidate_list+=("${HOME}/miniconda3/bin/conda" \
                     "${HOME}/anaconda3/bin/conda" \
                     "/opt/conda/bin/conda")

    declare -A seen=()
    local -a candidates=()
    for path_candidate in "${candidate_list[@]}"; do
        if [[ -n "${path_candidate}" && -x "${path_candidate}" && -z "${seen[${path_candidate}]:-}" ]]; then
            candidates+=("${path_candidate}")
            seen["${path_candidate}"]=1
        fi
    done

    local best_path=""
    local best_version=""
    local fallback_path=""
    local candidate version_output version latest
    for candidate in "${candidates[@]}"; do
        if version_output="$("${candidate}" --version 2>/dev/null)"; then
            version="${version_output##* }"
            version="${version//[[:space:]]/}"
            if [[ -z "${version}" ]]; then
                if [[ -z "${fallback_path}" ]]; then
                    fallback_path="${candidate}"
                fi
                continue
            fi
            if [[ -z "${best_version}" ]]; then
                best_version="${version}"
                best_path="${candidate}"
            else
                latest="$(printf '%s\n%s\n' "${version}" "${best_version}" | sort -V | tail -n1)"
                if [[ "${latest}" == "${version}" && "${version}" != "${best_version}" ]]; then
                    best_version="${version}"
                    best_path="${candidate}"
                fi
            fi
        else
            if [[ -z "${fallback_path}" ]]; then
                fallback_path="${candidate}"
            fi
        fi
    done

    if [[ -n "${best_path}" ]]; then
        if [[ -n "${best_version}" ]]; then
            log "Using conda at ${best_path} (version ${best_version})"
        else
            log "Using conda at ${best_path}"
        fi
        echo "${best_path}"
        return 0
    fi

    if [[ -n "${fallback_path}" ]]; then
        log "Using conda at ${fallback_path}"
        echo "${fallback_path}"
        return 0
    fi

    if (( ${#candidates[@]} > 0 )); then
        log "Using conda at ${candidates[0]}"
        echo "${candidates[0]}"
        return 0
    fi

    return 1
}

install_miniconda() {
    log "Conda executable not found."
    read -rp "Download and install Miniconda to ${MINICONDA_PREFIX}? [y/N] " reply
    if [[ ! "${reply}" =~ ^[Yy]$ ]]; then
        log "Cannot proceed without conda. Exiting."
        exit 1
    fi

    local tmp_installer
    tmp_installer="$(mktemp -t miniconda-installer-XXXXXX.sh)"
    log "Downloading Miniconda installer..."
    curl -fsSL "${MINICONDA_URL}" -o "${tmp_installer}"
    chmod +x "${tmp_installer}"
    log "Running Miniconda installer..."
    "${tmp_installer}" -b -u -p "${MINICONDA_PREFIX}"
    rm -f "${tmp_installer}"
    echo "${MINICONDA_PREFIX}/bin/conda"
}

installer_env_path() {
    local conda_exe="$1"
    local base_path
    base_path="$("${conda_exe}" info --base)"
    printf "%s/envs/%s" "${base_path}" "${INSTALLER_ENV_NAME}"
}

ensure_installer_env() {
    local conda_exe="$1"
    local env_path
    env_path="$(installer_env_path "${conda_exe}")"
    BOOTSTRAP_ENV_PATH="${env_path}"
    if [[ ! -d "${env_path}/conda-meta" ]]; then
        log "Creating installer environment..."
        local create_cmd=("${conda_exe}" create -y -n "${INSTALLER_ENV_NAME}" "python=${PYTHON_VERSION}" pip)
        local create_cmd_str
        printf -v create_cmd_str '%q ' "${create_cmd[@]}"
        log "Running: ${create_cmd_str% }"
        local create_log
        create_log="$(mktemp -t acq4-conda-create-XXXXXX.log)"
        if ! "${create_cmd[@]}" 2>&1 | tee "${create_log}"; then
            if grep -q "NoWritableEnvsDirError" "${create_log}"; then
                log "Conda could not create the installer environment: no writable envs directories are configured."
                log "Please ensure 'conda info --json' lists at least one writable path under 'envs_dirs'."
            elif grep -q "NoWritablePkgsDirError" "${create_log}"; then
                log "Conda could not download packages: no writable package cache directories are configured."
            fi
            log "Conda output:"
            cat "${create_log}"
            rm -f "${create_log}"
            exit 1
        fi
        rm -f "${create_log}"
    fi
    "${conda_exe}" run -n "${INSTALLER_ENV_NAME}" python -m pip install --quiet --upgrade \
        "${QT_PACKAGE}" "${TOML_PARSER_PACKAGE}"
}

check_conda_version() {
    local conda_exe="$1"
    local version_output
    if ! version_output="$("${conda_exe}" --version 2>/dev/null)"; then
        log "Unable to determine conda version; please ensure '${conda_exe}' is executable."
        exit 1
    fi
    local version="${version_output##* }"
    version="${version//[[:space:]]/}"
    if [[ -z "${version}" ]]; then
        log "Unable to parse conda version from output: ${version_output}"
        exit 1
    fi
    local earliest
    earliest="$(printf '%s\n%s\n' "${MIN_CONDA_VERSION}" "${version}" | sort -V | head -n1)"
    if [[ "${earliest}" != "${MIN_CONDA_VERSION}" ]]; then
        log "Conda version ${version} is too old; 'conda run' requires ${MIN_CONDA_VERSION} or newer."
        exit 1
    fi
}

download_installer_script() {
    if [[ -n "${SCRIPT_DIR}" ]]; then
        local local_installer="${SCRIPT_DIR}/installer.py"
        if [[ -f "${local_installer}" ]]; then
            echo "${local_installer}"
            return 0
        fi
    fi

    if ! command -v curl >/dev/null 2>&1; then
        log "curl is not available; cannot download installer."
        exit 1
    fi

    local tmp_installer
    if ! tmp_installer="$(mktemp -t acq4-installer-XXXXXX.py)"; then
        log "Unable to create temporary file for installer download."
        exit 1
    fi

    log "Downloading installer from ${INSTALLER_URL}"
    if curl -fsSL "${INSTALLER_URL}" -o "${tmp_installer}"; then
        DOWNLOADED_INSTALLER="${tmp_installer}"
        echo "${tmp_installer}"
        return 0
    fi

    local status=$?
    rm -f "${tmp_installer}"
    log "Failed to download installer.py (curl exit ${status})."
    exit 1
}

run_installer() {
    local conda_exe="$1"
    local installer_script="$2"
    shift 2
    "${conda_exe}" run -n "${INSTALLER_ENV_NAME}" python "${installer_script}" "$@"
}

cleanup_installer() {
    if [[ -n "${DOWNLOADED_INSTALLER}" && -f "${DOWNLOADED_INSTALLER}" ]]; then
        rm -f "${DOWNLOADED_INSTALLER}"
    fi
}

main() {
    trap cleanup_installer EXIT
    local conda_exe
    if ! conda_exe="$(find_conda)"; then
        conda_exe="$(install_miniconda)"
    fi
    export CONDA_EXE="${conda_exe}"
    check_conda_version "${conda_exe}"
    ensure_installer_env "${conda_exe}"
    if [[ -z "${BOOTSTRAP_ENV_PATH}" ]]; then
        BOOTSTRAP_ENV_PATH="$(installer_env_path "${conda_exe}")"
    fi
    local installer_script
    installer_script="$(download_installer_script)"
    run_installer "${conda_exe}" "${installer_script}" "$@"
}

main "$@"
