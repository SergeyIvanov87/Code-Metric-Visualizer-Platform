#!/bin/sh
# Install the pinned browser distribution, without npm or runtime network access.
set -eu
destination=${1:?Static asset destination is required}
staging=$(mktemp -d)
trap 'rm -rf "$staging"' EXIT HUP INT TERM
curl --fail --silent --show-error --location --retry 3 \
    https://registry.npmjs.org/json-formatter-js/-/json-formatter-js-2.5.23.tgz \
    -o "$staging/package.tgz"
printf '%s  %s\n' 3bceac96108c4e70888732da088ce930f5f6bd802aad1e38b8739e96806ad4d2 "$staging/package.tgz" | sha256sum -c -
tar -xzf "$staging/package.tgz" -C "$staging"
mkdir -p "$destination"
cp "$staging/package/dist/json-formatter.umd.js" "$staging/package/dist/json-formatter.css" "$staging/package/LICENSE" "$destination/"
