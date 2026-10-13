#!/usr/bin/env bash
# cbrm — BERO HOST management: the customer panel (no API) scripted with curl, and its noVNC console
# bridged with websocat and driven with vncdotool. Glue only; every part is a standard tool.
#
#   cbrm vms                                 VM, product, state, installed system
#   cbrm status  <vm>                        overview of one VM
#   cbrm logs    <vm> [n]                    panel action log, newest first (panel time, Europe/Berlin)
#   cbrm console <vm> <out.png> [--text]     screenshot of the console (--text: also OCR it)
#   cbrm type    <vm> <text> --confirm <vm>  type into the console
#   cbrm key     <vm> <key>... --confirm <vm>  press keys (vncdotool names: enter, ctrl-c, f1, ...)
#   cbrm power   <vm> start|stop|shutdown|restart --confirm <vm>
#
# Only the VMs in CBRM_VMS. Nothing else exists on purpose: no reinstall, root password, network reset,
# backups, ISO/boot order, scheduled tasks, renewals, upgrades or credit. Those stay manual in the panel.
# Every changing command repeats its target (--confirm) and is written to the audit log.
set -euo pipefail

BASE=https://bero-host.de
VMS=${CBRM_VMS:-"17761 17762 17763"}
SECRETS=${CBRM_SECRETS:-$HOME/agents/knowledge/secrets/bero-host.yml}
STATE=${XDG_STATE_HOME:-$HOME/.local/state}/cbrm
JAR=$STATE/cookies
UA="Mozilla/5.0 (X11; Linux x86_64) cbrm"
umask 077
mkdir -p "$STATE"

die() { echo "cbrm: $*" >&2; exit 2; }
audit() { echo "$(date -u +%FT%TZ) $*" >> "$STATE/audit.log"; }
web() { curl -sS --fail -A "$UA" -c "$JAR" -b "$JAR" "$@"; }
text() { htmlq --text --remove-nodes 'script, style' "${1:-body}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e '/^$/d'; }

login() {
  local token
  token=$(web "$BASE/login" | htmlq -a value 'form[action$="/login"] input[name=_token]')
  # The password never appears in an argument list: the form is built on a pipe.
  { printf '_token=%s&email=' "$token"
    sops --decrypt "$SECRETS" | yq -r .panel_user | tr -d '\n' | jq -sRr @uri | tr -d '\n'
    printf '&password='
    sops --decrypt "$SECRETS" | yq -r .panel_password | tr -d '\n' | jq -sRr @uri | tr -d '\n'
  } | web -o /dev/null -X POST -H 'Content-Type: application/x-www-form-urlencoded' --data-binary @- "$BASE/login"
  [[ $(web -o /dev/null -w '%{redirect_url}' "$BASE/customer") != *"/login"* ]] || die "login failed"
}

# GET a panel page, logging in first when the session is gone.
page() {
  [[ $(web -o /dev/null -w '%{redirect_url}' "$BASE/customer") != *"/login"* ]] || login
  web "$BASE$1"
}

product() {  # VM id -> product id, cached
  local vm=$1 pid
  if ! grep -q "^$vm " "$STATE/products" 2>/dev/null; then
    : > "$STATE/products"
    for pid in $(page /customer | grep -o '/customer/products/[0-9]*' | sort -u | cut -d/ -f4); do
      page "/customer/products/$pid" | htmlq --text title | grep -o '#[0-9]* (KVM' | tr -d '#(KVM ' |
        sed "s/\$/ $pid/" >> "$STATE/products"
    done
  fi
  awk -v v="$vm" '$1 == v { print $2 }' "$STATE/products" | grep . || die "VM $vm is not in this account"
}

allowed() { [[ " $VMS " == *" $1 "* ]] || die "VM '$1' is not in CBRM_VMS ($VMS)"; }
confirmed() { [[ ${*: -2:1} == --confirm && ${*: -1} == "$1" ]] || die "repeat the target: ... --confirm $1"; }

status() {
  page "/customer/products/$(product "$1")" | text | awk '
    /^KVM Rootserver #/ { on = 1; print "state: " prev_state; next }
    on && /^(Online|Offline|Gestoppt|Installation)/ && !st { st = 1; print "state: " $0 }
    on && want { print want ": " $0; want = "" }
    on && /^(Hostname|Installiertes System|Haupt IP-Adressen)$/ { want = $0 }
    on && /^Letztes Backup/ { print; exit }' | grep -v '^state: $'
}

logs() {
  local html csrf req
  html=$(page "/customer/products/$(product "$1")")
  csrf=$(htmlq -a content 'meta[name=csrf-token]' <<< "$html")
  # The log is a lazy Livewire component: replay its __lazyLoad call with its own snapshot.
  req=$(paste -d '\n' \
      <(htmlq -a wire:snapshot '[wire\:snapshot][x-intersect]' <<< "$html") \
      <(htmlq -a x-intersect '[wire\:snapshot][x-intersect]' <<< "$html") |
    jq -Rn --arg t "$csrf" '[inputs] as $l | [range(0; $l|length; 2) | {s: $l[.], c: $l[.+1]}]
      | map(select(.s | fromjson | .memo.name | endswith(".logs-table"))) | first
      | {_token: $t, components: [{snapshot: .s, updates: {},
         calls: [{path: "", method: "__lazyLoad", params: [.c | sub("^.*__lazyLoad\\(."; "") | sub(".\\)$"; "")]}]}]}')
  web -H 'Content-Type: application/json' -H 'X-Livewire: true' -H "X-CSRF-TOKEN: $csrf" \
      --data-binary "$req" "$(htmlq -a data-update-uri '[data-update-uri]' <<< "$html" | head -1)" |
    jq -r '.components[0].effects.html' | text |
    awk '/^: [0-9]/ { d = substr($0, 3) } /^Aktion: / { print d " " substr($0, 9) }' | sed 's/ | / /; s/ Uhr / /' | head -n "${2:-20}"
}

# Opens the console's websocket on a local port and runs vncdotool against it.
vnc() {
  local vm=$1 src host port pw lp bridge; shift
  src=$(page "/customer/rootserver/$vm/vnc" | htmlq -a src iframe | head -1)
  host=$(sed -n 's/.*[?&]host=\([^&]*\).*/\1/p' <<< "$src")
  port=$(sed -n 's/.*[?&]port=\([0-9]*\).*/\1/p' <<< "$src")
  pw=$(sed -n 's/.*[?&]password=\([^&]*\).*/\1/p' <<< "$src")
  pw=$(printf '%b' "${pw//%/\\x}")  # URL-decode: a Proxmox VNC ticket (PVEVNC:...)
  [[ -n $host && -n $port && -n $pw ]] || die "no console session offered for $vm"
  lp=$(( 20000 + RANDOM % 20000 ))
  websocat --binary -E "tcp-l:127.0.0.1:$lp" "wss://$host:$port/websockify" & bridge=$!
  trap 'kill "$bridge" 2>/dev/null' RETURN
  sleep 1
  vncdo -s "127.0.0.1::$lp" -p "$pw" "$@"
}

cmd=${1:-}; [[ -n $cmd ]] || { sed -n '2,15s/^# \{0,1\}//p' "$0"; exit 0; }; shift
[[ $cmd == vms ]] || allowed "${1:-}"
case $cmd in
  vms)     for vm in $VMS; do echo "$vm $(product "$vm") $(status "$vm" | sed -n 's/^\(state\|Installiertes System\): //p' | paste -sd' ')"; done ;;
  status)  status "$1" ;;
  logs)    logs "$1" "${2:-20}" ;;
  console) [[ $# -ge 2 ]] || die "usage: cbrm console <vm> <out.png> [--text]"
           vnc "$1" capture "$2"; [[ -s $2 ]] || die "no screenshot written"; echo "$2"
           [[ ${3:-} != --text ]] || tesseract "$2" - 2>/dev/null ;;
  type)    confirmed "$@"; audit "type $1 (${#2} chars)"; vnc "$1" type "$2" ;;
  key)     confirmed "$@"; vm=$1; set -- "${@:2:$#-3}"; audit "key $vm $*"
           args=(); for k in "$@"; do args+=(key "$k"); done; vnc "$vm" "${args[@]}" ;;
  power)   confirmed "$@"; [[ ${2:-} =~ ^(start|stop|shutdown|restart)$ ]] || die "power: start|stop|shutdown|restart"
           page "/customer/products/$(product "$1")" > /dev/null
           audit "power $1 $2 requested"
           r=$(web -H 'X-Requested-With: XMLHttpRequest' -H 'Accept: application/json' "$BASE/customer/rootserver/$1/$2")
           audit "power $1 $2 -> $r"; echo "$r" ;;
  *)       die "unknown command '$cmd'" ;;
esac
