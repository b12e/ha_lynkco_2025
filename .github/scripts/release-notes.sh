#!/usr/bin/env bash
# Build the release notes for the next release and print them as markdown.
#
# Change list: the commits since the last final release tag (vYYYY.M.N).
# Pre-release tags such as v2026.11.0-beta1 or v2026.11.1-pr50 are ignored on
# purpose: a beta tag on main once shrank the list to a single entry because
# `git describe` treated it as the previous release.
#
# Breaking changes, rendered in a [!CAUTION] block above the change list, come
# from the description of every merged pull request in the range (squash
# merges keep only the PR title in git, so the description is read with gh)
# and from commit bodies:
#   - a line that starts with "Breaking:" (also "Breaking change:",
#     "BREAKING CHANGE:", bold, in a quote, in a bullet or numbered list);
#     bullet lines directly below it are listed as its details;
#   - a "Breaking change(s)" heading, or that text alone in bold, followed by
#     paragraphs or bullets (each becomes one entry) until the next heading.
# Text inside HTML comments (the PR template is one) is invisible on GitHub
# and is skipped, and so are placeholders such as "Breaking: none".
#
# Usage: release-notes.sh [<since-ref>]
#   <since-ref> overrides the detected last release tag (handy for a dry run).
# Needs git, awk and gh (with a token that can read pull requests; a failure
# to read a description aborts the run, so a release never silently loses its
# caution block). Runs on bash 3.2 as well, so it can be tried on macOS.
set -euo pipefail
export LC_ALL=C  # byte-transparent text handling on every awk
trap 'echo "::error::release-notes.sh failed at line $LINENO" >&2' ERR

path_filter="custom_components/lynkco/"

since="${1:-}"
if [ -z "$since" ]; then
  # Nearest tag reachable from HEAD that looks like a final release: starts
  # with v + digit and contains no "-" (which marks betas and pre-releases).
  since=$(git describe --tags --abbrev=0 --match 'v[0-9]*' --exclude '*-*' 2>/dev/null || true)
fi
if [ -n "$since" ]; then
  range="${since}..HEAD"
else
  range="HEAD"
fi

changes=$(git log "$range" --pretty=format:'- %s (%h)' --invert-grep --grep='^chore(release):' -- "$path_filter")
if [ -z "$changes" ]; then
  changes="- Minor changes"
fi

# Turn a stream of texts (commit bodies and PR descriptions, each introduced
# by a line holding only the byte 0x1e) into one breaking-change entry per
# line; a detail of the entry above starts with two spaces and a dash.
breaking_lines() {
  awk '
    function flush() { if (entry != "") print entry; entry = "" }
    function strip_comments(s,    out, i, j) {
      out = ""
      while (1) {
        if (!incomment) {
          i = index(s, "<!--")
          if (i == 0) { out = out s; break }
          out = out substr(s, 1, i - 1)
          s = substr(s, i + 4)
          incomment = 1
        } else {
          j = index(s, "-->")
          if (j == 0) break
          s = substr(s, j + 3)
          incomment = 0
        }
      }
      return out
    }
    function is_bullet(s) { return s ~ /^[ \t]*([-*+]|[0-9]+[.)])[ \t]+/ }
    function strip_markers(s) {
      sub(/^[ \t]*(>[ \t]*)*/, "", s)             # blockquote, any depth
      sub(/^([-*+]|[0-9]+[.)])[ \t]+/, "", s)      # bullet or numbered item
      sub(/^\[[ xX]\][ \t]+/, "", s)              # task list box
      sub(/^[*_`]+/, "", s)                       # emphasis opener
      return s
    }
    $0 == "\036" { flush(); incomment = 0; insection = 0; nested = 0; next }
    {
      raw = strip_comments($0)
      sub(/\r$/, "", raw)
      quoted = raw
      sub(/^[ \t]*(>[ \t]*)*/, "", quoted)        # raw without the quote markers
      line = strip_markers(raw)
      low = tolower(line)

      # "Breaking:" line, in any of the tolerated markdown forms
      if (low ~ /^breaking([ -]changes?)?[*_`]*[ \t]*:/) {
        flush()
        nested = 0
        text = substr(line, index(line, ":") + 1)
        sub(/^[*_`]+/, "", text)
        gsub(/^[ \t]+|[ \t]+$/, "", text)
        if (text == "") { insection = 1; next }  # "Breaking changes:" header, entries follow
        if (tolower(text) ~ /^(none|no|nope|n\/a|nothing|-|no breaking changes?)[.!]?$/) next
        print text
        nested = 1
        next
      }
      # bullets directly below a "Breaking:" line are its details
      if (nested) {
        if (is_bullet(quoted)) { print "  - " line; next }
        nested = 0
      }
      # a "Breaking change(s)" heading or standalone bold line opens a section
      if (low ~ /^(#+[ \t]*)?breaking( changes?)?[*_`]*[ \t]*:?[*_`]*[ \t]*$/) { flush(); insection = 1; next }
      if (insection) {
        if (quoted ~ /^#/) { flush(); insection = 0 }             # next heading ends it
        else if (quoted ~ /^[ \t]*$/) { flush() }                 # blank line ends a paragraph
        else if (is_bullet(quoted)) { flush(); entry = line }     # each bullet is an entry
        else { entry = (entry == "" ? line : entry " " line) }    # paragraph lines join
      }
    }
    END { flush() }'
}

# Print the description of every pull request referenced by a "(#123)" in a
# subject of the range, each introduced by a separator line. An issue number
# in a subject is skipped; any other gh failure aborts the whole run.
pr_descriptions() {
  local prs pr err body
  prs=$(git log "$range" --format='%s' | grep -oE '\(#[0-9]+\)' | tr -d '(#)' | awk '!seen[$0]++' || true)
  [ -n "$prs" ] || return 0
  if ! command -v gh >/dev/null 2>&1; then
    if [ -n "${GITHUB_ACTIONS:-}" ]; then
      echo "::error::gh is required to read the pull request descriptions" >&2
      return 1
    fi
    echo "warning: gh not found, pull request descriptions are not scanned" >&2
    return 0
  fi
  err=$(mktemp)
  for pr in $prs; do
    if body=$(gh pr view "$pr" --json body --jq .body 2>"$err"); then
      printf '\036\n%s\n' "$body"
    elif grep -q 'Could not resolve to a PullRequest' "$err"; then
      :  # "(#33)" in a subject was an issue, not a pull request
    else
      printf '::error::could not read the description of #%s: %s\n' "$pr" "$(cat "$err")" >&2
      rm -f "$err"
      return 1
    fi
  done
  rm -f "$err"
}

breaking=$(
  { git log "$range" --format='%x1e%n%B'; pr_descriptions; } | breaking_lines
)
breaking=$(printf '%s\n' "$breaking" | awk 'NF && !seen[$0]++')

if [ -n "$breaking" ]; then
  printf '> [!CAUTION]\n> This release contains breaking changes:\n>\n'
  printf '%s\n' "$breaking" | awk '/^  - / { print "> " $0; next } { print "> - " $0 }'
  printf '\n'
fi
printf "# What's new:\n%s\n" "$changes"
