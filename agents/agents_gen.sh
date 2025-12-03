#!/bin/bash

# Get latest external skills
gitget https://github.com/anthropics/skills main \
  webapp-testing:webapp-testing \
  document-skills/pdf:pdf

{
  sed '/<!-- skills -->/q' AGENTS.md
  printf "\nRefer relevant SKILL.md under $HOME/code/scripts/agents:\n\n"
  find . -maxdepth 2 -name SKILL.md | sort | xargs -I {} awk '
    /^---$/         { if (++count == 2) exit }
    /^name:/        { name = $2 }
    /^description:/ { sub(/^description: */, ""); desc = $0 }
    END             { if (name && desc) printf "- [%s](%s/SKILL.md): %s\n", name, name, desc }
  ' {}
  printf "\n"
  sed -n '/<!-- \/skills -->/,$p' AGENTS.md
} | sponge AGENTS.md
