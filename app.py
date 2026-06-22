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

# build.sh clones bgutil into $PWD/bgutil-ytdlp-pot-provider/server
# On Render, PWD during build = /opt/render/project/src (the repo root)
# At runtime, the working dir is also the repo root, so this resolves correctly.
_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
BGUTIL_SERVER_HOME = os.path.join(_REPO_ROOT, 'bgutil-ytdlp-pot-provider', 'server')

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


def pick_url(info):
    """
    Extract the best playable URL from yt-dlp's info dict.
    skip_download=True does NOT always set a top-level 'url'.
    """
    if info.get('url'):
        return info['url']

    requested = info.get('requested_formats') or []
    for fmt in requested:
        if fmt.get('url') and fmt.get('vcodec') == 'none':
            return fmt['url']
    for fmt in requested:
        if fmt.get('url'):
            return fmt['url']

    formats = info.get('formats') or []
    audio_fmts = [f for f in formats if f.get('url') and f.get('vcodec') == 'none']
    if audio_fmts:
        audio_fmts.sort(key=lambda f: f.get('abr') or 0, reverse=True)
        return audio_fmts[0]['url']

    for fmt in formats:
        if fmt.get('url'):
            return fmt['url']

    return None


def try_extract(video_url, opts):
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            if not info:
                return None, None, 'no info returned'
            url = pick_url(info)
            if url:
                return info, url, None
            return None, None, 'no playable url found in extracted info'
    except yt_dlp.utils.DownloadError as e:
        return None, None, str(e)
    except Exception as e:
        return None, None, str(e)


@app.route('/stream')
def stream():
    video_id = request.args.get('id', '').strip()
    if not video_id:
        return jsonify({'error': 'missing id parameter'}), 400
    if len(video_id) != 11:
        return jsonify({'error': 'invalid video id'}), 400

    video_url = 'https://www.youtube.com/watch?v=' + video_id

    info, url, err = try_extract(video_url, YDL_OPTS_MWEB)

    if not info or not url:
        info, url, err2 = try_extract(video_url, YDL_OPTS_FALLBACK)
        if err2:
            err = err2

    if not info or not url:
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
        'url': url,
        'title': info.get('title'),
        'duration': info.get('duration'),
    })


@app.route('/health')
def health():
    bgutil_ok = os.path.isdir(BGUTIL_SERVER_HOME)
    return jsonify({
        'status': 'ok',
        'bgutil_built': bgutil_ok,
        'bgutil_path': BGUTIL_SERVER_HOME,   # shows exact path being checked
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
