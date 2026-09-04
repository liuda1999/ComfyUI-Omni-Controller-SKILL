#!/usr/bin/env python3
"""
Main controller for ComfyUI operations.
Acts as a unified entry point for all ComfyUI control actions.
"""
import argparse
import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "assets")


def run_script(script_name, args_list):
    """Run a sub-script and return its JSON output."""
    script_path = os.path.join(SCRIPT_DIR, script_name)
    cmd = [sys.executable, script_path] + args_list
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "raw_output": result.stdout, "error": result.stderr}


def main():
    ap = argparse.ArgumentParser(description="ComfyUI Controller")
    ap.add_argument("action", choices=[
        "start", "stop", "status", "run", "edit", "download", "models"
    ], help="Action to perform")
    ap.add_argument("--workflow", help="Path to workflow JSON")
    ap.add_argument("--output", help="Output path for edited workflow")
    ap.add_argument("--positive-prompt", help="Positive prompt text")
    ap.add_argument("--negative-prompt", help="Negative prompt text")
    ap.add_argument("--seed", type=int, help="Random seed")
    ap.add_argument("--random-seed", action="store_true", help="Use random seed")
    ap.add_argument("--width", type=int, help="Image width")
    ap.add_argument("--height", type=int, help="Image height")
    ap.add_argument("--steps", type=int, help="Sampler steps")
    ap.add_argument("--cfg", type=float, help="CFG scale")
    ap.add_argument("--model", help="Model name")
    ap.add_argument("--count", type=int, default=1, help="Number of images to generate")
    ap.add_argument("--url", help="Model download URL")
    ap.add_argument("--subfolder", help="Model subfolder")
    ap.add_argument("--host", default=os.environ.get("COMFYUI_HOST", "127.0.0.1"))
    ap.add_argument("--port", default=os.environ.get("COMFYUI_PORT", "3198"))  # comfyui-cli项目标准端口
    args = ap.parse_args()

    if args.action == "start":
        result = run_script("start_server.py", ["--host", args.host, "--port", args.port])
        print(json.dumps(result, indent=2))

    elif args.action == "stop":
        result = run_script("stop_server.py", [])
        print(json.dumps(result, indent=2))

    elif args.action == "status":
        result = run_script("check_status.py", ["--host", args.host, "--port", args.port])
        print(json.dumps(result, indent=2))

    elif args.action == "run":
        workflow_path = args.workflow or os.path.join(ASSETS_DIR, "default-workflow.json")
        if not os.path.isfile(workflow_path):
            print(json.dumps({"ok": False, "error": f"Workflow not found: {workflow_path}"}))
            sys.exit(1)

        # Check status first
        status = run_script("check_status.py", ["--host", args.host, "--port", args.port])
        if not status.get("ok"):
            print(json.dumps({"ok": False, "error": "Server not running", "status": status}))
            sys.exit(1)

        # If editing parameters, create temp workflow
        if any([args.positive_prompt, args.negative_prompt, args.seed, args.random_seed,
                args.width, args.height, args.steps, args.cfg, args.model]):
            tmp_path = os.path.join(ASSETS_DIR, "tmp-workflow.json")
            edit_args = ["--input", workflow_path, "--output", tmp_path]
            if args.positive_prompt:
                edit_args += ["--positive-prompt", args.positive_prompt]
            if args.negative_prompt:
                edit_args += ["--negative-prompt", args.negative_prompt]
            if args.seed is not None:
                edit_args += ["--seed", str(args.seed)]
            if args.random_seed:
                edit_args += ["--random-seed"]
            if args.width:
                edit_args += ["--width", str(args.width)]
            if args.height:
                edit_args += ["--height", str(args.height)]
            if args.steps:
                edit_args += ["--steps", str(args.steps)]
            if args.cfg:
                edit_args += ["--cfg", str(args.cfg)]
            if args.model:
                edit_args += ["--model", args.model]

            edit_result = run_script("edit_workflow.py", edit_args)
            if not edit_result.get("ok"):
                print(json.dumps({"ok": False, "error": "Failed to edit workflow", "detail": edit_result}))
                sys.exit(1)
            workflow_path = tmp_path

        # Run workflow (possibly multiple times)
        all_results = []
        for i in range(args.count):
            if i > 0 and args.random_seed:
                # Re-edit with new random seed for each run
                tmp_path = os.path.join(ASSETS_DIR, f"tmp-workflow-{i}.json")
                run_script("edit_workflow.py", [
                    "--input", workflow_path, "--output", tmp_path, "--random-seed"
                ])
                run_path = tmp_path
            else:
                run_path = workflow_path

            run_result = run_script("run_workflow.py", [
                "--host", args.host, "--port", args.port, "--workflow", run_path
            ])
            all_results.append(run_result)

        print(json.dumps({"ok": True, "runs": all_results}))

    elif args.action == "edit":
        if not args.workflow:
            print(json.dumps({"ok": False, "error": "--workflow required"}))
            sys.exit(1)
        output_path = args.output or os.path.join(ASSETS_DIR, "tmp-workflow.json")
        edit_args = ["--input", args.workflow, "--output", output_path]
        if args.positive_prompt:
            edit_args += ["--positive-prompt", args.positive_prompt]
        if args.negative_prompt:
            edit_args += ["--negative-prompt", args.negative_prompt]
        if args.seed is not None:
            edit_args += ["--seed", str(args.seed)]
        if args.random_seed:
            edit_args += ["--random-seed"]
        if args.width:
            edit_args += ["--width", str(args.width)]
        if args.height:
            edit_args += ["--height", str(args.height)]
        if args.steps:
            edit_args += ["--steps", str(args.steps)]
        if args.cfg:
            edit_args += ["--cfg", str(args.cfg)]
        if args.model:
            edit_args += ["--model", args.model]

        result = run_script("edit_workflow.py", edit_args)
        print(json.dumps(result, indent=2))

    elif args.action == "download":
        if not args.url:
            print(json.dumps({"ok": False, "error": "--url required"}))
            sys.exit(1)
        download_args = [args.url]
        if args.subfolder:
            download_args += ["--subfolder", args.subfolder]
        result = run_script("download_models.py", download_args)
        print(json.dumps(result, indent=2))

    elif args.action == "models":
        result = run_script("get_available_models.py", ["--host", args.host, "--port", args.port])
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
