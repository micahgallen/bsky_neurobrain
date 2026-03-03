from src.algos.neurobrain import handler as neurobrain_handler
from src.algos.neurobrain_v2 import handler as neurobrain_v2_handler
from src.config import FEED_URI, NEUROBRAIN_V2_FEED_URI

ALGOS = {
    FEED_URI: neurobrain_handler,
}
if NEUROBRAIN_V2_FEED_URI:
    ALGOS[NEUROBRAIN_V2_FEED_URI] = neurobrain_v2_handler
