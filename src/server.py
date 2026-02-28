from flask import Flask, jsonify, request
from src.config import HOSTNAME, SERVICE_DID, FEED_URI
from src.algos import ALGOS
from src.database import init_db

app = Flask(__name__)

init_db()


@app.route("/.well-known/did.json", methods=["GET"])
def did_json():
    return jsonify(
        {
            "@context": ["https://www.w3.org/ns/did/v1"],
            "id": SERVICE_DID,
            "service": [
                {
                    "id": "#bsky_fg",
                    "type": "BskyFeedGenerator",
                    "serviceEndpoint": f"https://{HOSTNAME}",
                }
            ],
        }
    )


@app.route("/xrpc/app.bsky.feed.describeFeedGenerator", methods=["GET"])
def describe_feed_generator():
    feeds = [{"uri": uri} for uri in ALGOS]
    return jsonify({"did": SERVICE_DID, "feeds": feeds})


@app.route("/xrpc/app.bsky.feed.getFeedSkeleton", methods=["GET"])
def get_feed_skeleton():
    feed = request.args.get("feed")
    if not feed:
        return jsonify({"error": "feed parameter is required"}), 400

    algo = ALGOS.get(feed)
    if algo is None:
        return jsonify({"error": "Unsupported algorithm"}), 400

    cursor = request.args.get("cursor")
    limit = request.args.get("limit", default=50, type=int)
    limit = max(1, min(limit, 100))

    body = algo(cursor, limit)
    return jsonify(body)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
