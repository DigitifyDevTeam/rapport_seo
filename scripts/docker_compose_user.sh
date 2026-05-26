# shellcheck shell=bash
# Source from other scripts:  source "$(dirname "$0")/docker_compose_user.sh"
# Docker runs as the host user so outputs/ stays writable over SFTP.

docker_host_uid() { id -u; }
docker_host_gid() { id -g; }
docker_host_user() { echo "$(docker_host_uid):$(docker_host_gid)"; }

# Args to append after "docker compose run --rm"
DOCKER_RUN_USER_ARGS=(--user "$(docker_host_user)")
