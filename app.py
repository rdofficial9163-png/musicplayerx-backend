"""
Render.com backend for Music PlayerX's Online tab.

Wraps yt-dlp's Python API. Uses the TV_EMBED client (extractor_args) to avoid
YouTube's "Sign in to confirm you're not a bot" challenge, which hits the
default WEB client on server IPs. tv_embedded is an OAuth-authenticated client
that yt-dlp supports natively and which bypasses the bot-check wall without
requiring real browser cookies.

Endpoint contract:
    GET /stream?id=<videoId>
    -> 200 {"url": "...", "title": "...", "duration": 123}
    -> 502 {"error": "..."}
"""

from flask import Flask, request, jsonify
import yt_dlp

app = Flask(__name__)

# tv_embedded client avoids the "Sign in to confirm you're not a bot" error
# that hits the default WEB client from server IPs. yt-dlp handles the
# OAuth flow for tv_embedded automatically -- no cookies needed.
YDL_OPTS = {
    'format': 'bestaudio[ext=m4a]/bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'noplaylist': True,
    'skip_download': True,
    # Use tv_embedded client -- bypasses bot-check without cookies
    'extractor_args': {
        'youtube': {
            'player_client': ['tv_embedded'],
        }
    },
    # Spoof a real browser UA so the CDN stream URLs don't get rejected
    'http_headers': {
        'User-Agent': (
            'Mozilla/5.0 (Linux; Android 12; Pixel 6) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Mobile Safari/537.36'
        ),
        'Accept-Language': 'en-US,en;q=0.9',
    },
}


@app.route('/stream')
def stream():
    video_id = request.args.get('id')
    if not video_id:
        return jsonify({'error': 'missing id parameter'}), 400

    # Reject obviously invalid IDs early so yt-dlp doesn't waste a network
    # round-trip just to fail. YouTube video IDs are always 11 characters.
    if len(video_id) != 11:
        return jsonify({'error': 'invalid video id'}), 400

    video_url = 'https://www.youtube.com/watch?v=' + video_id

    try:
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(video_url, download=False)
    except yt_dlp.utils.DownloadError as e:
        err = str(e)
        # Surface a friendlier message for the common bot-check failure
        # (should no longer happen with tv_embedded, but kept as a safety net)
        if 'Sign in to confirm' in err or 'bot' in err.lower():
            return jsonify({
                'error': 'YouTube is temporarily blocking this server. Try again in a few minutes.'
            }), 502
        if 'Private video' in err:
            return jsonify({'error': 'This video is private'}), 502
        if 'Video unavailable' in err:
            return jsonify({'error': 'Video unavailable'}), 502
        if 'age' in err.lower():
            return jsonify({'error': 'Age-restricted video'}), 502
        return jsonify({'error': err}), 502
    except Exception as e:
        return jsonify({'error': str(e)}), 502

    stream_url = info.get('url')
    if not stream_url:
        return jsonify({'error': 'yt-dlp returned no playable url for this video'}), 502

    return jsonify({
        'url': stream_url,
        'title': info.get('title'),
        'duration': info.get('duration'),
    })


@app.route('/health')
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
