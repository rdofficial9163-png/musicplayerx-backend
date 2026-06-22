"""
Render.com backend for Music PlayerX's Online tab.

Uses yt-dlp + bgutil-ytdlp-pot-provider (script mode) to generate
real YouTube BotGuard PO Tokens per-request, bypassing the
"Sign in to confirm you're not a bot" block that hits plain server IPs.

build.sh clones bgutil and compiles it during Render's build step.
At runtime, yt-dlp's bgutil plugin spawns Node.js to fetch the token.

Endpoint:
    GET /stream?id=<11-char videoId>
    200 -> {"url": "...", "title": "...", "duration": 123}
    502 -> {"error": "..."}
"""

import os
from flask import Flask, request, jsonify
import yt_dlp

app = Flask(__name__)

# Path where build.sh put the compiled bgutil server
BGUTIL_SERVER_HOME = os.path.expanduser('~/bgutil-ytdlp-pot-provider/server')

YDL_OPTS = {
    'format': 'bestaudio[ext=m4a]/bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'noplaylist': True,
    'skip_download': True,
    # mweb client is what yt-dlp officially recommends with PO Token
    'extractor_args': {
        'youtube': {
            'player_client': ['mweb'],
        },
        # Tell bgutil plugin where the compiled server script lives
        'youtubepot-bgutilscript': {
            'server_home': [BGUTIL_SERVER_HOME],
        },
    },
    'http_headers': {
        'User-Agent': (
            'Mozilla/5.0 (Linux; Android 12; Pixel 6) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Mobile Safari/537.36'
        ),
        'Accept-Language': 'en-US,en;q=0.9',
    },
}

# Fallback opts used if mweb+POT still fails (e.g. bgutil Node spawn issue)
YDL_OPTS_FALLBACK = {
    'format': 'bestaudio[ext=m4a]/bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'noplaylist': True,
    'skip_download': True,
    'extractor_args': {
        'youtube': {
            'player_client': ['tv_embedded', 'ios'],
        },
    },
}

BOT_PHRASES = ('sign in to confirm', 'bot', 'please sign in')


def is_bot_error(msg):
    low = msg.lower()
    return any(p in low for p in BOT_PHRASES)


def extract(video_url, opts):
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(video_url, download=False)
        return info


@app.route('/stream')
def stream():
    video_id = request.args.get('id', '').strip()
    if not video_id:
        return jsonify({'error': 'missing id parameter'}), 400
    if len(video_id) != 11:
        return jsonify({'error': 'invalid video id'}), 400

    video_url = 'https://www.youtube.com/watch?v=' + video_id
    info = None
    last_err = 'Extraction failed'

    # Try mweb + bgutil PO Token first
    try:
        info = extract(video_url, YDL_OPTS)
    except yt_dlp.utils.DownloadError as e:
        last_err = str(e)
    except Exception as e:
        last_err = str(e)

    # If that failed, try fallback clients
    if info is None or not info.get('url'):
        try:
            info = extract(video_url, YDL_OPTS_FALLBACK)
        except yt_dlp.utils.DownloadError as e:
            last_err = str(e)
        except Exception as e:
            last_err = str(e)

    if not info or not info.get('url'):
        if is_bot_error(last_err):
            return jsonify({'error': 'YouTube is blocking this server. Try again in a few minutes.'}), 502
        if 'Private video' in last_err:
            return jsonify({'error': 'This video is private'}), 502
        if 'Video unavailable' in last_err:
            return jsonify({'error': 'Video unavailable'}), 502
        if 'age' in last_err.lower():
            return jsonify({'error': 'Age-restricted video'}), 502
        return jsonify({'error': last_err}), 502

    return jsonify({
        'url': info.get('url'),
        'title': info.get('title'),
        'duration': info.get('duration'),
    })


@app.route('/health')
def health():
    bgutil_ok = os.path.isdir(BGUTIL_SERVER_HOME)
    return jsonify({'status': 'ok', 'bgutil_built': bgutil_ok})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
