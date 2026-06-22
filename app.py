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


def pick_url(info):
    """
    Extract the best playable URL from yt-dlp's info dict.

    yt-dlp with skip_download=True does NOT always set a top-level 'url'.
    The selected format(s) live in info['requested_formats'] (list, when
    video+audio were merged) or info['url'] (single format).  We prefer
    the audio stream from requested_formats, then fall back to the
    top-level url, then scan all formats for an audio-only stream.
    """
    # Case 1: single selected format with direct url
    if info.get('url'):
        return info['url']

    # Case 2: multiple selected formats (e.g. video+audio merge attempt)
    requested = info.get('requested_formats') or []
    for fmt in requested:
        if fmt.get('url') and fmt.get('vcodec') == 'none':
            return fmt['url']   # audio-only format
    for fmt in requested:
        if fmt.get('url'):
            return fmt['url']   # any format

    # Case 3: scan full format list for best audio-only with a url
    formats = info.get('formats') or []
    audio_fmts = [f for f in formats if f.get('url') and f.get('vcodec') == 'none']
    if audio_fmts:
        # highest abr wins
        audio_fmts.sort(key=lambda f: f.get('abr') or 0, reverse=True)
        return audio_fmts[0]['url']

    # Case 4: any format with a url at all
    for fmt in formats:
        if fmt.get('url'):
            return fmt['url']

    return None


def try_extract(video_url, opts):
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            if not info:
                return None, 'no info returned'
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

    # Try mweb + POT first
    info, url, err = try_extract(video_url, YDL_OPTS_MWEB)

    # Fall back to tv_embedded/ios if mweb failed
    if not info or not url:
        info, url, err2 = try_extract(video_url, YDL_OPTS_FALLBACK)
        if err2:
            err = err2  # surface the most recent error

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
    return jsonify({
        'status': 'ok',
        'bgutil_built': os.path.isdir(BGUTIL_SERVER_HOME),
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
