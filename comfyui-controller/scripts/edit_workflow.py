#!/usr/bin/env python3
"""Edit a ComfyUI workflow JSON: update prompts, parameters, seeds, etc."""
import argparse
import json
import random
import sys


def load_workflow(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_workflow(path, workflow):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(workflow, f, indent=2, ensure_ascii=False)


def find_nodes_by_class(workflow, class_types):
    """Find nodes matching any of the given class_types (case-insensitive)."""
    results = []
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type", "").lower()
        if ct in [c.lower() for c in class_types]:
            results.append((node_id, node))
    return results


def find_nodes_by_title(workflow, keywords):
    """Find nodes whose _meta.title contains any of the keywords (case-insensitive)."""
    results = []
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        title = node.get("_meta", {}).get("title", "").lower()
        if any(kw.lower() in title for kw in keywords):
            results.append((node_id, node))
    return results


def update_prompt(workflow, prompt_text, target="positive"):
    """Update prompt text in the workflow."""
    # Try to find by class_type first
    clip_nodes = find_nodes_by_class(workflow, ["CLIPTextEncode"])
    
    if target == "positive":
        # Look for nodes with positive-related titles
        positive_nodes = find_nodes_by_title(workflow, ["positive", "prompt", "正面"])
        if positive_nodes:
            for node_id, node in positive_nodes:
                if "text" in node.get("inputs", {}):
                    node["inputs"]["text"] = prompt_text
                    return True
        # Otherwise update the first CLIPTextEncode
        if clip_nodes:
            node_id, node = clip_nodes[0]
            if "text" in node.get("inputs", {}):
                node["inputs"]["text"] = prompt_text
                return True
    elif target == "negative":
        negative_nodes = find_nodes_by_title(workflow, ["negative", "负面"])
        if negative_nodes:
            for node_id, node in negative_nodes:
                if "text" in node.get("inputs", {}):
                    node["inputs"]["text"] = prompt_text
                    return True
        # Update second CLIPTextEncode if exists
        if len(clip_nodes) > 1:
            node_id, node = clip_nodes[1]
            if "text" in node.get("inputs", {}):
                node["inputs"]["text"] = prompt_text
                return True
    return False


def update_seed(workflow, seed=None):
    """Update seed in sampler nodes. If seed is None, generate random."""
    if seed is None:
        seed = random.randint(0, 0xFFFFFFFF)
    
    sampler_classes = ["KSampler", "BasicSampler", "BasicGuider", "SamplerCustom"]
    sampler_nodes = find_nodes_by_class(workflow, sampler_classes)
    
    updated = False
    for node_id, node in sampler_nodes:
        if "seed" in node.get("inputs", {}):
            node["inputs"]["seed"] = seed
            updated = True
    return updated, seed


def update_resolution(workflow, width=None, height=None):
    """Update resolution in EmptyLatentImage nodes."""
    latent_nodes = find_nodes_by_class(workflow, ["EmptyLatentImage", "EmptySD3LatentImage"])
    updated = False
    for node_id, node in latent_nodes:
        if width is not None and "width" in node.get("inputs", {}):
            node["inputs"]["width"] = width
            updated = True
        if height is not None and "height" in node.get("inputs", {}):
            node["inputs"]["height"] = height
            updated = True
    return updated


def update_sampler_steps(workflow, steps=None):
    """Update steps in sampler nodes."""
    sampler_classes = ["KSampler", "BasicSampler", "SamplerCustom"]
    sampler_nodes = find_nodes_by_class(workflow, sampler_classes)
    updated = False
    for node_id, node in sampler_nodes:
        if steps is not None and "steps" in node.get("inputs", {}):
            node["inputs"]["steps"] = steps
            updated = True
    return updated


def update_cfg(workflow, cfg=None):
    """Update CFG scale in sampler nodes."""
    sampler_classes = ["KSampler", "BasicSampler", "SamplerCustom"]
    sampler_nodes = find_nodes_by_class(workflow, sampler_classes)
    updated = False
    for node_id, node in sampler_nodes:
        if cfg is not None and "cfg" in node.get("inputs", {}):
            node["inputs"]["cfg"] = cfg
            updated = True
    return updated


def update_model(workflow, model_name):
    """Update checkpoint/model in CheckpointLoader nodes."""
    loader_classes = ["CheckpointLoaderSimple", "CheckpointLoader", "UNETLoader", "DualCLIPLoader"]
    loader_nodes = find_nodes_by_class(workflow, loader_classes)
    updated = False
    for node_id, node in loader_nodes:
        if "ckpt_name" in node.get("inputs", {}):
            node["inputs"]["ckpt_name"] = model_name
            updated = True
        elif "model_name" in node.get("inputs", {}):
            node["inputs"]["model_name"] = model_name
            updated = True
    return updated


def main():
    ap = argparse.ArgumentParser(description="Edit ComfyUI workflow JSON")
    ap.add_argument("--input", required=True, help="Input workflow JSON path")
    ap.add_argument("--output", required=True, help="Output workflow JSON path")
    ap.add_argument("--positive-prompt", help="Update positive prompt text")
    ap.add_argument("--negative-prompt", help="Update negative prompt text")
    ap.add_argument("--seed", type=int, help="Set seed (random if not provided)")
    ap.add_argument("--random-seed", action="store_true", help="Set a random seed")
    ap.add_argument("--width", type=int, help="Set image width")
    ap.add_argument("--height", type=int, help="Set image height")
    ap.add_argument("--steps", type=int, help="Set sampler steps")
    ap.add_argument("--cfg", type=float, help="Set CFG scale")
    ap.add_argument("--model", help="Set checkpoint/model name")
    args = ap.parse_args()

    workflow = load_workflow(args.input)
    changes = []

    if args.positive_prompt:
        if update_prompt(workflow, args.positive_prompt, target="positive"):
            changes.append("positive prompt")
    if args.negative_prompt:
        if update_prompt(workflow, args.negative_prompt, target="negative"):
            changes.append("negative prompt")
    if args.seed is not None or args.random_seed:
        seed = args.seed if args.seed is not None else None
        updated, actual_seed = update_seed(workflow, seed)
        if updated:
            changes.append(f"seed ({actual_seed})")
    if args.width or args.height:
        if update_resolution(workflow, args.width, args.height):
            changes.append(f"resolution ({args.width}x{args.height})")
    if args.steps:
        if update_sampler_steps(workflow, args.steps):
            changes.append(f"steps ({args.steps})")
    if args.cfg:
        if update_cfg(workflow, args.cfg):
            changes.append(f"cfg ({args.cfg})")
    if args.model:
        if update_model(workflow, args.model):
            changes.append(f"model ({args.model})")

    save_workflow(args.output, workflow)
    print(json.dumps({"ok": True, "changes": changes, "output": args.output}))


if __name__ == "__main__":
    main()
