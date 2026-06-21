#!/usr/bin/env bash
# Regenerate the dashboard's tunnel videos + entrance audio from the raw dataset.
# Output -> frontend/public/media/{video,audio}, served by Vite at /media/.
#
# Videos are REUSED across hives (only 3 tunnel recordings exist); each hive gets
# a UNIQUE audio clip (no audio repeats). Mapping lives in src/main.js (MEDIA).
#
# Needs ffmpeg. If you don't have it: `pip install imageio-ffmpeg` then set
#   FF="$(python -c 'import imageio_ffmpeg as f;print(f.get_ffmpeg_exe())')"
set -e
FF="${FF:-ffmpeg}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DS="$ROOT/dataset"
V="$ROOT/frontend/public/media/video"
A="$ROOT/frontend/public/media/audio"
mkdir -p "$V" "$A"

vid(){ "$FF" -y -hide_banner -loglevel error -i "$1" -t 11 -vf "scale=1280:-2" -c:v libx264 -crf 25 -preset veryfast -an -movflags +faststart "$2"
       "$FF" -y -hide_banner -loglevel error -i "$2" -frames:v 1 -q:v 4 "${2%.mp4}.jpg"; echo "video $(basename "$2")"; }
aud(){ "$FF" -y -hide_banner -loglevel error -ss 3 -i "$1" -t 18 -ac 1 -c:a libmp3lame -b:a 96k "$2"; echo "audio $(basename "$2")"; }

# 3 tunnel videos (entrance scanner, ~7680x2350 -> 1280-wide web clip)
vid "$DS/vd2/varroa_free/100_2024-08-22_10-50-30.mkv"     "$V/tunnel_free.mp4"
vid "$DS/vd2/varroa_infested/100_2024-08-21_13-10-53.mkv" "$V/tunnel_inf1.mp4"
vid "$DS/vd2/varroa_infested/101_2024-08-21_13-11-14.mkv" "$V/tunnel_inf2.mp4"

# 7 unique entrance-audio clips (one per fed hive)
aud "$DS/to_bee_or_no_to_bee/CF003 - Active - Day - (214).wav"                       "$A/ent_01.mp3"
aud "$DS/to_bee_or_no_to_bee/CJ001 - Missing Queen - Day -  (100).wav"               "$A/ent_02.mp3"
aud "$DS/to_bee_or_no_to_bee/Hive1_12_06_2018_QueenBee_H1_audio___15_00_00.wav"      "$A/ent_03.mp3"
aud "$DS/to_bee_or_no_to_bee/Hive1_31_05_2018_NO_QueenBee_H1_audio___15_00_00.wav"   "$A/ent_04.mp3"
aud "$DS/to_bee_or_no_to_bee/Hive3_12_07_2017_NO_QueenBee_H3_audio___15_00_00.wav"   "$A/ent_05.mp3"
aud "$DS/to_bee_or_no_to_bee/Hive3_20_07_2017_QueenBee_H3_audio___06_10_00.wav"      "$A/ent_06.mp3"
aud "$DS/urban/audio/beehives_2021/audio_2021_chunk_3/11-08-2021_16h45_HIVE-3629.WAV" "$A/ent_07.mp3"
echo "done."
