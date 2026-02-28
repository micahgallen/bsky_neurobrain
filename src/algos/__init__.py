from src.algos.neurobrain import handler as neurobrain_handler
from src.config import FEED_URI

ALGOS = {
    FEED_URI: neurobrain_handler,
}
