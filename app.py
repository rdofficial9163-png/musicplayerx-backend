"""
Render.com backend for Music PlayerX's Online tab.
"""

import os
import logging
from flask import Flask, request, jsonify
import yt_dlp

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
BGUTIL_SERVER_HOME = os.path.join(_REPO_ROOT, 'bgutil-ytdlp-pot-provider', 'server')

def make_opts(player_clients, use_bgutil=False):
    youtube_args = {
        'player_client': player_clients,
        'formats': ['missing_pot'],
    }
    opts = {
        'format': 'bestaudio/best',
        'quiet': False,
        'no_warnings': False,
        'noplaylist': True,
        'skip_download': True,
        'extractor_args': {'youtube': youtube_args},
    }
    if use_bgutil:
        opts['extractor_args']['youtubepot-bgutilscript'] = {
            'server_home': [BGUTIL_SERVER_HOME],
        }
    return opts

# Try these clients in order, each independently
STRATEGIES = [
    ('mweb+bgutil',      make_opts(['mweb'],                  use_bgutil=True)),
    ('tv_embedded',      make_opts(['tv_embedded'],            use_bgutil=False)),
    ('ios',              make_opts(['ios'],                    use_bgutil=False)),
    ('android',          make_opts(['android'],                use_bgutil=False)),
    ('web+bgutil',       make_opts(['web'],                    use_bgutil=True)),
    ('mweb_nopot',       make_opts(['mweb'],                   use_bgutil=False)),
]

BOT_PHRASES = ('sign in to confirm', 'not a bot', 'please sign in')

def is_bot_error(msg):
    return any(p in msg.lower() for p in BOT_PHRASES)

def pick_url(info):
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

def try_extract(label, video_url, opts):
    logger.info(f'[{label}] trying extraction')
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            if not info:
                logger.warning(f'[{label}] no info returned')
                return None, None, 'no info returned'
            url = pick_url(info)
            if url:
                logger.info(f'[{label}] SUCCESS, url starts with: {url[:60]}')
                return info, url, None
            logger.warning(f'[{label}] info returned but no url found')
            return None, None, 'no playable url in info'
    except yt_dlp.utils.DownloadError as e:
        logger.warning(f'[{label}] DownloadError: {e}')
        return None, None, str(e)
    except Exception as e:
        logger.warning(f'[{label}] Exception: {e}')
        return None, None, str(e)

@app.route('/stream')
def stream():
    video_id = request.args.get('id', '').strip()
    if not video_id:
        return jsonify({'error': 'missing id parameter'}), 400
    if len(video_id) != 11:
        return jsonify({'error': 'invalid video id'}), 400

    video_url = 'https://www.youtube.com/watch?v=' + video_id
    last_err = None

    for label, opts in STRATEGIES:
        info, url, err = try_extract(label, video_url, opts)
        if info and url:
            return jsonify({
                'url': url,
                'title': info.get('title'),
                'duration': info.get('duration'),
                'client': label,
            })
        last_err = err

    if is_bot_error(last_err or ''):
        return jsonify({'error': 'YouTube is blocking this server. Try again later.'}), 502
    if 'Private video' in (last_err or ''):
        return jsonify({'error': 'This video is private'}), 502
    if 'Video unavailable' in (last_err or ''):
        return jsonify({'error': 'Video unavailable'}), 502
    if 'age' in (last_err or '').lower():
        return jsonify({'error': 'Age-restricted video'}), 502
    return jsonify({'error': last_err or 'All clients failed'}), 502

@app.route('/health')
def health():
    return jsonify({
        'status': 'ok',
        'bgutil_built': os.path.isdir(BGUTIL_SERVER_HOME),
        'bgutil_path': BGUTIL_SERVER_HOME,
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
