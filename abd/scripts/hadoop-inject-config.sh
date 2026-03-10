#!/usr/bin/env bash

set -e

# Finds core-site.xml in $HADOOP_HOME and modifies it, adding a xref include of
# auth-keys.xml before the closing </configuration> tag

patch_core_site() {
  local core_site="$HADOOP_HOME/etc/hadoop/core-site.xml"
  if [[ ! -f "$core_site" ]]; then
    echo "Error: $core_site not found"
    exit 1
  fi
  # Check if the patch has already been applied
  if grep -q "<!-- ABD auth-keys include -->" "$core_site"; then
    echo "🔎 Patch already applied to $core_site, skipping."
    return
  fi
  # Create a backup of the original file
  cp "$core_site" "${core_site}.bak"

  # Insert the xref include before the closing </configuration> tag
  awk '/<\/configuration>/ {
    print "  <!-- ABD auth-keys include -->"
    print "  <include xmlns=\"http://www.w3.org/2001/XInclude\" href=\"auth-keys.xml\">"
    print "    <fallback />"
    print "  </include>"
  }1' "${core_site}.bak" > "$core_site"

  echo "✅ Patched $core_site successfully."
}

if [[ -z "$HADOOP_HOME" ]]; then
  echo "Error: HADOOP_HOME environment variable is not set."
  exit 1
fi

patch_core_site

