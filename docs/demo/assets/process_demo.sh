#!/bin/bash
# MatchForge Demo Video Processing Script
# Usage: Place your raw clips in this directory, edit the variables below, then run ./process_demo.sh

set -euo pipefail

# === CONFIGURE THESE ===
# List your raw clips in the desired final order (update filenames)
CLIPS=(
  "raw_hero_agent_trace.mp4"      # Beat 2 - the wow shot (lead with this or put early)
  "raw_screenshot_upload.mp4"     # Beat 1
  "raw_report_claims.mp4"         # Beat 3
  "raw_questions.mp4"             # Beat 4
  "raw_share_badge.mp4"           # Beat 5
)

# Target total ~55s. Trim each as needed below.
# Example trims: start time and duration (in seconds or HH:MM:SS)
# Adjust these after watching your raw footage
TRIM_HERO="00:00:02 18"      # start, duration
TRIM_UPLOAD="00:00:01 9"
TRIM_REPORT="00:00:00 11"
TRIM_QUESTIONS="00:00:01 5"
TRIM_SHARE="00:00:03 10"

OUTPUT_DIR="."
FINAL_VIDEO="matchforge-demo-55s.mp4"

# For GIFs (hero especially)
GIF_WIDTH=720
GIF_FPS=10

# === END CONFIG ===

echo "=== Trimming clips ==="
mkdir -p trimmed

trim_clip() {
  local input=$1
  local start=$2
  local dur=$3
  local name=$4
  ffmpeg -y -i "$input" -ss "$start" -t "$dur" -c:v libx264 -preset fast -crf 20 -c:a aac trimmed/"$name" 2>/dev/null
  echo "Trimmed: $name"
}

# You can expand this with actual variables if needed
# For now, manual example - edit as needed or enhance the script

echo "Note: Edit the trim sections and filenames in this script for your actual clips."
echo "Example trim command pattern:"
echo 'ffmpeg -i yourraw.mp4 -ss 00:00:02 -t 18 -c:v libx264 -preset fast -crf 20 trimmed/hero.mp4'

echo ""
echo "Once trimmed, create concat.txt like:"
cat > /tmp/concat-example.txt <<EOF
file 'trimmed/hero_agent.mp4'
file 'trimmed/report.mp4'
...
EOF

echo ""
echo "Then concatenate:"
echo 'ffmpeg -f concat -safe 0 -i /tmp/concat-example.txt -c copy '"$FINAL_VIDEO"

echo ""
echo "Example hero GIF:"
echo 'ffmpeg -i trimmed/hero_agent.mp4 -vf "fps='"$GIF_FPS"',scale='"$GIF_WIDTH"':-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" -loop 0 '"${OUTPUT_DIR}/agent-trace-hero.gif"

echo ""
echo "See VIDEO_GUIDE.md for full details and variations."
echo "Run individual ffmpeg commands for best control."
