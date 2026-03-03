import re
import unicodedata

# All keyword terms — a single match passes. We have massive classifier
# headroom (~6 posts/sec capacity, currently using ~0.07/sec) so the
# prefilter's job is just to cut obvious noise, not be precise.
_KEYWORDS = [
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
    r"white matter", r"gray matter", r"grey matter", r"blood-brain barrier",
    r"neuro\w*", r"CNS", r"PNS",
    # Psychology
    r"cognition", r"cognitive", r"perception", r"working memory",
    r"long-term memory", r"episodic memory", r"semantic memory",
    r"procedural memory", r"executive function", r"decision.making",
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
    r"higher.order thought", r"neural correlates of consciousness",
    r"NCC", r"determinism", r"mental causation",
    r"supervenience", r"philosophy of mind",
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
    r"peer.reviewed", r"preprint", r"study finds",
    r"researchers found", r"meta.analysis", r"replication",
    r"effect size", r"statistical significance", r"p.value",
    r"confidence interval", r"sample size", r"longitudinal",
    r"randomized controlled", r"double.blind", r"neuropsychology",
    r"computational model\w*", r"simulation", r"cognitive science",
    r"cogsci", r"behavioral experiment\w*", r"eye.tracking",
    r"pupillometry", r"TMS", r"tDCS", r"lesion study",
    r"case study", r"single.cell recording",
    # Broad terms — previously required 2+ matches, now single match
    # since we have 90x classifier headroom
    r"brain", r"brains",
    r"memory", r"memories",
    r"attention",
    r"learning",
    r"psychology", r"psychologist\w*",
    r"mental health", r"psychiatric",
    r"neurodivergent", r"ADHD", r"autism", r"autistic",
    r"sleep", r"dreams?", r"circadian",
    r"stress", r"trauma", r"PTSD",
    r"empathy", r"emotion\w*", r"motivation",
    r"intelligence", r"IQ", r"reasoning",
    r"anxiety", r"depression",
    r"mindful\w*",
    r"behavior\w*", r"behaviour\w*",
    # Research signals
    r"study shows", r"research shows", r"research finds",
    r"scientists found", r"scientists say",
    r"new study", r"new research", r"according to research",
    r"new paper", r"paper finds", r"paper shows",
    r"published in", r"journal of",
    r"et al\b", r"doi:", r"arxiv",
    # Neuroscience terms that the originals missed
    r"sensory", r"motor cortex", r"visual cortex",
    r"auditory cortex", r"somatosensory",
    r"prefrontal cortex", r"parietal", r"temporal lobe",
    r"occipital", r"frontal lobe", r"cingulate",
    r"insula", r"hypothalamus", r"cerebral",
    r"subcortical", r"cortical",
    r"lateralization", r"hemispher\w*",
    r"receptor\w*", r"agonist", r"antagonist",
    r"excitatory", r"inhibitory",
    r"plasticity", r"potentiation", r"LTP", r"LTD",
    r"oscillation\w*", r"gamma", r"theta", r"alpha waves?",
    r"spike\w*", r"firing rate",
    r"representation\w*", r"topograph\w*",
    r"dynamical system\w*", r"attractor",
    r"recurrent network", r"neural network",
    r"gene expression", r"epigenetic\w*",
    r"optogenetic\w*", r"chemogenetic\w*",
    r"tract.tracing", r"calcium imaging",
    r"patch.clamp", r"electrocorticogra\w*", r"ECoG",
    r"two.photon", r"in vivo", r"in vitro",
    r"place cell\w*", r"grid cell\w*", r"head direction",
    r"spatial navigation", r"cognitive map\w*",
    r"reward", r"punishment", r"operant",
    r"classical conditioning", r"Pavlov\w*",
    r"stimulus", r"stimuli", r"response",
    # Psychology / cogsci terms
    r"psycholog\w*", r"cogniti\w*",
    r"percept\w*", r"illusion\w*",
    r"attentional", r"selective attention",
    r"inhibition", r"cognitive control",
    r"task.switching", r"set.shifting",
    r"mind wander\w*", r"default mode",
    r"resting.state", r"functional connectivity",
    r"structural connectivity",
    r"affect\w*", r"valence", r"arousal",
    r"appraisal", r"interoception",
    r"proprioception", r"nociception",
    r"mental rotation", r"spatial reasoning",
    r"analogical reasoning", r"causal reasoning",
    r"counterfactual", r"theory.theory",
    r"simulation theory", r"mirror neuron\w*",
    r"mentaliz\w*", r"empathiz\w*",
    r"attachment theory", r"developmental",
    r"critical period", r"sensitive period",
    r"brain develop\w*",
    r"aging", r"ageing", r"neurodegenerat\w*",
    r"Alzheimer\w*", r"Parkinson\w*", r"dementia",
    r"concussion", r"TBI", r"brain injury",
    r"stroke", r"lesion",
    r"disorder", r"syndrome",
    r"biomarker\w*", r"endophenotype\w*",
    r"heritab\w*", r"twin stud\w*",
    r"genome.wide", r"GWAS", r"polygenic",
    # --- Cognitive Atlas (918 concepts, multi-word terms not already covered) ---
    # Source: https://www.cognitiveatlas.org/concepts/a/
    # Poldrack RA, et al. (2011). The Cognitive Atlas: Towards a knowledge
    # foundation for cognitive neuroscience. Front. Neuroinform. 5:17.
    # doi: 10.3389/fninf.2011.00017
    r"abstract analogy", r"abstract knowledge",
    r"acoustic coding", r"acoustic phonetic processing", r"acoustic processing",
    r"action initiation", r"activation level",
    r"active maintenance", r"active recall", r"adaptive control",
    r"analogical inference", r"analogical problem solving", r"analogical transfer",
    r"animacy decision", r"animacy perception",
    r"apparent motion", r"arithmetic processing",
    r"articulatory loop", r"articulatory planning", r"articulatory rehearsal",
    r"auditory coding", r"auditory feedback", r"auditory grouping",
    r"auditory imagery", r"auditory localization", r"auditory masking",
    r"auditory recognition", r"auditory scene", r"auditory scene analysis",
    r"auditory sentence comprehension", r"auditory stream segregation",
    r"auditory tone detection", r"auditory tone discrimination",
    r"auditory word comprehension",
    r"autobiographical recall", r"aversive salience",
    r"binocular convergence", r"binocular disparity", r"binocular rivalry",
    r"binocular vision", r"biological motion",
    r"body orientation", r"body representation", r"border ownership",
    r"capacity limitation",
    r"categorical clustering", r"categorical knowledge", r"categorical perception",
    r"category based induction", r"category learning",
    r"causal inference", r"central coherence", r"central executive",
    r"change blindness", r"chromatic contrast",
    r"color constancy", r"color perception", r"color recognition",
    r"conceptual category", r"conceptual coherence", r"conceptual combination",
    r"conceptual metaphor", r"conceptual planning", r"conceptual priming",
    r"concept learning",
    r"confidence judgment", r"conflict adaptation", r"conflict detection",
    r"conjunction search", r"constituent structure",
    r"context memory", r"context representation", r"contextual knowledge",
    r"contingency learning", r"convergent thinking",
    r"covert attention", r"creative cognition", r"creative problem solving",
    r"creative thinking", r"cue dependent forgetting",
    r"decay of activation", r"decision certainty", r"decision uncertainty",
    r"declarative knowledge", r"declarative rule",
    r"deductive inference", r"deductive reasoning",
    r"deep processing", r"deep structure",
    r"delay discounting", r"depth perception",
    r"distributed coding", r"divergent thinking", r"divided attention",
    r"domain specificity", r"dominant percept",
    r"echoic memory", r"economic value processing",
    r"effortful processing", r"elaborative processing", r"elaborative rehearsal",
    r"emotion perception", r"emotion recognition", r"emotion regulation",
    r"emotional decision making", r"emotional enhancement",
    r"emotional expression", r"emotional intelligence",
    r"emotional memory", r"emotional reappraisal",
    r"episodic buffer", r"episodic future thinking",
    r"episodic learning", r"episodic planning", r"episodic simulation",
    r"error detection", r"error signal",
    r"exogenous attention", r"explicit knowledge", r"explicit learning",
    r"face perception", r"face recognition",
    r"facial expression", r"facial recognition",
    r"false memory", r"feature comparison", r"feature detection",
    r"feature extraction", r"feature integration", r"feature search",
    r"feature.based attention", r"feedback processing",
    r"figure ground segregation",
    r"flicker fusion", r"fluid intelligence", r"focused attention",
    r"form perception", r"functional fixedness",
    r"gestalt grouping", r"global precedence",
    r"goal formation", r"goal maintenance", r"goal management",
    r"grammatical encoding", r"gustatory perception",
    r"habit learning", r"habit memory",
    r"iconic memory", r"imagined pain",
    r"implicit knowledge", r"implicit learning",
    r"impulsivity", r"inattentional blindness",
    r"incentive salience", r"incidental learning",
    r"inductive reasoning", r"inhibition of return",
    r"instrumental conditioning", r"instrumental learning",
    r"intentional forgetting", r"intentional learning",
    r"interference control", r"interference resolution",
    r"internal speech", r"interoceptive awareness",
    r"intertemporal choice", r"intrinsic motivation",
    r"involuntary attention",
    r"language production", r"lateral masking",
    r"lexical ambiguity", r"lexical processing", r"lexical retrieval",
    r"loss anticipation", r"loss aversion",
    r"mental arithmetic", r"mental imagery",
    r"metacognitive skill", r"metamemory",
    r"memory acquisition", r"memory consolidation", r"memory decay",
    r"memory retrieval", r"memory storage", r"memory trace",
    r"morphological processing",
    r"motion aftereffect", r"motion detection",
    r"motivational salience",
    r"motor control", r"motor learning", r"motor planning",
    r"motor program", r"motor sequence learning",
    r"multisensory integration", r"multistable perception",
    r"music cognition", r"music perception",
    r"narrative comprehension",
    r"negative priming", r"nondeclarative memory",
    r"novelty detection", r"numerical cognition", r"numerical comparison",
    r"object categorization", r"object perception", r"object recognition",
    r"object.based attention", r"oddball detection",
    r"olfactory perception", r"optical illusion",
    r"overt attention",
    r"pain habituation", r"pain sensitization",
    r"pavlovian conditioning",
    r"perceptual binding", r"perceptual categorization",
    r"perceptual fluency", r"perceptual learning", r"perceptual priming",
    r"performance monitoring",
    r"phonological awareness", r"phonological buffer",
    r"phonological encoding", r"phonological loop",
    r"phonological processing", r"phonological retrieval",
    r"phonological working memory",
    r"pitch discrimination", r"pitch perception",
    r"positive priming", r"pragmatic inference", r"pragmatic reasoning",
    r"preattentive processing", r"preconscious perception",
    r"proactive control", r"proactive interference",
    r"problem solving", r"procedural knowledge", r"procedural learning",
    r"processing capacity", r"processing speed",
    r"prospective memory", r"prospective planning",
    r"psychological refractory period",
    r"punishment processing",
    r"reactive control",
    r"reinforcement learning", r"relational learning",
    r"remote memory", r"repetition priming", r"repressed memory",
    r"response conflict", r"response inhibition", r"response selection",
    r"retroactive interference",
    r"reward anticipation", r"reward learning",
    r"reward processing", r"reward valuation",
    r"saccadic eye movement",
    r"selective control", r"self control", r"self monitoring",
    r"semantic categorization", r"semantic knowledge",
    r"semantic network", r"semantic processing",
    r"semantic working memory",
    r"sensory defensiveness", r"sensory memory",
    r"sentence comprehension", r"sentence production", r"sentence recognition",
    r"sequence learning", r"serial processing",
    r"set shifting", r"shape recognition",
    r"short.term memory", r"skill acquisition",
    r"social cognition", r"social inference", r"social intelligence",
    r"social motivation", r"social norm processing",
    r"somatosensation", r"source memory", r"source monitoring",
    r"spatial ability", r"spatial attention", r"spatial cognition",
    r"spatial localization", r"spatial memory",
    r"spatial selective attention", r"spatial working memory",
    r"speech processing",
    r"spontaneous recovery", r"spreading activation",
    r"subliminal perception",
    r"sustained attention",
    r"syntactic parsing", r"syntactic processing",
    r"tactile working memory", r"task difficulty", r"task set",
    r"task switching", r"taste aversion",
    r"temporal cognition", r"temporal discrimination",
    r"text comprehension", r"text processing",
    r"time perception",
    r"top down processing",
    r"unconscious perception", r"unconscious process",
    r"understanding mental states",
    r"verbal fluency", r"verbal memory",
    r"vestibular control",
    r"visual acuity", r"visual attention", r"visual awareness",
    r"visual body recognition", r"visual face recognition",
    r"visual form discrimination", r"visual form recognition",
    r"visual imagery", r"visual localization", r"visual masking",
    r"visual memory", r"visual object detection", r"visual object recognition",
    r"visual pattern recognition", r"visual recognition",
    r"visual scene perception", r"visual search",
    r"visual sentence comprehension",
    r"visual shape recognition", r"visual word recognition",
    r"visual working memory", r"visuospatial sketch pad",
    r"voice perception",
    r"word comprehension", r"word generation",
    r"working memory maintenance", r"working memory updating",
]

_EXCLUSION_TERMS = [
    # Politics
    r"Trump", r"Biden", r"Democrat\w*", r"Republican\w*", r"GOP", r"MAGA",
    r"election", r"vote", r"politician\w*", r"Congress", r"Senate",
    r"legislation", r"partisan", r"liberal", r"conservative",
    r"left-wing", r"right-wing", r"woke", r"anti-woke", r"cancel culture",
    r"culture war", r"immigration policy", r"gun control", r"abortion",
    # Geopolitics / conflict
    r"Israel\w*", r"Palestin\w*", r"Hamas", r"Hezbollah", r"Gaza",
    r"West Bank", r"Zionist\w*", r"antisemit\w*", r"IDF",
    r"Iran\w*", r"NATO", r"Ukraine", r"Russia\w*", r"Putin",
    r"genocide", r"apartheid", r"colony", r"coloniz\w*",
    r"war crime\w*", r"bombing", r"missile\w*", r"invasion",
    r"ceasefire", r"sanction\w*", r"refugee\w*",
    # Crypto
    r"crypto", r"bitcoin", r"NFT", r"stonks", r"meme stock\w*",
    # Pseudoscience
    r"astrology", r"horoscope", r"zodiac", r"manifesting",
    # Sports
    r"sports score\w*", r"fantasy league\w*", r"game tonight",
]

# Science-relevant hashtags (without '#', lowercased)
_SCIENCE_HASHTAGS = {
    "neuroscience", "neuro", "neurosci",
    "cogsci", "cognitivescience", "cognitive",
    "brainscience", "brainsci",
    "psychology", "psych",
    "linguistics", "psycholinguistics",
    "philosophyofmind", "consciousness",
    "cognitiveanthropology",
    "neuropsychology", "neuropsych",
    "neurobiology", "mentalhealth",
    "cognition", "brainstim",
    "eeg", "fmri", "neuroimaging",
}


def _build_pattern(terms):
    """Build a single compiled regex from a list of terms, with word boundaries."""
    joined = "|".join(terms)
    return re.compile(rf"\b(?:{joined})\b", re.IGNORECASE)


_KEYWORD_RE = _build_pattern(_KEYWORDS)
_EXCLUSION_RE = _build_pattern(_EXCLUSION_TERMS)


def _normalize_unicode(text: str) -> str:
    """Normalize Unicode text so fancy bold/italic/etc. characters become ASCII.

    Handles mathematical bold (𝗯𝗼𝗹𝗱), italic, script, etc. that some users
    apply for visual emphasis — these are different codepoints than ASCII
    and invisible to regex without normalization.
    """
    # NFKD decomposes compatibility characters to their base forms
    # e.g. 𝗰 (U+1D5F0 MATHEMATICAL SANS-SERIF BOLD SMALL C) → c
    normalized = unicodedata.normalize("NFKD", text)
    # Strip combining marks left over from decomposition
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def passes_prefilter(text: str) -> bool:
    """Return True if the text likely relates to cognitive science.

    Normalizes Unicode first (handles fancy bold/italic text), then checks
    for any keyword match. The classifier handles precision — the prefilter
    just needs to not miss things.
    """
    text = _normalize_unicode(text)

    if _EXCLUSION_RE.search(text):
        return False

    if _KEYWORD_RE.search(text):
        return True

    return False


def check_hashtags(hashtags: list[str]) -> bool:
    """Return True if any hashtag matches a science-relevant tag.

    Args:
        hashtags: list of tag strings (without '#' prefix), as extracted
                  from Bluesky post facets.
    """
    for tag in hashtags:
        if tag.lower() in _SCIENCE_HASHTAGS:
            return True
    return False
