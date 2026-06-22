"""
Render.com backend for Music PlayerX's Online tab.

Uses yt-dlp + bgutil-ytdlp-pot-provider (script mode) to generate
real YouTube BotGuard PO Tokens, bypassing bot-check on server IPs.

mweb client provides HLS streams -- format selector must not restrict
to m4a/webm since mweb only has m3u8. ExoPlayer handles HLS fine.
"""

import os
from flask import Flask, request, jsonify
import yt_dlp

app = Flask(__name__)

BGUTIL_SERVER_HOME = os.path.expanduser('~/bgutil-ytdlp-pot-provider/server')

# mweb + bgutil POT -- primary path
YDL_OPTS_MWEB = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'noplaylist': True,
    'skip_download': True,
    'extractor_args': {
        'youtube': {
            'player_client': ['mweb'],
            # Allow formats even if POT wasn't attached (bgutil handles it)
            'formats': ['missing_pot'],
        },
        'youtubepot-bgutilscript': {
            'server_home': [BGUTIL_SERVER_HOME],
        },
    },
}

# Fallback: tv_embedded then ios -- no POT needed, may still work
YDL_OPTS_FALLBACK = {
    'format': 'bestaudio/best',
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

BOT_PHRASES = ('sign in to confirm', 'not a bot', 'please sign in')


def is_bot_error(msg):
    return any(p in msg.lower() for p in BOT_PHRASES)


def try_extract(video_url, opts):
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            if info and info.get('url'):
                return info, None
            return None, 'no playable url returned'
    except yt_dlp.utils.DownloadError as e:
        return None, str(e)
    except Exception as e:
        return None, str(e)


@app.route('/stream')
def stream():
    video_id = request.args.get('id', '').strip()
    if not video_id:
        return jsonify({'error': 'missing id parameter'}), 400
    if len(video_id) != 11:
        return jsonify({'error': 'invalid video id'}), 400

    video_url = 'https://www.youtube.com/watch?v=' + video_id

    # Try mweb + POT first
    info, err = try_extract(video_url, YDL_OPTS_MWEB)

    # Fall back to tv_embedded/ios if mweb failed
    if not info:
        info, err2 = try_extract(video_url, YDL_OPTS_FALLBACK)
        if err2:
            err = err2  # surface the most recent error

    if not info:
        if is_bot_error(err or ''):
            return jsonify({'error': 'YouTube is blocking this server. Try again in a few minutes.'}), 502
        if 'Private video' in (err or ''):
            return jsonify({'error': 'This video is private'}), 502
        if 'Video unavailable' in (err or ''):
            return jsonify({'error': 'Video unavailable'}), 502
        if 'age' in (err or '').lower():
            return jsonify({'error': 'Age-restricted video'}), 502
        return jsonify({'error': err or 'Extraction failed'}), 502

    return jsonify({
        'url': info.get('url'),
        'title': info.get('title'),
        'duration': info.get('duration'),
    })


@app.route('/health')
def health():
    return jsonify({
        'status': 'ok',
        'bgutil_built': os.path.isdir(BGUTIL_SERVER_HOME),
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
