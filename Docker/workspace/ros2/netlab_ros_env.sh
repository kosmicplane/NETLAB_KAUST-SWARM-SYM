#!/usr/bin/env bash
# Permission-safe ROS 2 environment loader for NETLAB containers and diagnostics.
# ROS-generated setup scripts reference optional AMENT variables. Nounset is
# disabled only while sourcing those scripts and restored afterwards.

netlab_source_ros_environment() {
  local requested_overlay="${1:-}"
  local had_nounset=0
  case "$-" in
    *u*) had_nounset=1 ;;
  esac
  set +u

  local distro="${ROS_DISTRO:-jazzy}"
  local ros_setup="/opt/ros/${distro}/setup.bash"
  if [[ ! -r "$ros_setup" ]]; then
    printf '[NETLAB-ROS][ERROR] ROS setup file is unavailable: %s\n' "$ros_setup" >&2
    (( had_nounset )) && set -u
    return 1
  fi
  # shellcheck disable=SC1090
  source "$ros_setup"

  if [[ "$requested_overlay" != "--base-only" ]]; then
    local overlay="$requested_overlay"
    [[ -z "$overlay" ]] && overlay="/workspace/ros2/install/setup.bash"
    if [[ -r "$overlay" ]]; then
      # shellcheck disable=SC1090
      source "$overlay"
    elif [[ -n "$requested_overlay" ]]; then
      printf '[NETLAB-ROS][ERROR] Requested workspace overlay is unavailable: %s\n' "$overlay" >&2
      (( had_nounset )) && set -u
      return 1
    fi
  fi

  (( had_nounset )) && set -u
}
