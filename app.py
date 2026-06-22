"""
Render.com backend for Music PlayerX's Online tab.

This wraps yt-dlp's own Python API -- it does NOT reimplement signature
deciphering or any anti-bot-evasion logic. yt-dlp already does all of that
internally as part of normal extract_info(); this file just calls it and
returns the result in the JSON shape StreamResolver.java on the Android
side expects.

Endpoint contract (matches StreamResolver.RENDER_BASE_URL + "/stream?id="):
    GET /stream?id=<videoId>
    -> 200 {"url": "<playable audio url>", "title": "...", "duration": 123}
    -> 502 {"error": "..."}  if extraction failed for any reason
"""

from flask import Flask, request, jsonify
import yt_dlp

app = Flask(__name__)

YDL_OPTS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'noplaylist': True,
    'skip_download': True,
}


@app.route('/stream')
def stream():
    video_id = request.args.get('id')
    if not video_id:
        return jsonify({'error': 'missing id parameter'}), 400

    video_url = 'https://www.youtube.com/watch?v=' + video_id

    try:
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(video_url, download=False)
    except Exception as e:
        # covers age-restricted/region-blocked/removed videos, rate limiting,
        # and the SABR format issues mentioned in the project notes -- none of
        # these are bugs in this Flask wrapper, they're yt-dlp/YouTube-side
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
