from src.algos.neurobrain import handler as neurobrain_handler
from src.algos.signal import handler as signal_handler
from src.algos.intero import handler as intero_handler
from src.config import FEED_URI, SIGNAL_FEED_URI, INTERO_FEED_URI

ALGOS = {
    FEED_URI: neurobrain_handler,
}
if SIGNAL_FEED_URI:
    ALGOS[SIGNAL_FEED_URI] = signal_handler
if INTERO_FEED_URI:
    ALGOS[INTERO_FEED_URI] = intero_handler
