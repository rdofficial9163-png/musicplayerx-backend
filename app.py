"""
Render.com backend for Music PlayerX's Online tab.

Tries multiple yt-dlp player clients in order to work around YouTube's
bot-check. tv_embedded is tried first; if it fails with the bot/sign-in
error, falls back to ios, then web_creator.
"""

from flask import Flask, request, jsonify
import yt_dlp

app = Flask(__name__)

# Client order: tv_embedded first (no bot-check), ios as fallback (also usually clean),
# web_creator last (standard but most likely to trigger bot-check from server IPs).
PLAYER_CLIENTS = ['tv_embedded', 'ios', 'web_creator']

BASE_OPTS = {
    'format': 'bestaudio[ext=m4a]/bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'noplaylist': True,
    'skip_download': True,
    'http_headers': {
        'User-Agent': (
            'Mozilla/5.0 (Linux; Android 12; Pixel 6) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Mobile Safari/537.36'
        ),
        'Accept-Language': 'en-US,en;q=0.9',
    },
}

BOT_PHRASES = ('Sign in to confirm', 'bot', 'confirm your age', 'please sign in')


def is_bot_error(msg):
    msg_lower = msg.lower()
    return any(p.lower() in msg_lower for p in BOT_PHRASES)


def try_extract(video_url):
    """Try each player client in order, return (info, None) or (None, error_str)."""
    last_err = 'Unknown error'
    for client in PLAYER_CLIENTS:
        opts = dict(BASE_OPTS)
        opts['extractor_args'] = {'youtube': {'player_client': [client]}}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                if info and info.get('url'):
                    return info, None
                last_err = 'yt-dlp returned no playable url'
        except yt_dlp.utils.DownloadError as e:
            last_err = str(e)
            if is_bot_error(last_err):
                # Bot check hit this client -- try next
                continue
            # Non-bot error (private, unavailable, etc.) -- no point retrying other clients
            return None, last_err
        except Exception as e:
            last_err = str(e)
    return None, last_err


@app.route('/stream')
def stream():
    video_id = request.args.get('id')
    if not video_id:
        return jsonify({'error': 'missing id parameter'}), 400
    if len(video_id) != 11:
        return jsonify({'error': 'invalid video id'}), 400

    video_url = 'https://www.youtube.com/watch?v=' + video_id
    info, err = try_extract(video_url)

    if info is None:
        if err and is_bot_error(err):
            return jsonify({'error': 'YouTube is blocking this server. Try again in a few minutes.'}), 502
        if err and 'Private video' in err:
            return jsonify({'error': 'This video is private'}), 502
        if err and 'Video unavailable' in err:
            return jsonify({'error': 'Video unavailable'}), 502
        if err and 'age' in err.lower():
            return jsonify({'error': 'Age-restricted video'}), 502
        return jsonify({'error': err or 'Extraction failed'}), 502

    return jsonify({
        'url': info.get('url'),
        'title': info.get('title'),
        'duration': info.get('duration'),
    })


@app.route('/health')
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
