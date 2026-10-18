import tkinter as tk
from tkinter import scrolledtext
import random
import json
import os
import sys
import csv
import math
import urllib.request
import threading
from collections import defaultdict, Counter, deque

DEFAULT_SETTINGS = {
    "model": "qwen2.5:0.5b",
    "ollama_url": "http://localhost:11434/api/chat",
    "reply_language": "English",
    "reply_max_words": 45,
    "use_ai_input_translation": True
}
OLLAMA_URL_DEFAULT = "http://localhost:11434/api/chat"

# Resolve app resources in both normal Python and PyInstaller builds.
# Large datasets can sit beside the EXE or inside a data\ subfolder.
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
    BUNDLE_DIR = getattr(sys, "_MEIPASS", APP_DIR)
    USER_DATA_DIR = os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "FlyGPT"
    )
    os.makedirs(USER_DATA_DIR, exist_ok=True)
    SAVE_FILE = os.path.join(USER_DATA_DIR, "fly_memory.json")
    SETTINGS_FILE = os.path.join(USER_DATA_DIR, "settings.json")
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = APP_DIR
    SAVE_FILE = os.path.join(APP_DIR, "fly_memory.json")
    SETTINGS_FILE = os.path.join(APP_DIR, "settings.json")


def load_settings():
    settings = DEFAULT_SETTINGS.copy()
    # In an installed EXE, preferences live in the user's profile. The
    # settings.json beside the program is used as the first-run template.
    candidates = [SETTINGS_FILE]
    template_file = os.path.join(APP_DIR, "settings.json")
    if template_file not in candidates:
        candidates.append(template_file)

    for candidate in candidates:
        try:
            with open(candidate, "r", encoding="utf-8") as file:
                saved = json.load(file)
            if isinstance(saved, dict):
                for key in settings:
                    if key in saved:
                        settings[key] = saved[key]
            # Seed the per-user settings file on first launch of the EXE.
            if candidate != SETTINGS_FILE and getattr(sys, "frozen", False):
                try:
                    with open(SETTINGS_FILE, "w", encoding="utf-8") as file:
                        json.dump(settings, file, indent=2)
                except OSError:
                    pass
            break
        except (OSError, ValueError, TypeError):
            continue
    return settings


settings = load_settings()
MODEL = str(settings.get("model", "qwen2.5:0.5b"))
OLLAMA_URL = str(settings.get("ollama_url", OLLAMA_URL_DEFAULT))


def find_resource(filename):
    """Find a read-only resource beside the app or in its data folder."""
    candidates = [
        os.path.join(APP_DIR, filename),
        os.path.join(APP_DIR, "data", filename),
        os.path.join(BUNDLE_DIR, filename),
        os.path.join(BUNDLE_DIR, "data", filename),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    # Return the expected install location so the status message is clear.
    return candidates[0]


CONNECTOME_FILE = find_resource("connections_princeton.csv")
ANNOTATIONS_FILE = find_resource("Supplemental_file1_neuron_annotations.tsv")

INPUTS = ["food", "danger", "light", "social"]
HIDDEN = ["approach", "avoid", "explore", "rest"]

# Recent conversation is kept in RAM while the app is open.
conversation_history = []
MAX_HISTORY_MESSAGES = 12


# ==================================================
# ARTIFICIAL BEHAVIOR NETWORK
# ==================================================

def new_weights():
    return {
        source: {
            target: random.uniform(-0.5, 0.5)
            for target in HIDDEN
        }
        for source in INPUTS
    }


def initial_state():
    return {
        "hunger": 70,
        "energy": 80,
        "curiosity": 60,
        "fear": 0,
        "last_action": "EXPLORE",
        "weights": new_weights(),
        "memories": [],
        "experiences": 0,
        "last_feelings": ["The fly has not reacted to a message yet."]
    }


def clamp(value):
    return max(0, min(100, value))


def load_state():
    state = initial_state()

    if not os.path.isfile(SAVE_FILE):
        return state

    try:
        with open(SAVE_FILE, "r", encoding="utf-8") as file:
            saved = json.load(file)

        for key in (
            "hunger", "energy", "curiosity", "fear",
            "last_action", "memories", "experiences", "last_feelings"
        ):
            if key in saved:
                state[key] = saved[key]

        old_weights = saved.get("weights", {})

        for source in INPUTS:
            for target in HIDDEN:
                try:
                    state["weights"][source][target] = float(
                        old_weights[source][target]
                    )
                except (KeyError, TypeError, ValueError):
                    pass

    except (OSError, ValueError, TypeError):
        pass

    return state


brain = load_state()
busy = False


def save_state():
    try:
        temporary = SAVE_FILE + ".tmp"

        with open(temporary, "w", encoding="utf-8") as file:
            json.dump(brain, file, indent=2)

        os.replace(temporary, SAVE_FILE)

    except OSError:
        pass


def activate(value):
    value = max(-20, min(20, value))
    return 1.0 / (1.0 + math.exp(-value))


def neural_process(stimuli):
    values = {}

    for target in HIDDEN:
        total = sum(
            stimuli[source] * brain["weights"][source][target]
            for source in INPUTS
        )
        values[target] = activate(total)

    values["approach"] += brain["hunger"] / 200
    values["avoid"] += brain["fear"] / 150
    values["explore"] += brain["curiosity"] / 200
    values["rest"] += (100 - brain["energy"]) / 150

    return max(values, key=values.get), values


def describe_change(name, old, new):
    """Turn a state change into a short in-simulation feeling description."""
    difference = new - old
    if abs(difference) < 2:
        return None

    descriptions = {
        "fear": ("more afraid", "a bit safer"),
        "hunger": ("hungrier", "less hungry"),
        "energy": ("more energetic", "more tired"),
        "curiosity": ("more curious", "less curious"),
    }
    if name not in descriptions:
        return None

    increase, decrease = descriptions[name]
    feeling = increase if difference > 0 else decrease
    return f"The fly started to feel {feeling} ({old} -> {new})."


def keyword_stimuli(message):
    """Fallback input translator when Ollama is unavailable for classification."""
    text = message.lower()
    food_words = ["banana", "apple", "fruit", "food", "sugar", "yeast", "eat", "hungry"]
    danger_words = ["bird", "danger", "spider", "predator", "swat", "trap", "threat", "unsafe"]
    light_words = ["light", "lamp", "bright", "sun", "flash", "dark"]
    social_words = ["hello", "hi", "hey", "fly", "bzz", "come here", "look"]
    return {
        "food": float(any(word in text for word in food_words)),
        "danger": float(any(word in text for word in danger_words)),
        "light": float(any(word in text for word in light_words)),
        "social": float(any(word in text for word in social_words)),
    }


def translate_message_to_stimuli(message):
    """Translate human text into simple cues; this call does not write the fly's reply."""
    fallback = keyword_stimuli(message)
    if not settings.get("use_ai_input_translation", True):
        return fallback

    prompt = (
        "Translate the human message into cues for a simple simulated fruit fly. "
        "Do not answer the human. Return ONLY valid JSON with numeric values 0 or 1 "
        "for exactly these keys: food, danger, light, social. Set a cue to 1 only "
        "when the message plausibly signals it. Negation matters: 'there is no danger' "
        "must set danger to 0. Do not infer danger merely because the word appears.\n"
        f"Human message: {message[:1000]}"
    )
    try:
        payload = {
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1, "num_predict": 80}
        }
        request = urllib.request.Request(
            OLLAMA_URL, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
        raw = data.get("message", {}).get("content", "")
        parsed = json.loads(raw)
        return {key: float(bool(parsed.get(key, fallback[key]))) for key in INPUTS}
    except Exception:
        # Keyword fallback keeps FlyGPT usable if the model returns malformed JSON.
        return fallback


def process_brain(message, stimuli=None):
    """Process translated cues and save the changes caused by this message."""
    if stimuli is None:
        stimuli = keyword_stimuli(message)

    stimuli = {
        key: float(bool(stimuli.get(key, 0)))
        for key in INPUTS
    }
    previous_state = {
        key: int(brain.get(key, 0))
        for key in ("fear", "hunger", "energy", "curiosity")
    }

    # Baseline drift in this deliberately simplified artificial model.
    brain["hunger"] = clamp(brain["hunger"] + 1)
    brain["energy"] = clamp(brain["energy"] - 1)
    brain["curiosity"] = clamp(brain["curiosity"] + 1)

    if stimuli["food"]:
        brain["hunger"] = clamp(brain["hunger"] - 20)
        brain["energy"] = clamp(brain["energy"] + 3)

    if stimuli["danger"]:
        brain["fear"] = clamp(brain["fear"] + 35)
    else:
        brain["fear"] = clamp(brain["fear"] - 3)

    action, activations = neural_process(stimuli)

    if stimuli["danger"]:
        action = "avoid"
    elif stimuli["food"]:
        action = "approach"
    elif brain["energy"] < 15:
        action = "rest"

    names = {
        "approach": "APPROACH_STIMULUS",
        "avoid": "AVOID_DANGER",
        "explore": "EXPLORE",
        "rest": "REST"
    }
    result = names[action]
    brain["last_action"] = result
    brain["experiences"] += 1

    feelings = []
    for key, old_value in previous_state.items():
        description = describe_change(key, old_value, int(brain[key]))
        if description:
            feelings.append(description)
    brain["last_feelings"] = feelings or ["The fly's internal state barely changed."]

    brain["memories"].append({
        "message": message[:100],
        "action": result,
        "stimuli": stimuli.copy(),
        "feelings": list(brain["last_feelings"])
    })
    brain["memories"] = brain["memories"][-20:]
    save_state()
    return result, activations


# ==================================================
# REAL CONNECTOME CONNECTIONS
# ==================================================

outgoing = defaultdict(list)
incoming = defaultdict(list)
neuron_ids = set()
neuropil_counts = Counter()
transmitter_counts = Counter()

connectome_loaded = False
connectome_error = ""
connection_count = 0


def load_connectome():
    global connectome_loaded, connectome_error, connection_count

    if not os.path.isfile(CONNECTOME_FILE):
        connectome_error = "CSV not found: connections_princeton.csv"
        return

    try:
        with open(
            CONNECTOME_FILE, "r", encoding="utf-8-sig", newline=""
        ) as file:
            reader = csv.DictReader(file)

            required = {
                "pre_root_id", "post_root_id",
                "neuropil", "syn_count", "nt_type"
            }

            if not required.issubset(set(reader.fieldnames or [])):
                connectome_error = "CSV columns do not match expected format."
                return

            for row in reader:
                source = (row.get("pre_root_id") or "").strip()
                target = (row.get("post_root_id") or "").strip()

                if not source or not target:
                    continue

                try:
                    synapses = int(row.get("syn_count", ""))
                except (ValueError, TypeError):
                    continue

                if synapses <= 0:
                    continue

                neuropil = (row.get("neuropil") or "").strip()
                transmitter = (row.get("nt_type") or "unknown").strip()

                outgoing[source].append((target, synapses))
                incoming[target].append((source, synapses))

                neuron_ids.add(source)
                neuron_ids.add(target)

                if neuropil:
                    neuropil_counts[neuropil] += 1

                if transmitter:
                    transmitter_counts[transmitter] += 1

                connection_count += 1

        for node in outgoing:
            outgoing[node].sort(
                key=lambda edge: edge[1], reverse=True
            )

        connectome_loaded = connection_count > 0

        if not connectome_loaded:
            connectome_error = "No valid connections found."

    except (OSError, csv.Error, UnicodeError) as error:
        connectome_error = str(error)


load_connectome()


# ==================================================
# FLYWIRE NEURON ANNOTATIONS
# ==================================================

annotations = {}
annotations_loaded = False
annotations_error = ""
annotation_count = 0
annotation_fields = []


def load_annotations():
    global annotations_loaded, annotations_error
    global annotation_count, annotation_fields

    if not os.path.isfile(ANNOTATIONS_FILE):
        annotations_error = (
            "TSV not found: "
            "Supplemental_file1_neuron_annotations.tsv"
        )
        return

    try:
        with open(
            ANNOTATIONS_FILE, "r", encoding="utf-8-sig", newline=""
        ) as file:
            reader = csv.DictReader(file, delimiter="\t")
            annotation_fields = reader.fieldnames or []

            if "root_id" not in annotation_fields:
                annotations_error = (
                    "No 'root_id' column found in the TSV. "
                    "Check that this is the neuron annotation file."
                )
                return

            useful_fields = [
                "root_id", "flow", "super_class", "cell_class",
                "cell_sub_class", "cell_type", "hemibrain_type",
                "side", "nerve", "top_nt", "known_nt", "synonyms",
                "fbbt_id", "vfb_id", "status", "fru_dsx", "supertype"
            ]

            for row in reader:
                root_id = (row.get("root_id") or "").strip()

                if not root_id or root_id.lower() in ("na", "nan"):
                    continue

                info = {}

                for field in useful_fields:
                    value = (row.get(field) or "").strip()

                    if value and value.lower() not in ("na", "nan"):
                        info[field] = value

                annotations[root_id] = info
                annotation_count += 1

        annotations_loaded = annotation_count > 0

        if not annotations_loaded:
            annotations_error = "No annotation rows with root_id found."

    except (OSError, csv.Error, UnicodeError) as error:
        annotations_error = str(error)


load_annotations()


def annotation_report():
    if not annotations_loaded:
        return (
            "=== FLYWIRE ANNOTATIONS ===\n"
            "Annotations could not be loaded.\n"
            + annotations_error
            + "\n\nPlace the TSV beside FlyGPT.exe or in the data folder, then restart FlyGPT."
        )

    matched = len(set(annotations).intersection(neuron_ids))

    return (
        "=== FLYWIRE ANNOTATIONS ===\n"
        f"Annotation rows loaded: {annotation_count:,}\n"
        f"IDs also found in connectome: {matched:,}\n\n"
        "Commands:\n"
        "/search visual\n"
        "/search photoreceptor\n"
        "/search T4\n"
        "/neuron ID\n\n"
        "The two files may use different dataset releases."
    )


def neuron_annotation_report(node):
    info = annotations.get(node)

    if not info:
        return (
            f"No annotation found for neuron {node}.\n"
            "The ID may be missing, or the files may use "
            "different dataset releases."
        )

    fields = [
        ("cell_type", "Cell type"),
        ("cell_class", "Cell class"),
        ("cell_sub_class", "Cell subclass"),
        ("super_class", "Superclass"),
        ("flow", "Flow"),
        ("hemibrain_type", "Hemibrain type"),
        ("side", "Side"),
        ("nerve", "Nerve"),
        ("top_nt", "Predicted neurotransmitter"),
        ("known_nt", "Known neurotransmitter"),
        ("synonyms", "Synonyms"),
        ("fbbt_id", "FlyBase ontology ID"),
        ("vfb_id", "VirtualFlyBrain ID"),
        ("status", "Status"),
        ("supertype", "Supertype")
    ]

    lines = [f"=== NEURON ANNOTATION: {node} ==="]

    for key, label in fields:
        if info.get(key):
            lines.append(f"{label}: {info[key]}")

    if len(lines) == 1:
        lines.append("No descriptive annotation fields were populated.")

    return "\n".join(lines)


def search_annotations(query, limit=25):
    if not annotations_loaded:
        return "Annotations unavailable:\n" + annotations_error

    query = query.strip().lower()

    if not query:
        return (
            "Usage: /search SEARCH_TERM\n"
            "Examples: /search visual, /search photoreceptor, /search T4"
        )

    searchable_fields = [
        "flow", "super_class", "cell_class", "cell_sub_class",
        "cell_type", "hemibrain_type", "nerve", "top_nt",
        "known_nt", "synonyms", "supertype"
    ]

    results = []

    for root_id, info in annotations.items():
        matched_field = None

        for field in searchable_fields:
            if query in info.get(field, "").lower():
                matched_field = field
                break

        if matched_field:
            results.append((
                root_id not in neuron_ids,
                root_id,
                info,
                matched_field
            ))

    results.sort(key=lambda item: (item[0], item[1]))

    lines = [
        f"=== ANNOTATION SEARCH: {query} ===",
        f"Matching neurons: {len(results):,}",
        f"Showing up to {limit} results.",
        "Connectome matches are shown first.",
        ""
    ]

    for not_in_connectome, root_id, info, matched_field in results[:limit]:
        label = (
            info.get("cell_type")
            or info.get("hemibrain_type")
            or info.get("cell_class")
            or info.get("cell_sub_class")
            or "(no cell-type label)"
        )

        extra = []
        if info.get("side"):
            extra.append(info["side"])
        if info.get("top_nt"):
            extra.append(info["top_nt"])

        suffix = " | " + " | ".join(extra) if extra else ""
        status = "" if not not_in_connectome else " [not in CSV]"

        lines.append(f"{root_id} | {label}{suffix}{status}")
        lines.append(
            f"    Matched field: {matched_field} = "
            f"{info.get(matched_field, '')}"
        )

    if not results:
        lines.append("No matches. Try a broader search term.")

    lines.extend([
        "",
        "Use /neuron ID to inspect an ID.",
        "A text match does not prove the neuron's exact function."
    ])

    return "\n".join(lines)


# ==================================================
# CONNECTOME REPORTS AND GRAPH EXPERIMENTS
# ==================================================

def connectome_report():
    if not connectome_loaded:
        return (
            "=== CONNECTOME ===\n"
            "Could not load connection data.\n"
            + connectome_error
        )

    lines = [
        "=== REAL CONNECTOME DATA ===",
        f"Neurons referenced: {len(neuron_ids):,}",
        f"Connection records: {connection_count:,}",
        "",
        "Most common neuropil labels:"
    ]

    for name, count in neuropil_counts.most_common(8):
        lines.append(f"  {name}: {count:,} records")

    lines.extend(["", "Transmitter labels:"])

    for name, count in transmitter_counts.most_common(8):
        lines.append(f"  {name}: {count:,} records")

    lines.extend([
        "",
        "Commands:",
        "/neuron ID - inspect a neuron",
        "/search TERM - search neuron annotations",
        "/annotations - metadata status",
        "/inputs ID - show incoming connections",
        "/outputs ID - show outgoing connections",
        "/path ID1 ID2 - find a directed graph path",
        "/propagate ID - simplified graph experiment",
        "",
        "The graph is not a complete biological behavior model."
    ])

    return "\n".join(lines)


def neuron_report(node):
    if not connectome_loaded:
        return "Connectome unavailable: " + connectome_error

    if node not in neuron_ids:
        if node in annotations:
            return (
                "This neuron has annotation data but is not referenced "
                "in the loaded connection CSV.\n\n"
                + neuron_annotation_report(node)
            )

        return f"Neuron {node} was not found in the connection CSV."

    lines = [
        f"=== NEURON {node} ===",
        f"Outgoing connection records: {len(outgoing[node])}",
        f"Incoming connection records: {len(incoming[node])}",
        ""
    ]

    if node in annotations:
        lines.append(neuron_annotation_report(node))
    else:
        lines.append("No matching annotation found for this neuron ID.")

    lines.extend(["", "Strongest outgoing connections:"])

    for target, count in outgoing[node][:10]:
        target_info = annotations.get(target, {})
        label = target_info.get("cell_type") or target_info.get("cell_class")
        suffix = f" [{label}]" if label else ""
        lines.append(f"  -> {target}: {count} synapses{suffix}")

    lines.extend(["", "Strongest incoming connections:"])

    strongest = sorted(
        incoming[node], key=lambda edge: edge[1], reverse=True
    )[:10]

    for source, count in strongest:
        source_info = annotations.get(source, {})
        label = source_info.get("cell_type") or source_info.get("cell_class")
        suffix = f" [{label}]" if label else ""
        lines.append(f"  {source} ->: {count} synapses{suffix}")

    return "\n".join(lines)


def connection_report(node, direction, limit=15):
    if not connectome_loaded:
        return "Connectome unavailable: " + connectome_error

    if node not in neuron_ids:
        return f"Neuron {node} was not found in the connection CSV."

    edges = outgoing[node] if direction == "out" else incoming[node]
    edges = sorted(edges, key=lambda edge: edge[1], reverse=True)

    title = "OUTPUTS" if direction == "out" else "INPUTS"
    lines = [
        f"=== NEURON {node}: {title} ===",
        f"Connection records: {len(edges)}",
        f"Showing up to {limit} connections, strongest first.",
        ""
    ]

    for other, synapses in edges[:limit]:
        info = annotations.get(other, {})
        label = (
            info.get("cell_type")
            or info.get("cell_class")
            or info.get("cell_sub_class")
            or "unknown type"
        )

        if direction == "out":
            lines.append(f"{node} -> {other} | {synapses} synapses | {label}")
        else:
            lines.append(f"{other} -> {node} | {synapses} synapses | {label}")

    if not edges:
        lines.append("No connections recorded in this direction.")

    return "\n".join(lines)


def find_path(start, goal, max_depth=8, max_nodes=50000):
    if not connectome_loaded:
        return "Connectome unavailable: " + connectome_error

    if start not in neuron_ids or goal not in neuron_ids:
        return "Both neuron IDs must exist in the connection CSV."

    if start == goal:
        return "Start and destination are the same neuron."

    queue = deque([(start, 0)])
    parent = {start: None}
    found = False

    while queue and len(parent) < max_nodes:
        current, depth = queue.popleft()

        if depth >= max_depth:
            continue

        # outgoing edges are already sorted by synapse count
        for neighbor, _ in outgoing.get(current, []):
            if neighbor in parent:
                continue

            parent[neighbor] = current

            if neighbor == goal:
                found = True
                break

            queue.append((neighbor, depth + 1))

            if len(parent) >= max_nodes:
                break

        if found:
            break

    if not found:
        return (
            f"No path found from {start} to {goal} "
            f"within {max_depth} steps and {max_nodes} explored nodes."
        )

    path = []
    node = goal

    while node is not None:
        path.append(node)
        node = parent[node]

    path.reverse()

    lines = [
        "=== CONNECTOME PATH ===",
        f"Start: {start}",
        f"Destination: {goal}",
        f"Edges in path: {len(path) - 1}",
        "",
        " -> ".join(path),
        "",
        "Neuron labels:"
    ]

    for node in path:
        info = annotations.get(node, {})
        label = (
            info.get("cell_type")
            or info.get("cell_class")
            or "unknown type"
        )
        lines.append(f"{node}: {label}")

    lines.extend([
        "",
        "This is a directed graph path, not proof of a functional signal route."
    ])

    return "\n".join(lines)


def propagate_signal(start_node, steps=3):
    if not connectome_loaded:
        return "Connectome unavailable: " + connectome_error

    if start_node not in neuron_ids:
        return f"Neuron {start_node} is not in the connection CSV."

    active = {start_node: 1.0}

    lines = [
        "=== CONNECTOME GRAPH EXPERIMENT ===",
        f"Starting neuron: {start_node}",
        f"Propagation rounds: {steps}",
        "",
        "Simplified graph calculation, not a biological firing prediction."
    ]

    for step in range(1, steps + 1):
        next_active = defaultdict(float)

        for source, activation_value in active.items():
            edges = outgoing.get(source, [])[:20]

            if not edges:
                continue

            total_weight = sum(weight for _, weight in edges)

            if total_weight <= 0:
                continue

            for target, weight in edges:
                next_active[target] += (
                    activation_value * weight / total_weight
                )

        active = dict(sorted(
            next_active.items(),
            key=lambda item: item[1],
            reverse=True
        )[:200])

        lines.append(f"Round {step}: {len(active)} active graph nodes")

        if not active:
            lines.append("No further outgoing paths.")
            break

    lines.extend(["", "Highest propagated values:"])

    for node, value in sorted(
        active.items(), key=lambda item: item[1], reverse=True
    )[:10]:
        info = annotations.get(node, {})
        label = info.get("cell_type") or info.get("cell_class")
        suffix = f" | {label}" if label else ""
        lines.append(f"  {node}: {value:.4f}{suffix}")

    return "\n".join(lines)


# ==================================================
# STATUS, LEARNING AND COMMANDS
# ==================================================

def brain_report():
    return (
        "=== BRAIN STATUS ===\n"
        f"Hunger: {brain['hunger']}/100\n"
        f"Energy: {brain['energy']}/100\n"
        f"Curiosity: {brain['curiosity']}/100\n"
        f"Fear: {brain['fear']}/100\n"
        f"Last action: {brain['last_action']}\n"
        f"Experiences: {brain['experiences']}\n"
        "Last feelings:\n" + "\n".join(
            f"  - {feeling}" for feeling in brain.get(
                "last_feelings", ["The fly has not reacted to a message yet."]
            )
        )
    )


def brain_details():
    lines = ["=== ARTIFICIAL BEHAVIOR NETWORK ==="]

    for source in INPUTS:
        lines.append(f"\n{source}:")

        for target in HIDDEN:
            lines.append(
                f"  -> {target}: "
                f"{brain['weights'][source][target]:+.3f}"
            )

    lines.append("\nRecent experiences:")

    for memory in brain["memories"][-5:]:
        lines.append(f"  {memory['message']} -> {memory['action']}")

    lines.extend([
        "",
        connectome_report(),
        "",
        annotation_report()
    ])

    return "\n".join(lines)


def learn_from_reward(reward):
    mapping = {
        "APPROACH_STIMULUS": "approach",
        "AVOID_DANGER": "avoid",
        "EXPLORE": "explore",
        "REST": "rest"
    }

    target = mapping.get(brain["last_action"])

    if target is None:
        return "No behavior available to learn from yet."

    amount = 0.05 if reward > 0 else -0.05

    for source in INPUTS:
        brain["weights"][source][target] += amount

    save_state()

    return (
        f"Adjusted artificial connections for {target}.\n"
        "This is experimental artificial learning, not biological learning."
    )


def handle_command(command):
    parts = command.split()

    if not parts:
        return ""

    name = parts[0].lower()

    if name == "/help":
        return (
            "/help - Show commands\n"
            "/status - Show behavior state and last feelings\n"
            "/settings - Show settings file and current options\n"
            "/brain - Inspect networks and data\n"
            "/connectome - Show connection summary\n"
            "/annotations - Show metadata status\n"
            "/search TERM - Search neuron labels\n"
            "/neuron ID - Inspect a neuron\n"
            "/inputs ID - Show incoming connections\n"
            "/outputs ID - Show outgoing connections\n"
            "/path ID1 ID2 - Find a directed graph path\n"
            "/propagate ID - Run graph experiment\n"
            "/feed - Simulate food stimulus\n"
            "/danger - Simulate danger\n"
            "/light - Simulate light\n"
            "/rest - Restore energy\n"
            "/reward - Reward last behavior\n"
            "/punish - Discourage last behavior\n"
            "/reset - Reset behavior state"
        )

    if name == "/status":
        return brain_report()

    if name == "/settings":
        return (
            "=== FLYGPT SETTINGS ===\n"
            f"Settings file: {SETTINGS_FILE}\n"
            + json.dumps(settings, indent=2)
            + "\n\nEdit settings.json and restart FlyGPT to apply changes."
        )

    if name == "/brain":
        return brain_details()

    if name == "/connectome":
        return connectome_report()

    if name == "/annotations":
        return annotation_report()

    if name == "/search":
        query = command[len(parts[0]):].strip()
        return search_annotations(query)

    if name in ("/neuron", "/propagate", "/inputs", "/outputs"):
        if len(parts) != 2 or not parts[1].isdigit():
            return f"Usage: {name} NEURON_ID"

        node = parts[1]

        if name == "/neuron":
            return neuron_report(node)
        if name == "/propagate":
            return propagate_signal(node)
        if name == "/inputs":
            return connection_report(node, "in")
        return connection_report(node, "out")

    if name == "/path":
        if len(parts) != 3:
            return "Usage: /path START_NEURON_ID DESTINATION_NEURON_ID"

        if not parts[1].isdigit() or not parts[2].isdigit():
            return "Both neuron IDs must contain digits only."

        return find_path(parts[1], parts[2])

    if name in ("/feed", "/danger", "/light"):
        messages = {
            "/feed": "I see a banana",
            "/danger": "A predator is nearby",
            "/light": "I see a bright light"
        }

        action, activations = process_brain(messages[name])

        values = "\n".join(
            f"{key}: {value:.2f}"
            for key, value in activations.items()
        )

        return (
            f"Stimulus processed.\nAction: {action}\n\n"
            f"Artificial behavior-network activations:\n{values}\n\n"
            + brain_report()
        )

    if name == "/rest":
        previous_state = {
            key: int(brain.get(key, 0))
            for key in ("fear", "hunger", "energy", "curiosity")
        }
        brain["energy"] = clamp(brain["energy"] + 25)
        brain["fear"] = clamp(brain["fear"] - 10)
        feelings = []
        for key, old_value in previous_state.items():
            description = describe_change(key, old_value, int(brain[key]))
            if description:
                feelings.append(description)
        brain["last_feelings"] = feelings or ["The fly's internal state barely changed."]
        save_state()
        return "Rest simulated.\n\n" + brain_report()

    if name == "/reward":
        return learn_from_reward(1)

    if name == "/punish":
        return learn_from_reward(-1)

    if name == "/reset":
        brain.clear()
        brain.update(initial_state())
        save_state()
        conversation_history.clear()
        return "Behavior state and artificial weights reset. Chat history cleared."

    return "Unknown command. Type /help."


# ==================================================
# OLLAMA CHAT
# ==================================================

def fallback_fly_reply(action, stimuli):
    """Reliable format fallback if the small language model ignores the prompt."""
    fear = int(brain.get("fear", 0))
    hunger = int(brain.get("hunger", 0))
    energy = int(brain.get("energy", 0))
    curiosity = int(brain.get("curiosity", 0))
    last_feelings = " ".join(brain.get("last_feelings", [])).lower()

    if "safer" in last_feelings:
        feeling = "a little safer"
    elif fear >= 65:
        feeling = "alarmed and cautious"
    elif fear >= 30:
        feeling = "uneasy and alert"
    elif energy <= 20:
        feeling = "tired"
    elif hunger >= 75:
        feeling = "hungry and alert"
    elif curiosity >= 65:
        feeling = "curious and alert"
    else:
        feeling = "calm and alert"

    if action == "AVOID_DANGER" or stimuli.get("danger"):
        phrase = "BZZ! Away, away!"
    elif action == "APPROACH_STIMULUS" and stimuli.get("food"):
        phrase = "Bzz! Something tasty!"
    elif action == "REST":
        phrase = "Bzz... time to rest."
    elif stimuli.get("social"):
        phrase = "Bzz! What's that?"
    elif stimuli.get("light"):
        phrase = "Bzz? What's that bright thing?"
    else:
        phrase = "Bzz..."

    return f'The fly feels {feeling}. It seems to want to say, "{phrase}"'


def ask_ai(message, action, activations, stimuli):
    """Translate the simulation's current response into a fly-like phrase."""
    # Deliberately do not send chat history here: previous assistant-style replies
    # can make a small model imitate a helpful chatbot instead of translating
    # the fly simulation's current state.
    state = {
        "hunger": brain["hunger"],
        "energy": brain["energy"],
        "curiosity": brain["curiosity"],
        "fear": brain["fear"],
        "last_feelings": brain.get("last_feelings", []),
        "last_action": brain.get("last_action", action),
    }

    system_prompt = f"""
You are NOT a human assistant and NOT a chatbot. You are the language translator
for a small, simplified fruit-fly behavior simulation. The human's message has
already been converted into stimulus cues and processed by the simulation.
Your only job is to translate the resulting state into a short, imaginative,
fly-like reaction. Do not answer the human normally, give advice, reassure them,
offer help, or ask how you can help.

OUTPUT FORMAT — follow this format every time:
The fly feels [a short feeling/state grounded in the supplied state]. It seems
to want to say, "[a short playful fly-like phrase]"

Keep it to 1-2 sentences and under {int(settings.get('reply_max_words', 45))} words.
Do not repeat the human's message. Do not describe generic circling/hovering unless
the action/state makes that relevant. Do not claim that the fly literally speaks;
"wants to say" is a playful translation. Do not invent state changes. Use only the
provided current state, last feelings, stimuli and selected action.

Examples of the required style:
Human: "Hey my little fly pet!"
State suggests curiosity, social cue, no danger.
Output: The fly feels curious and a little alert. It seems to want to say, "Bzz! What's that?"

Human: "There is no danger, little fly."
State shows fear decreasing.
Output: The fly feels a little safer. It seems to want to say, "Bzz... all clear?"

Human: "A bird is chasing you!"
State shows high fear and avoid action.
Output: The fly feels alarmed. It seems to want to say, "BZZ! Away, away!"

Human: "Look, fruit!"
State shows food cue and approach action.
Output: The fly feels drawn toward the food. It seems to want to say, "Bzz! Something tasty!"

SIMULATION STATE:
{json.dumps(state)}
INPUT CUES: {json.dumps(stimuli)}
SELECTED ACTION: {action}
NETWORK ACTIVATIONS: {json.dumps(activations)}
HUMAN MESSAGE (context for interpreting the already-processed cues only): {message[:1000]}

The state and connectome graph are simplified experiments, not a validated model
of a real fly brain. Never claim otherwise.
"""
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system_prompt}],
        "stream": False,
        "options": {
            "temperature": 0.65,
            "num_predict": 90
        }
    }
    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )

    with urllib.request.urlopen(request, timeout=120) as response:
        data = json.loads(response.read().decode("utf-8"))

    reply = data.get("message", {}).get("content", "").strip()

    # Save a lightweight record for diagnostics, but don't feed it back as
    # chatbot-style conversation history to the next generation.
    if reply:
        # Enforce the requested output shape. Tiny models sometimes ignore the
        # prompt and revert to assistant-style chat; use a state-based fallback.
        normalized = reply.lstrip().strip('"\'` ')
        if (
            normalized.lower().startswith("the fly feels")
            and "it seems to want to say" in normalized.lower()
        ):
            conversation_history.append({"role": "user", "content": message[:1000]})
            conversation_history.append({"role": "assistant", "content": normalized})
            del conversation_history[:-MAX_HISTORY_MESSAGES]
            return normalized

    return fallback_fly_reply(action, stimuli)


# ==================================================
# TKINTER INTERFACE
# ==================================================

def add_chat(message):
    chat.config(state="normal")
    chat.insert(tk.END, message + "\n")
    chat.config(state="disabled")
    chat.see(tk.END)


def send_message(event=None):
    global busy

    if busy:
        return

    message = entry.get().strip()

    if not message:
        return

    entry.delete(0, tk.END)
    add_chat(f"You: {message}")

    if message.startswith("/"):
        add_chat(f"Fly: {handle_command(message.strip())}\n")
        return

    busy = True
    send_button.config(state="disabled", text="Translating...")
    entry.config(state="disabled")

    threading.Thread(
        target=ai_worker,
        args=(message,),
        daemon=True
    ).start()


def ai_worker(message):
    try:
        # Language -> cues -> simulation -> fly-language response.
        stimuli = translate_message_to_stimuli(message)
        action, activations = process_brain(message, stimuli)
        reply = ask_ai(message, action, activations, stimuli)
    except Exception as error:
        reply = (
            "Bzz! I could not reach Ollama.\n"
            "Make sure Ollama is running.\n"
            f"Details: {error}"
        )

    root.after(0, finish_message, reply)


def finish_message(reply):
    global busy

    add_chat(f"Fly: {reply}\n")
    busy = False
    send_button.config(state="normal", text="Send")
    entry.config(state="normal")
    entry.focus_set()


def close_app():
    save_state()
    root.destroy()


root = tk.Tk()
root.title("FlyGPT - Fruit Fly Connectome Experiment")
root.geometry("700x780")
root.configure(bg="#20252d")
root.protocol("WM_DELETE_WINDOW", close_app)

title = tk.Label(
    root,
    text="FlyGPT 🪰",
    font=("Arial", 23, "bold"),
    bg="#20252d",
    fg="#a8e6a3"
)
title.pack(pady=12)

subtitle = tk.Label(
    root,
    text="Ollama + FlyWire Connectome + Annotations",
    font=("Arial", 10),
    bg="#20252d",
    fg="#b7c0cc"
)
subtitle.pack()

chat = scrolledtext.ScrolledText(
    root,
    wrap=tk.WORD,
    font=("Arial", 10),
    bg="#15191f",
    fg="white",
    insertbackground="white",
    state="disabled"
)
chat.pack(padx=12, pady=12, fill="both", expand=True)

entry = tk.Entry(
    root,
    font=("Arial", 12),
    bg="#303742",
    fg="white",
    insertbackground="white"
)
entry.pack(padx=12, pady=5, fill="x")
entry.bind("<Return>", send_message)

send_button = tk.Button(
    root,
    text="Send",
    command=send_message,
    font=("Arial", 11, "bold"),
    bg="#a8e6a3",
    fg="#20252d",
    relief="flat"
)
send_button.pack(pady=(5, 12))

add_chat(
    "Fly: Bzz! FlyGPT is ready.\n"
    "Fly: Type /help to see the commands.\n\n"
    + connectome_report()
    + "\n\n"
    + annotation_report()
)

entry.focus_set()
root.mainloop()
