#!/usr/bin/env bash

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


# ---------- CONSTANTS ----------
export SRC_DIR=${SRC_DIR:-"${this_folder}/src"}
export TEST_DIR=${TEST_DIR:-"${this_folder}/test"}
# -------------------------------
# --- main functions

_pwd=$(pwd)
cd "$this_folder"

result=0


[ ! -d "$this_folder/.venv" ] && python3 -m venv .venv
source ./.venv/bin/activate

which flask >/dev/null 2>&1
result="$?"
[ "$result" -ne "0" ] && pip install flask

flask run -p 8080 &
result="$?"
[ "$result" -ne "0" ] && err "[setup] could not start flask server" && cd "$_pwd" && exit 1

cd "$_pwd"
