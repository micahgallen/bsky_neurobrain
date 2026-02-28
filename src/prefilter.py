import re

# Inclusion keywords by category — combined into a single OR pattern
_INCLUSION_TERMS = [
    # Neuroscience
    r"neurosci\w*", r"neuron\w*", r"synaps\w*", r"synaptic", r"cortex",
    r"cortical", r"hippocampus", r"hippocampal", r"amygdala", r"prefrontal",
    r"cerebellum", r"dopamine", r"serotonin", r"norepinephrine", r"GABA",
    r"glutamate", r"neuroplasticity", r"axon\w*", r"dendrit\w*", r"glia\w*",
    r"astrocyte\w*", r"microglia", r"myelin", r"fMRI", r"EEG", r"MEG",
    r"neuroimaging", r"brain scan", r"connectome", r"tractography",
    r"optogenetics", r"electrophysiology", r"neurotransmitter\w*",
    r"neuropeptide\w*", r"neural circuit\w*", r"brain region\w*",
    r"thalamus", r"basal ganglia", r"striatum", r"brainstem",
    r"white matter", r"gray matter", r"blood-brain barrier",
    r"brain", r"neuro\w*", r"CNS", r"PNS",
    # Psychology
    r"cognition", r"cognitive", r"perception", r"working memory",
    r"long-term memory", r"episodic memory", r"semantic memory",
    r"procedural memory", r"executive function", r"decision making",
    r"metacognition", r"cognitive load", r"priming", r"implicit memory",
    r"explicit memory", r"cognitive bias", r"heuristic\w*",
    r"psychophysics", r"reaction time", r"signal detection",
    r"mental model\w*", r"schema", r"chunking", r"interference",
    r"encoding", r"retrieval", r"habituation", r"sensitization",
    r"conditioning", r"reinforcement", r"developmental psych\w*",
    r"cognitive development", r"Piaget", r"Vygotsky", r"theory of mind",
    r"false belief", r"joint attention", r"psycholinguistic\w*",
    r"visual perception", r"auditory perception", r"multisensory",
    r"crossmodal",
    # Philosophy of mind
    r"consciousness", r"qualia", r"phenomenal", r"hard problem",
    r"explanatory gap", r"intentionality", r"mental representation",
    r"functionalism", r"dualism", r"physicalism", r"panpsychism",
    r"integrated information", r"global workspace",
    r"higher-order thought", r"neural correlates of consciousness",
    r"NCC", r"free will", r"determinism", r"mental causation",
    r"supervenience", r"emergence", r"philosophy of mind",
    r"phenomenology", r"embodied cognition", r"enactivism",
    r"extended mind", r"predictive processing", r"Bayesian brain",
    r"active inference", r"free energy principle",
    # Linguistics
    r"syntax", r"morphology", r"phonology", r"phonetics", r"semantics",
    r"pragmatics", r"linguistic\w*", r"language acquisition",
    r"universal grammar", r"Chomsky", r"minimalism",
    r"generative grammar", r"neurolinguistic\w*", r"Broca",
    r"Wernicke", r"aphasia", r"dyslexia", r"bilingual\w*",
    r"multilingual\w*", r"speech perception", r"speech production",
    r"prosody", r"discourse", r"language processing", r"garden path",
    r"parsing", r"lexical access", r"word recognition",
    r"sentence processing", r"language comprehension",
    # Cognitive anthropology
    r"cognitive anthropology", r"cultural cognition", r"ethnoscience",
    r"folk taxonomy", r"cognitive ecology", r"distributed cognition",
    r"situated cognition", r"cultural evolution", r"cognitive niche",
    r"cumulative culture", r"social learning", r"imitation",
    r"emulation", r"cultural transmission", r"cognitive archaeology",
    # Methods / General
    r"peer-reviewed", r"preprint", r"study finds",
    r"researchers found", r"meta-analysis", r"replication",
    r"effect size", r"statistical significance", r"p-value",
    r"confidence interval", r"sample size", r"longitudinal",
    r"randomized controlled", r"double-blind", r"neuropsychology",
    r"computational model\w*", r"simulation", r"cognitive science",
    r"cogsci", r"behavioral experiment\w*", r"eye tracking",
    r"pupillometry", r"TMS", r"tDCS", r"lesion study",
    r"case study", r"single-cell recording",
]

_EXCLUSION_TERMS = [
    # Politics
    r"Trump", r"Biden", r"Democrat\w*", r"Republican\w*", r"GOP", r"MAGA",
    r"election", r"vote", r"politician\w*", r"Congress", r"Senate",
    r"legislation", r"partisan", r"liberal", r"conservative",
    r"left-wing", r"right-wing", r"woke", r"anti-woke", r"cancel culture",
    r"culture war", r"immigration policy", r"gun control", r"abortion",
    # Crypto
    r"crypto", r"bitcoin", r"NFT", r"stonks", r"meme stock\w*",
    # Pseudoscience
    r"astrology", r"horoscope", r"zodiac", r"manifesting",
    # Sports
    r"sports score\w*", r"fantasy league\w*", r"game tonight",
]


def _build_pattern(terms):
    """Build a single compiled regex from a list of terms, with word boundaries."""
    joined = "|".join(terms)
    return re.compile(rf"\b(?:{joined})\b", re.IGNORECASE)


_INCLUSION_RE = _build_pattern(_INCLUSION_TERMS)
_EXCLUSION_RE = _build_pattern(_EXCLUSION_TERMS)


def passes_prefilter(text: str) -> bool:
    """Return True if the text contains science keywords and no exclusion keywords."""
    if _EXCLUSION_RE.search(text):
        return False
    if _INCLUSION_RE.search(text):
        return True
    return False
