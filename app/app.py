import os
import time
from flask import Flask, jsonify
import redis

app = Flask(__name__)

REDIS_HOST = os.environ.get("REDIS_HOST", "redis-service")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))

# Short timeouts so a bad host fails fast (useful for the failure-demo section)
r = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    socket_connect_timeout=2,
    socket_timeout=2,
)


@app.route("/")
def index():
    count = r.incr("hits")
    return jsonify({
        "message": "Hello from Fluid AI DevOps challenge by Harsh",
        "hits": count,
        "pod": os.environ.get("HOSTNAME", "unknown"),
    })


@app.route("/health")
def health():
    """
    Liveness/readiness target. Deliberately fails (500) if Redis
    is unreachable, so a bad REDIS_HOST propagates into a probe
    failure -> CrashLoopBackOff. This is what you'll use for the
    intentional-failure section of the video.
    """
    try:
        r.ping()
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"status": "error", "detail": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
