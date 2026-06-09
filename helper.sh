#!/usr/bin/env bash

# ===> HEADER SECTION START  ===>

# http://bash.cumulonim.biz/NullGlob.html
shopt -s nullglob
# -------------------------------
this_folder="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
if [ -z "$this_folder" ]; then
  this_folder=$(dirname $(readlink -f $0))
fi
parent_folder=$(dirname "$this_folder")

# -------------------------------
# --- required functions
debug(){
    local __msg="$1"
    echo " [DEBUG] `date` ... $__msg "
}

info(){
    local __msg="$1"
    echo " [INFO]  `date` ->>> $__msg "
}

warn(){
    local __msg="$1"
    echo " [WARN]  `date` *** $__msg "
}

err(){
    local __msg="$1"
    echo " [ERR]   `date` !!! $__msg "
}


source_if_exists() {
  local file="$1"
  if [ ! -f "$file" ]; then
    warn "we DON'T have a $(basename "$file") file - creating it"
    touch "$file"
    chmod 600 "$file"
  else
    . "$file"
  fi
}

# ---------- CONSTANTS ----------
export FILE_VARIABLES=${FILE_VARIABLES:-".variables"}
export FILE_LOCAL_VARIABLES=${FILE_LOCAL_VARIABLES:-".local_variables"}
export FILE_SECRETS=${FILE_SECRETS:-".secrets"}
export INCLUDE_FILE=${INCLUDE_FILE:-".bashutils"}
export BASHUTILS_URL=${BASHUTILS_URL:-"https://api.github.com/repos/tgedr/bashutils/contents/.bashutils"}
export BASHUTILS_CHECKSUM_URL=${BASHUTILS_CHECKSUM_URL:-"https://api.github.com/repos/tgedr/bashutils/contents/.bashutils.checksum"}
export BASHUTILS_CHECK_INTERVAL_SECONDS=${BASHUTILS_CHECK_INTERVAL_SECONDS:-"86400"}

get_file_mtime_epoch() {
  local file="$1"
  local mtime
  mtime="$(stat -c %Y "$file" 2>/dev/null)" && {
    echo "$mtime"
    return 0
  }
  mtime="$(stat -f %m "$file" 2>/dev/null)" && {
    echo "$mtime"
    return 0
  }
  return 1
}

download_bashutils_if_newer() {
  local bashutils="$this_folder/$INCLUDE_FILE"
  local bashutils_last_check="$this_folder/${INCLUDE_FILE}.last_check"
  local bashutils_checksum="$this_folder/${INCLUDE_FILE}.checksum"
  local just_fetch="0"
  local now_epoch
  local last_check_epoch
  local elapsed
  local did_remote_check=0
  local bashutils_tmp
  local checksum_tmp
  local actual_sha256
  local expected_sha256

  if [ -f "$bashutils" ] && [ -f "$bashutils_last_check" ]; then
    now_epoch=$(date +%s)
    if last_check_epoch="$(get_file_mtime_epoch "$bashutils_last_check")"; then
      case "$last_check_epoch" in
        ''|*[!0-9]*)
          warn "[download_bashutils_if_newer] invalid last check marker timestamp, forcing a remote check"
          ;;
        *)
          elapsed=$((now_epoch - last_check_epoch))
          if [ "$elapsed" -lt "$BASHUTILS_CHECK_INTERVAL_SECONDS" ]; then
            info "[download_bashutils_if_newer] no need to update $INCLUDE_FILE (last checked $elapsed seconds ago)"
            return 0
          fi
          ;;
      esac
    fi
  else
    info "[download_bashutils_if_newer] no $INCLUDE_FILE or ${INCLUDE_FILE}.last_check found - we will fetch it"
    just_fetch="1"
  fi

  if ! command -v curl >/dev/null 2>&1; then
    err "[download_bashutils_if_newer] please install curl"
    return 1
  fi

  if ! command -v sha256sum >/dev/null 2>&1; then
    err "[download_bashutils_if_newer] please install sha256sum to verify $INCLUDE_FILE"
    return 1
  fi

  checksum_tmp="$(mktemp)"
  if ! curl -fsSL "$BASHUTILS_CHECKSUM_URL" \
    | python3 -c "import sys,json,base64; sys.stdout.buffer.write(base64.b64decode(json.load(sys.stdin)['content']))" \
    > "$checksum_tmp"; then
    err "[download_bashutils_if_newer] failed to download $(basename "$BASHUTILS_CHECKSUM_URL")"
    rm -f "$checksum_tmp"
    return 1
  fi
  expected_sha256=$(cat "$checksum_tmp" | awk '{print $1}')
  info "[download_bashutils_if_newer] expected_sha256: $expected_sha256"
  rm -f "$checksum_tmp"

  if [ "$just_fetch" -ne "1" ]; then
      info "[download_bashutils_if_newer] checking existing $INCLUDE_FILE"

      actual_sha256=$(cat "$bashutils_checksum" | awk '{print $1}')
      info "[download_bashutils_if_newer] actual_sha256: $actual_sha256"
      
      if [ "$actual_sha256" != "$expected_sha256" ]; then
        info "[download_bashutils_if_newer] $INCLUDE_FILE is outdated (actual: $actual_sha256, expected: $expected_sha256), updating it"
        just_fetch="1"
      else
        info "[download_bashutils_if_newer] $INCLUDE_FILE is up to date"
      fi
  fi


  if [ "$just_fetch" -eq "1" ]; then
    bashutils_tmp="$(mktemp)"
    curl -fsSL "$BASHUTILS_URL" \
      | python3 -c "import sys,json,base64; sys.stdout.buffer.write(base64.b64decode(json.load(sys.stdin)['content']))" \
      > "$bashutils_tmp"
    if [ ! "$?" -eq "0" ]; then
      err "[download_bashutils_if_newer] failed to download $INCLUDE_FILE"
      rm -f "$bashutils_tmp"
      return 1
    fi
    info "[download_bashutils_if_newer] downloaded $INCLUDE_FILE to $bashutils_tmp"
    actual_sha256="$(sha256sum "$bashutils_tmp" | awk '{print $1}')"
    info "[download_bashutils_if_newer] actual_sha256: $actual_sha256"

    if [ "$actual_sha256" != "$expected_sha256" ]; then
      info "[download_bashutils_if_newer] $INCLUDE_FILE checksum is not equal to the expected one (actual: $actual_sha256, expected: $expected_sha256), aborting update"
      return 1
    fi

    mv "$bashutils_tmp" "$bashutils"
    rm -f "$bashutils_tmp"
    touch "$bashutils_last_check" || warn "[download_bashutils_if_newer] failed to update last check marker; next run will perform a remote check"
    info "[download_bashutils_if_newer] updated $INCLUDE_FILE or ${INCLUDE_FILE}.last_check "
  fi

}

# -------------------------------
# --- source variables files
source_if_exists "$this_folder/$FILE_VARIABLES"
source_if_exists "$this_folder/$FILE_LOCAL_VARIABLES"
source_if_exists "$this_folder/$FILE_SECRETS"

# ---------- include bashutils ----------
BASHUTILS_UPDATE="${BASHUTILS_UPDATE:-0}"
[ "$BASHUTILS_UPDATE" -eq "1" ] && download_bashutils_if_newer
. "$this_folder/$INCLUDE_FILE"

# <=== HEADER SECTION END  <===


# ===> MAIN SECTION    ===>
# ---------- CONSTANTS ----------
export SRC_DIR=${SRC_DIR:-"${this_folder}/src"}
export TEST_DIR=${TEST_DIR:-"${this_folder}/test"}
# -------------------------------
# --- main functions

reqs(){
  info "[reqs|in]"
  _pwd=`pwd`
  cd "$this_folder"

  uv sync --group dev
  local result="$?"
  if [ ! "$result" -eq "0" ] ; then err "[reqs] could not install dependencies"; fi
  
  go install github.com/open-telemetry/opentelemetry-collector-contrib/cmd/telemetrygen@latest

  cd "$_pwd"

  local msg="[reqs|out] => ${result}"
  [[ ! "$result" -eq "0" ]] && info "$msg" && exit 1
  info "$msg"
}


test_collector(){
  info "[test_collector|in]"
  _pwd=`pwd`
  cd "$this_folder"

  
  docker pull "$OTEL_COLLECTOR_IMG"
  docker run -p 4317:4317 -p 4318:4318 -p 55679:55679 --name test-collector "$OTEL_COLLECTOR_IMG" &
  sleep 3
  info "[test_collector] generating test traces with telemetrygen"
  $GOBIN/telemetrygen traces --otlp-insecure --traces 3
  sleep 6
  info "[test_collector] stopping test collector container"
  docker rm -f test-collector

  local result="$?"
  if [ ! "$result" -eq "0" ] ; then err "[test_collector] tests failed"; fi
  cd "$_pwd"

  local msg="[test_collector|out] => ${result}"
  [[ ! "$result" -eq "0" ]] && info "$msg" && exit 1
  info "$msg"
}

build_docker_image(){
  info "[build_docker_image|in]"
  _pwd=`pwd`

  cd "$this_folder/$DOCKER_DIR"

  docker build --build-arg OTEL_COLLECTOR_IMG_VERSION="$OTEL_COLLECTOR_IMG_VERSION" -t "$CUSTOM_COLLECTOR_IMAGE" . \
    && docker push "$CUSTOM_COLLECTOR_IMAGE"
  local result="$?"
  if [ ! "$result" -eq "0" ] ; then err "[build_docker_image] failed to build the docker image"; fi
  cd "$_pwd"

  local msg="[build_docker_image|out] => ${result}"
  [[ ! "$result" -eq "0" ]] && info "$msg" && exit 1
  info "$msg"
}

run_collector(){
  info "[run_collector|in]"

  _pwd=`pwd`
  cd "$this_folder"
  
  [ -d "$this_folder/${TMP_DIR}" ] || mkdir "$this_folder/${TMP_DIR}"
  cd "$this_folder/${TMP_DIR}"
  [ -d "${OUTPUT_DIR}" ] || mkdir "${OUTPUT_DIR}"

  docker run --rm -p 4317:4317 -p 4318:4318 -v "./${OUTPUT_DIR}:/${OUTPUT_DIR}" --name "$CONTAINER_NAME" "$CUSTOM_COLLECTOR_IMAGE"
  local result="$?"
  if [ ! "$result" -eq "0" ] ; then err "[run_collector] failed to run the collector"; fi
  cd "$_pwd"

  local msg="[run_collector|out] => ${result}"
  [[ ! "$result" -eq "0" ]] && info "$msg" && exit 1
  info "$msg"
}




setup_debian(){
  info "[setup_debian|in]"

  if [ "$(id -u)" -ne 0 ]; then
    err "[setup_debian] must be run as root"
    exit 1
  fi

  apt-get update -y

  # --- docker
  info "[setup_debian] installing docker"
  apt-get install -y ca-certificates curl gnupg lsb-release
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \
    $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io
  systemctl enable --now docker

  # --- docker-compose
  info "[setup_debian] installing docker-compose"
  local compose_version
  compose_version="$(curl -fsSL https://api.github.com/repos/docker/compose/releases/latest | grep '"tag_name"' | sed 's/.*: *"//;s/".*//')"
  curl -fsSL "https://github.com/docker/compose/releases/download/${compose_version}/docker-compose-linux-$(uname -m)" \
    -o /usr/local/bin/docker-compose
  chmod +x /usr/local/bin/docker-compose

  # --- python 3.12
  info "[setup_debian] installing python 3.12"
  apt-get install -y software-properties-common
  apt-get update -y
  apt-get install -y python3.12 python3.12-venv python3.12-dev python3-pip
  update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 100
  update-alternatives --set python3 /usr/bin/python3.12
  update-alternatives --install /usr/bin/python python /usr/bin/python3.12 100
  update-alternatives --set python /usr/bin/python3.12

  local result="$?"
  local msg="[setup_debian|out] => ${result}"
  [[ ! "$result" -eq "0" ]] && info "$msg" && exit 1
  info "$msg"
}


# <=== MAIN SECTION END  <===


# ===> FOOTER SECTION START  ===>

usage() {
  cat <<EOM
  usage:
  $(basename $0) { option }
    options:
      - reqs                                  installs development requirements
      - linter_check                          runs code lint and format check
      - sast_check                            runs static application security tests (SAST) check
      - sca_check                             runs software component analysis (SCA) check
      - test [<test_folder>]                  runs unit tests
      - test_coverage                         prints test coverage report
      - test_coverage_check <threshold>       checks coverage against a threshold
      - build                                 builds the package
      - publish                               publishes the package
      - tag                                   creates a git tag with the version and pushes it
      - test_collector                        runs the OpenTelemetry Collector in a container for testing purposes
      - build_docker_image                     builds the OpenTelemetry Collector Docker image
      - run_collector                         runs the OpenTelemetry Collector Docker image
      - setup_debian                          installs docker, docker-compose and python 3.12 on Debian OS
EOM
  exit 1
}


case "$1" in
  reqs)
    reqs
    ;;
  linter_check)
    lint_check_ruff_uv
    ;;
  sast_check)
    sast_check_bandit_uv "$SRC_DIR"
    ;;
  sca_check)
    sca_check_safety_uv "$SAFETY_KEY"
    ;;
  test)
    pytest_uv "$TEST_DIR"
    ;;
  test_coverage)
    test_print_coverage_uv
    ;;
  test_coverage_check)
    test_coverage_check_uv "$2"
    ;;
  build)
    build_uv
    ;;
  publish)
    publish_pypi_uv "$PYPI_TOKEN"
    ;;
  tag)
    git_tag_and_push_auto_uv
    ;;
  test_collector)
    test_collector
    ;;
  build_docker_image)
    build_docker_image
    ;;
  run_collector)
    run_collector
    ;;
  setup_debian)
    setup_debian
    ;;
  *)
    usage
    ;;
esac

# <=== FOOTER SECTION END  <===
