#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${SOURCE_DIR:-/opt/awesome-openclaw-skills/categories}"
TARGET_DIR="${TARGET_DIR:-/root/.openclaw/skills}"

if [ ! -d "$SOURCE_DIR" ]; then
  echo "Skill source directory not found: $SOURCE_DIR"
  exit 1
fi

mkdir -p "$TARGET_DIR"
shopt -s nullglob

installed=0
for source_path in "$SOURCE_DIR"/*.md; do
  skill_name="$(basename "$source_path" .md)"
  skill_dir="${TARGET_DIR}/${skill_name}"
  skill_file="${skill_dir}/SKILL.md"
  reference_file="${skill_dir}/REFERENCE.md"
  manifest_file="${TARGET_DIR}/${skill_name}.json"
  skill_title="$(sed -n '1s/^#\s*//p' "$source_path")"

  mkdir -p "$skill_dir"
  cp "$source_path" "$reference_file"

  cat >"$skill_file" <<EOF
---
name: ${skill_name}
description: Browse the ${skill_name//-/ } catalog imported from awesome-openclaw-skills and choose relevant community skills or references for the user's request.
---

# ${skill_title:-$skill_name}

This managed skill mirrors the \`${skill_name}\` category from \`awesome-openclaw-skills\`.

Use this skill to:

1. Scan the bundled category list for relevant community skills.
2. Identify the most relevant tools or workflows for the user's natural-language request.
3. Recommend or install concrete downstream skills as a follow-up when needed.

Read \`REFERENCE.md\` for the full imported category catalog.
EOF

  cat >"$manifest_file" <<EOF
{
  "name": "${skill_name}",
  "enabled": true,
  "source": "awesome-openclaw-skills",
  "type": "category-catalog",
  "skillPath": "${skill_file}",
  "referencePath": "${reference_file}"
}
EOF

  echo "Installed ${skill_name}"
  installed=$((installed + 1))
done

if [ "$installed" -eq 0 ]; then
  echo "No category markdown files were found in ${SOURCE_DIR}"
  exit 1
fi

echo "Installed ${installed} awesome-openclaw-skills catalog wrappers into ${TARGET_DIR}"
